#!/usr/bin/env python3
"""GGG 工作流的共享校验逻辑。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# 确保从任意目录调用时都能正确 import 同目录下的模块
sys.path.insert(0, str(Path(__file__).resolve().parent))

from workflow_contracts import (
    ALL_PHASES,
    BASELINE_REQUIRED_TOKENS,
    CANONICAL_STAGE_FILES,
    CODE_REVIEW_INDEX_REQUIRED_TOKENS,
    CODE_REVIEW_ROUND_REQUIRED_TOKENS,
    DESIGN_HARD_RESIDUAL_TOKENS,
    DESIGN_RISK_ONLY_TOKENS,
    DESIGN_REQUIRED_TOKENS,
    IMPLEMENTATION_LOG_REQUIRED_TOKENS,
    INTERFACE_DETAIL_FILENAME,
    INTERFACE_DETAIL_REQUIRED_TOKENS,
    PLACEHOLDER_TOKENS,
    PUBLIC_PHASES,
    RESEARCH_REQUIRED_TOKENS,
    REVIEW_FLAG_KEYS,
    STAGE_FILE_ALIASES,
    TASK_REQUIRED_TOKENS,
    TEST_REPORT_INDEX_REQUIRED_TOKENS,
    TEST_REPORT_ROUND_REQUIRED_TOKENS,
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_meta(feature_dir: Path) -> dict:
    meta_path = feature_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError("缺少 meta.json")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def assert_contains(text: str, tokens: list[str], label: str, errors: list[str]) -> None:
    for token in tokens:
        if token not in text:
            errors.append(f"{label} 缺少关键内容: {token}")


def assert_not_exists(path: Path, label: str, errors: list[str]) -> None:
    if path.exists():
        errors.append(f"{label} 不应在当前阶段提前生成")


def assert_stage_doc_naming(feature_dir: Path, errors: list[str]) -> None:
    for child in feature_dir.iterdir():
        if child.is_dir():
            continue

        name = child.name
        if name in STAGE_FILE_ALIASES:
            errors.append(f"发现重复或非标准阶段文档: {name}，请改为 {STAGE_FILE_ALIASES[name]}")
            continue

        if re.match(r"^\d{2}-.*\.(md|sql)$", name) and name not in CANONICAL_STAGE_FILES:
            errors.append(f"发现非标准阶段文档名: {name}。阶段主文档只允许使用固定编号文件名")


def extract_section(text: str, heading: str) -> str:
    lines = text.splitlines()
    start = None
    current_level = None
    for idx, line in enumerate(lines):
        if line.strip() == heading:
            start = idx
            current_level = len(line) - len(line.lstrip("#"))
            break
    if start is None or current_level is None:
        return ""

    section_lines = []
    for idx in range(start, len(lines)):
        line = lines[idx]
        if idx > start and line.lstrip().startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            if level <= current_level:
                break
        section_lines.append(line)
    return "\n".join(section_lines)


def section_meaningful_lines(section_text: str) -> list[str]:
    lines: list[str] = []
    for raw in section_text.splitlines()[1:]:
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if stripped in ["```", "```text", "```json", "```plantuml", "```sql"]:
            continue
        if re.fullmatch(r"\|[-\s|:]+\|?", stripped):
            continue
        lines.append(stripped)
    return lines


def assert_no_unresolved_placeholders(text: str, label: str, errors: list[str]) -> None:
    for token in PLACEHOLDER_TOKENS:
        if token in text:
            errors.append(f"{label} 仍包含未收口占位内容: {token}")


def assert_no_design_residuals(
    text: str,
    label: str,
    errors: list[str],
    allow_risk_confirmation: bool = False,
) -> None:
    for token in DESIGN_HARD_RESIDUAL_TOKENS:
        if token in text:
            errors.append(f"{label} 仍包含技术方案阶段未收口残留: {token}")

    risk_checked_text = text
    if allow_risk_confirmation:
        risk_section = extract_section(text, "## 十六、测试链路与风险")
        if risk_section:
            risk_checked_text = text.replace(risk_section, "", 1)

    for token in DESIGN_RISK_ONLY_TOKENS:
        if token in risk_checked_text:
            errors.append(f"{label} 只能在非阻塞风险章节保留并解释: {token}")


def assert_section_has_substance(
    section_text: str,
    heading: str,
    label: str,
    errors: list[str],
    min_lines: int = 1,
) -> None:
    lines = section_meaningful_lines(section_text)
    if len(lines) < min_lines:
        errors.append(f"{label} 的 {heading} 内容过少，仍像模板占位")


def extract_line_value(text: str, prefix: str) -> str:
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip()
    return ""


def assert_line_has_value(text: str, prefix: str, message: str, errors: list[str], min_chars: int = 1) -> None:
    value = extract_line_value(text, prefix)
    if len(value) < min_chars:
        errors.append(message)


def assert_regex_exists(text: str, pattern: str, message: str, errors: list[str]) -> None:
    if not re.search(pattern, text, re.MULTILINE):
        errors.append(message)


def assert_table_has_headers(text: str, headers: list[str], message: str, errors: list[str]) -> None:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = split_table_row(stripped)
        if cells and all(header in cells for header in headers):
            return
    errors.append(message)


def split_table_row(row: str) -> list[str]:
    stripped = row.strip()
    if not stripped.startswith("|"):
        return []
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if cells and re.fullmatch(r"[-:\s]+", "".join(cells)):
        return []
    return cells


def extract_first_table(section_text: str) -> tuple[list[str], list[list[str]]]:
    headers: list[str] = []
    rows: list[list[str]] = []
    for line in section_text.splitlines():
        cells = split_table_row(line.strip())
        if not cells:
            continue
        if not headers:
            headers = cells
            continue
        rows.append(cells)
    return headers, rows


def iter_markdown_tables(section_text: str) -> list[tuple[list[str], list[list[str]]]]:
    tables: list[tuple[list[str], list[list[str]]]] = []
    headers: list[str] = []
    rows: list[list[str]] = []

    for line in section_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            if headers:
                tables.append((headers, rows))
                headers = []
                rows = []
            continue

        cells = split_table_row(stripped)
        if not cells:
            continue
        if not headers:
            headers = cells
            continue
        rows.append(cells)

    if headers:
        tables.append((headers, rows))
    return tables


def table_cell(headers: list[str], row: list[str], header: str) -> str:
    if header not in headers:
        return ""
    idx = headers.index(header)
    if idx >= len(row):
        return ""
    return row[idx].strip()


def evidence_refs(value: str) -> set[str]:
    return set(re.findall(r"\bE\d+\b", value))


def claim_refs(value: str) -> set[str]:
    return set(re.findall(r"\bC\d+\b", value))


def design_refs(value: str) -> set[str]:
    return set(re.findall(r"\bD\d+\b", value))


def extract_table_ids(section_text: str, id_pattern: str) -> set[str]:
    _headers, rows = extract_first_table(section_text)
    ids: set[str] = set()
    compiled = re.compile(id_pattern)
    for row in rows:
        if not row:
            continue
        candidate = row[0].strip()
        if compiled.fullmatch(candidate):
            ids.add(candidate)
    return ids


def extract_claim_ids_from_research(text: str) -> set[str]:
    return extract_table_ids(extract_section(text, "## 9. 结论账本（Claim Ledger）"), r"C\d+")


def extract_design_ids_from_design(text: str) -> set[str]:
    ids: set[str] = set()
    for headers, rows in iter_markdown_tables(text):
        if "设计ID" not in headers:
            continue
        for row in rows:
            ids.update(design_refs(table_cell(headers, row, "设计ID")))
    return ids


EVIDENCE_LEVELS = {
    "代码已证实",
    "编译已证实",
    "接口已证实",
    "数据已证实",
    "推断",
    "未覆盖",
    "阻塞",
}

CONFIDENCE_LEVELS = {"高", "中", "低"}

FILE_EVIDENCE_TYPES = {
    "Controller",
    "Service",
    "Manager",
    "Mapper",
    "Facade",
    "Provider",
    "Consumer",
    "DTO",
    "VO",
    "Entity",
    "实体",
    "枚举",
    "常量",
    "配置",
    "SQL",
    "XML",
    "Job",
    "MQ",
}

NON_FILE_EVIDENCE_TYPES = {
    "运行时",
    "接口",
    "日志",
    "数据证据",
    "DB",
    "ES",
    "Redis",
    "命令输出",
}


def infer_repo_root_from_feature(feature_dir: Path) -> Path:
    if feature_dir.parent.name == "features" and feature_dir.parent.parent.name == "ggg":
        return feature_dir.parent.parent.parent
    return feature_dir


def infer_repo_root_from_doc(path: Path) -> Path:
    parent = path.parent
    if parent.parent.name == "features" and parent.parent.parent.name == "ggg":
        return parent.parent.parent.parent
    return parent


def is_file_evidence_type(value: str) -> bool:
    normalized = re.sub(r"[、,，;；/]+", " ", value)
    tokens = {token.strip() for token in normalized.split() if token.strip()}
    if tokens & NON_FILE_EVIDENCE_TYPES:
        return False
    return bool(tokens & FILE_EVIDENCE_TYPES)


def extract_location_refs(value: str) -> list[tuple[str, int]]:
    normalized = re.sub(r"<br\s*/?>", "、", value, flags=re.IGNORECASE)
    parts = re.split(r"[、,，;；\n]+", normalized)
    refs: list[tuple[str, int]] = []
    for raw_part in parts:
        part = raw_part.strip().strip("`")
        if not part or part in {"-", "无", "不涉及"}:
            continue
        markdown_match = re.match(r"^\[[^\]]+\]\((.+)\)$", part)
        if markdown_match:
            part = markdown_match.group(1).strip()
        part = part.strip("<>").strip()
        match = re.match(r"^(.+):(\d+)(?:-\d+)?$", part)
        if match:
            refs.append((match.group(1).strip(), int(match.group(2))))
    return refs


def resolve_evidence_path(raw_path: str, repo_root: Path) -> Path:
    normalized = raw_path.replace("/", "\\")
    candidate = Path(normalized)
    if candidate.is_absolute():
        return candidate
    return repo_root / candidate


def assert_file_evidence_locations(evidence: str, repo_root: Path, errors: list[str]) -> None:
    headers, rows = extract_first_table(evidence)
    for row in rows:
        evidence_id = table_cell(headers, row, "编号")
        evidence_type = table_cell(headers, row, "类型")
        location = table_cell(headers, row, "位置")
        if not re.fullmatch(r"E\d+", evidence_id or ""):
            continue
        if not is_file_evidence_type(evidence_type):
            continue

        refs = extract_location_refs(location)
        if not refs:
            errors.append(f"01-research.md {evidence_id} 文件类证据位置必须使用 path:line 格式，当前为: {location}")
            continue

        for raw_path, line_no in refs:
            resolved = resolve_evidence_path(raw_path, repo_root)
            if not resolved.exists() or not resolved.is_file():
                errors.append(f"01-research.md {evidence_id} 证据位置文件不存在: {raw_path}")
                continue
            try:
                line_count = len(resolved.read_text(encoding="utf-8", errors="ignore").splitlines())
            except OSError as exc:
                errors.append(f"01-research.md {evidence_id} 证据位置无法读取: {raw_path} ({exc})")
                continue
            if line_no < 1 or line_no > line_count:
                errors.append(
                    f"01-research.md {evidence_id} 证据位置行号越界: {raw_path}:{line_no}，文件共 {line_count} 行"
                )


def split_path_list(value: str) -> list[str]:
    normalized = re.sub(r"<br\s*/?>", "、", value, flags=re.IGNORECASE)
    parts = re.split(r"[、,，;；\n]+", normalized)
    ignored = {"", "-", "无", "不涉及", "只读", "同上"}
    return [part.strip(" `") for part in parts if part.strip(" `") not in ignored]


def extract_worker_assignment_rows(text: str) -> list[list[str]]:
    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if "多 agent 并行编码分配表" in line:
            start = idx
            break
    if start is None:
        for idx, line in enumerate(lines):
            cells = split_table_row(line)
            if cells and cells[0] == "Worker":
                start = idx - 1
                break
    if start is None:
        return []

    rows: list[list[str]] = []
    seen_header = False
    for line in lines[start + 1:]:
        stripped = line.strip()
        if not stripped:
            if seen_header and rows:
                break
            continue
        if not stripped.startswith("|"):
            if seen_header:
                break
            continue
        cells = split_table_row(stripped)
        if not cells:
            continue
        if cells[0] == "Worker":
            seen_header = True
            continue
        if seen_header and cells and re.fullmatch(r"W\d+", cells[0]):
            rows.append(cells)
    return rows


def assert_worker_assignment_quality(text: str, errors: list[str]) -> None:
    rows = extract_worker_assignment_rows(text)
    if not rows:
        errors.append("03-tasks.md 多 agent 并行编码分配表缺少可解析的 Worker 分配行")
        return

    allowed_owner: dict[str, str] = {}
    for row in rows:
        if len(row) < 8:
            errors.append(f"03-tasks.md Worker 分配行列数不足: {' | '.join(row)}")
            continue

        worker, task, allowed, forbidden, _readonly, _deps, merge_order, verify = row[:8]
        if not re.fullmatch(r"W\d+", worker):
            errors.append(f"03-tasks.md Worker 编号不规范: {worker}")
        if not re.search(r"\bT\d+\b", task):
            errors.append(f"03-tasks.md {worker} 缺少任务编号 Tn")
        if not split_path_list(allowed):
            errors.append(f"03-tasks.md {worker} 缺少允许修改文件/目录")
        if not split_path_list(forbidden):
            errors.append(f"03-tasks.md {worker} 缺少禁止修改文件/目录")
        if not merge_order or merge_order in {"-", "无", "不涉及"}:
            errors.append(f"03-tasks.md {worker} 缺少合并顺序")
        if not verify or verify in {"-", "无", "不涉及"}:
            errors.append(f"03-tasks.md {worker} 缺少验证命令")

        for path in split_path_list(allowed):
            previous_worker = allowed_owner.get(path)
            if previous_worker and previous_worker != worker:
                errors.append(
                    f"03-tasks.md 多 agent 分配冲突: {previous_worker} 和 {worker} 都允许修改 {path}"
                )
            else:
                allowed_owner[path] = worker


def extract_parallel_execution_level(text: str) -> str:
    for raw in text.splitlines():
        match = re.search(r"并行(?:执行)?等级[：:]\s*(L[012])", raw)
        if match:
            return match.group(1)

    # Backward compatibility for older task docs that predate L0/L1/L2.
    if re.search(r"\|\s*W\d+\s*\|", text):
        return "L2"
    if "并行安全评估矩阵" in text and re.search(r"\b(可并行|需串行|先锁契约)\b", text):
        return "L1"
    return ""


def assert_l0_parallel_reason(text: str, errors: list[str]) -> None:
    if not re.search(r"不并行原因(?:（[^）]*）)?[：:]\s*\S+", text):
        errors.append("03-tasks.md 并行等级为 L0 时必须写清不并行原因")
    if not re.search(r"推荐执行顺序[：:]\s*\S+", text):
        errors.append("03-tasks.md 并行等级为 L0 时必须写清推荐串行执行顺序")
    if extract_worker_assignment_rows(text):
        errors.append("03-tasks.md 并行等级为 L0 时不应输出多 agent Worker 分配行")


def assert_l1_or_l2_parallel_matrix(text: str, errors: list[str]) -> None:
    for token in ["并行安全评估矩阵", "共享依赖", "契约/表/配置影响", "冲突结论", "执行方式"]:
        if token not in text:
            errors.append(f"03-tasks.md 缺少并行安全评估内容: {token}")
    assert_regex_exists(
        text,
        r"\b(可并行|需串行|先锁契约)\b",
        "03-tasks.md 并行安全评估缺少冲突结论",
        errors,
    )
    assert_regex_exists(
        text,
        r"\b(并行|串行|准备并行)\b",
        "03-tasks.md 并行安全评估缺少执行方式",
        errors,
    )


def assert_l2_worker_assignment(text: str, errors: list[str]) -> None:
    for token in [
        "多 agent 并行编码分配表",
        "Worker",
        "允许修改文件/目录",
        "禁止修改文件/目录",
        "只读参考文件/目录",
        "合并顺序",
        "验证命令",
    ]:
        if token not in text:
            errors.append(f"03-tasks.md 缺少多 agent 并行编码分配内容: {token}")
    assert_regex_exists(
        text,
        r"\|\s*W\d+\s*\|",
        "03-tasks.md 多 agent 并行编码分配表缺少 Worker 行",
        errors,
    )
    assert_worker_assignment_quality(text, errors)


def assert_baseline_quality(text: str, errors: list[str]) -> None:
    understanding = extract_section(text, "## 2. 需求理解")
    scope = extract_section(text, "## 3. 范围边界")
    user_path = extract_section(text, "## 4. 用户路径与前后端职责")
    business_rules = extract_section(text, "## 5. 业务规则矩阵")
    data_identity = extract_section(text, "## 6. 数据身份矩阵")
    old_chain = extract_section(text, "## 7. 旧链路复用与隔离")
    acceptance = extract_section(text, "## 8. 验收标准")

    assert_line_has_value(text, "- 主项目：", "00-baseline.md 缺少主项目", errors)
    assert_section_has_substance(understanding, "## 2. 需求理解", "00-baseline.md", errors, min_lines=2)
    assert_section_has_substance(scope, "## 3. 范围边界", "00-baseline.md", errors, min_lines=2)
    assert_table_has_headers(
        user_path,
        ["用户/角色", "动作", "后端职责"],
        "00-baseline.md 用户路径与前后端职责缺少关键表头: 用户/角色、动作、后端职责",
        errors,
    )
    assert_table_has_headers(
        business_rules,
        ["规则", "输入", "输出", "边界"],
        "00-baseline.md 业务规则矩阵缺少关键表头: 规则、输入、输出、边界",
        errors,
    )
    assert_table_has_headers(
        data_identity,
        ["业务对象", "唯一标识", "去重维度", "状态隔离维度"],
        "00-baseline.md 数据身份矩阵缺少关键表头: 业务对象、唯一标识、去重维度、状态隔离维度",
        errors,
    )
    assert_table_has_headers(
        old_chain,
        ["旧链路", "复用结论", "隔离方式", "风险"],
        "00-baseline.md 旧链路复用与隔离缺少关键表头: 旧链路、复用结论、隔离方式、风险",
        errors,
    )
    assert_table_has_headers(
        acceptance,
        ["验收点", "验证方式"],
        "00-baseline.md 验收标准缺少关键表头: 验收点、验证方式",
        errors,
    )


def assert_research_evidence_quality(
    baseline_check: str,
    coverage: str,
    claim_ledger: str,
    evidence: str,
    errors: list[str],
    repo_root: Path | None = None,
) -> None:
    evidence_ids = extract_table_ids(evidence, r"E\d+")
    claim_ids = extract_table_ids(claim_ledger, r"C\d+")
    if not evidence_ids:
        errors.append("01-research.md 代码证据索引缺少可追溯的 E1/E2 证据行")
    if not claim_ids:
        errors.append("01-research.md 结论账本缺少可追溯的 C1/C2 结论行")

    baseline_headers, baseline_rows = extract_first_table(baseline_check)
    for row in baseline_rows:
        status = table_cell(baseline_headers, row, "验证状态")
        evidence_value = table_cell(baseline_headers, row, "证据ID")
        if status == "已验证" and not evidence_refs(evidence_value):
            item = table_cell(baseline_headers, row, "baseline 条目") or "未命名条目"
            errors.append(f"01-research.md Baseline 验证清单中“{item}”标为已验证但缺少 Exx 证据ID")

    coverage_headers, coverage_rows = extract_first_table(coverage)
    for row in coverage_rows:
        claim_id = table_cell(coverage_headers, row, "结论ID")
        if not re.fullmatch(r"C\d+", claim_id or ""):
            continue
        level = table_cell(coverage_headers, row, "证据等级")
        confidence = table_cell(coverage_headers, row, "置信度")
        if claim_id not in claim_ids:
            errors.append(f"01-research.md 覆盖度表引用了未登记到结论账本的结论ID: {claim_id}")
        if level not in EVIDENCE_LEVELS:
            errors.append(f"01-research.md {claim_id} 证据等级不合法: {level}")
        if confidence not in CONFIDENCE_LEVELS:
            errors.append(f"01-research.md {claim_id} 置信度必须明确为 高 / 中 / 低，当前为: {confidence}")
        if confidence == "高" and level in {"推断", "未覆盖", "阻塞"}:
            errors.append(f"01-research.md {claim_id} 不能在证据等级为“{level}”时标为高置信")

    ledger_headers, ledger_rows = extract_first_table(claim_ledger)
    for row in ledger_rows:
        claim_id = table_cell(ledger_headers, row, "结论ID")
        if not re.fullmatch(r"C\d+", claim_id or ""):
            continue
        claim_text = table_cell(ledger_headers, row, "关键结论")
        evidence_value = table_cell(ledger_headers, row, "证据ID")
        level = table_cell(ledger_headers, row, "证据等级")
        confidence = table_cell(ledger_headers, row, "置信度")
        uncovered = table_cell(ledger_headers, row, "未覆盖范围")
        follow_up = table_cell(ledger_headers, row, "后续确认方式")
        refs = evidence_refs(evidence_value)

        if not claim_text or claim_text in {"-", "无"}:
            errors.append(f"01-research.md {claim_id} 缺少关键结论文本")
        if not refs:
            errors.append(f"01-research.md {claim_id} 缺少 Exx 证据ID")
        for ref in refs:
            if ref not in evidence_ids:
                errors.append(f"01-research.md {claim_id} 引用了不存在于代码证据索引的证据ID: {ref}")
        if level not in EVIDENCE_LEVELS:
            errors.append(f"01-research.md {claim_id} 证据等级不合法: {level}")
        if confidence not in CONFIDENCE_LEVELS:
            errors.append(f"01-research.md {claim_id} 置信度必须明确为 高 / 中 / 低，当前为: {confidence}")
        if confidence == "高" and level in {"推断", "未覆盖", "阻塞"}:
            errors.append(f"01-research.md {claim_id} 不能在证据等级为“{level}”时标为高置信")
        if level in {"推断", "未覆盖", "阻塞"} and (not uncovered or not follow_up):
            errors.append(f"01-research.md {claim_id} 为“{level}”时必须写清未覆盖范围和后续确认方式")

    if repo_root is not None:
        assert_file_evidence_locations(evidence, repo_root, errors)


def assert_research_quality(text: str, errors: list[str], repo_root: Path | None = None) -> None:
    baseline_check = extract_section(text, "## 1. Baseline 验证清单")
    main_flow = extract_section(text, "## 2. 主链路代码事实")
    old_side_effects = extract_section(text, "## 3. 旧链路副作用清单")
    data_identity = extract_section(text, "## 4. 数据身份和状态维度对照")
    reuse = extract_section(text, "## 5. 复用性分级")
    reverse_impact = extract_section(text, "## 6. 旧能力反向影响检查")
    coverage = extract_section(text, "## 8. 代码证据覆盖度、运行时证据缺口和置信度")
    claim_ledger = extract_section(text, "## 9. 结论账本（Claim Ledger）")
    residual_risk = extract_section(text, "## 11. 残余风险和后续确认方式")
    evidence = extract_section(text, "## 12. 代码证据索引")

    assert_section_has_substance(baseline_check, "## 1. Baseline 验证清单", "01-research.md", errors, min_lines=2)
    assert_section_has_substance(main_flow, "## 2. 主链路代码事实", "01-research.md", errors, min_lines=2)
    assert_section_has_substance(old_side_effects, "## 3. 旧链路副作用清单", "01-research.md", errors, min_lines=2)
    assert_section_has_substance(data_identity, "## 4. 数据身份和状态维度对照", "01-research.md", errors, min_lines=2)
    assert_section_has_substance(reuse, "## 5. 复用性分级", "01-research.md", errors, min_lines=2)
    assert_section_has_substance(reverse_impact, "## 6. 旧能力反向影响检查", "01-research.md", errors, min_lines=2)
    assert_section_has_substance(coverage, "## 8. 代码证据覆盖度、运行时证据缺口和置信度", "01-research.md", errors, min_lines=2)
    assert_section_has_substance(claim_ledger, "## 9. 结论账本（Claim Ledger）", "01-research.md", errors, min_lines=2)
    assert_section_has_substance(residual_risk, "## 11. 残余风险和后续确认方式", "01-research.md", errors, min_lines=2)
    assert_table_has_headers(
        baseline_check,
        ["baseline 条目", "验证状态", "代码事实", "证据ID", "风险"],
        "01-research.md Baseline 验证清单缺少关键表头: baseline 条目、验证状态、代码事实、证据ID、风险",
        errors,
    )
    assert_table_has_headers(
        old_side_effects,
        ["旧能力", "反向影响范围", "结论"],
        "01-research.md 旧链路副作用清单缺少关键表头: 旧能力、反向影响范围、结论",
        errors,
    )
    assert_table_has_headers(
        data_identity,
        ["业务对象", "唯一标识", "状态隔离维度"],
        "01-research.md 数据身份和状态维度对照缺少关键表头: 业务对象、唯一标识、状态隔离维度",
        errors,
    )
    assert_table_has_headers(
        coverage,
        ["结论ID", "证据来源", "证据等级", "未覆盖范围", "运行时证据缺口", "置信度"],
        "01-research.md 代码证据覆盖度缺少关键表头: 结论ID、证据来源、证据等级、未覆盖范围、运行时证据缺口、置信度",
        errors,
    )
    assert_table_has_headers(
        claim_ledger,
        ["结论ID", "关键结论", "证据ID", "证据等级", "置信度", "未覆盖范围", "后续确认方式"],
        "01-research.md 结论账本缺少关键表头: 结论ID、关键结论、证据ID、证据等级、置信度、未覆盖范围、后续确认方式",
        errors,
    )
    assert_table_has_headers(
        evidence,
        ["编号", "项目", "位置", "结论说明"],
        "01-research.md 代码证据索引缺少关键表头: 编号、项目、位置、结论说明",
        errors,
    )
    assert_regex_exists(
        text,
        r"\|\s*E\d+\s*\|\s*[^|\s][^|]*\|",
        "01-research.md 缺少已填写的代码证据行",
        errors,
    )
    assert_research_evidence_quality(baseline_check, coverage, claim_ledger, evidence, errors, repo_root)


def assert_claim_refs_exist(label: str, refs: set[str], valid_claim_ids: set[str] | None, errors: list[str]) -> None:
    if valid_claim_ids is None:
        return
    for ref in refs:
        if ref not in valid_claim_ids:
            errors.append(f"{label} 引用了 01-research.md 中不存在的结论ID: {ref}")


def assert_design_refs_exist(label: str, refs: set[str], valid_design_ids: set[str] | None, errors: list[str]) -> None:
    if valid_design_ids is None:
        return
    for ref in refs:
        if ref not in valid_design_ids:
            errors.append(f"{label} 引用了 02-design.md 中不存在的设计ID: {ref}")


def traceable_row_name(headers: list[str], row: list[str], fallback_index: int) -> str:
    for header in ["设计ID", "表名", "表", "字段", "接口名称", "决策点", "类/文件/表", "变更项", "编号"]:
        value = table_cell(headers, row, header)
        if value and value not in {"-", "无", "不涉及"}:
            return value
    return f"第{fallback_index}行"


def assert_traceable_design_rows(
    section_text: str,
    heading: str,
    required_headers: list[str],
    errors: list[str],
    require_design_id: bool = True,
) -> tuple[set[str], set[str]]:
    matching_tables: list[tuple[list[str], list[list[str]]]] = []
    for headers, rows in iter_markdown_tables(section_text):
        if all(header in headers for header in required_headers):
            matching_tables.append((headers, rows))

    if not matching_tables:
        errors.append(f"02-design.md 的 {heading} 缺少追溯表头: {'、'.join(required_headers)}")
        return set(), set()

    all_design_refs: set[str] = set()
    all_claim_refs: set[str] = set()
    for headers, rows in matching_tables:
        if not rows:
            errors.append(f"02-design.md 的 {heading} 追溯表缺少数据行")
            continue
        for index, row in enumerate(rows, start=1):
            if not any(cell.strip() for cell in row):
                continue
            row_name = traceable_row_name(headers, row, index)
            row_design_refs = design_refs(table_cell(headers, row, "设计ID"))
            row_claim_refs = claim_refs(table_cell(headers, row, "来源Cxx"))

            if require_design_id and not row_design_refs:
                errors.append(f"02-design.md 的 {heading} 行“{row_name}”缺少 Dxx 设计ID")
            if not row_claim_refs:
                errors.append(f"02-design.md 的 {heading} 行“{row_name}”缺少 Cxx 来源引用")

            all_design_refs.update(row_design_refs)
            all_claim_refs.update(row_claim_refs)

    return all_design_refs, all_claim_refs


def assert_design_traceability(
    sql_design: str,
    core_changes: str,
    interface_design: str,
    decisions: str,
    errors: list[str],
    valid_claim_ids: set[str] | None = None,
) -> None:
    _sql_design_refs, sql_claim_refs = assert_traceable_design_rows(
        sql_design, "## 五、SQL 表设计", ["设计ID", "来源Cxx"], errors
    )
    core_design_refs, core_claim_refs = assert_traceable_design_rows(
        core_changes, "## 六、核心改动", ["设计ID", "来源Cxx"], errors
    )
    interface_design_refs, interface_claim_refs = assert_traceable_design_rows(
        interface_design, "## 八、接口设计", ["设计ID", "来源Cxx"], errors
    )
    decision_design_refs, decision_claim_refs = assert_traceable_design_rows(
        decisions, "## 十三、设计决策记录", ["设计ID", "来源Cxx"], errors
    )

    all_claim_refs = sql_claim_refs | core_claim_refs | interface_claim_refs | decision_claim_refs
    assert_claim_refs_exist("02-design.md", all_claim_refs, valid_claim_ids, errors)


def assert_design_quality(text: str, errors: list[str], valid_claim_ids: set[str] | None = None) -> None:
    instance_identity = extract_section(text, "## 二、实例身份与状态隔离")
    contract_flow = extract_section(text, "## 三、前后端接口协作流")
    data_carrier = extract_section(text, "## 四、数据承载设计")
    sql_design = extract_section(text, "## 五、SQL 表设计")
    core_changes = extract_section(text, "## 六、核心改动")
    call_chain = extract_section(text, "## 七、主链路与依赖")
    interface_design = extract_section(text, "## 八、接口设计")
    decisions = extract_section(text, "## 十三、设计决策记录")
    test_risk = extract_section(text, "## 十六、测试链路与风险")

    assert_section_has_substance(instance_identity, "## 二、实例身份与状态隔离", "02-design.md", errors, min_lines=2)
    assert_section_has_substance(contract_flow, "## 三、前后端接口协作流", "02-design.md", errors, min_lines=2)
    assert_section_has_substance(data_carrier, "## 四、数据承载设计", "02-design.md", errors, min_lines=2)
    assert_section_has_substance(sql_design, "## 五、SQL 表设计", "02-design.md", errors, min_lines=2)
    assert_section_has_substance(core_changes, "## 六、核心改动", "02-design.md", errors, min_lines=2)
    assert_section_has_substance(call_chain, "## 七、主链路与依赖", "02-design.md", errors, min_lines=2)
    assert_section_has_substance(interface_design, "## 八、接口设计", "02-design.md", errors, min_lines=2)
    assert_section_has_substance(decisions, "## 十三、设计决策记录", "02-design.md", errors, min_lines=1)
    assert_section_has_substance(test_risk, "## 十六、测试链路与风险", "02-design.md", errors, min_lines=2)
    assert_regex_exists(text, r"@startuml", "02-design.md 缺少时序图", errors)
    assert_design_traceability(sql_design, core_changes, interface_design, decisions, errors, valid_claim_ids)


def assert_interface_detail_quality(path: Path, text: str, errors: list[str]) -> None:
    label = path.name
    if not INTERFACE_DETAIL_FILENAME.fullmatch(path.name):
        errors.append(f"{label} 命名不规范，推荐使用 02-interface-01-主题.md")
    assert_contains(text, INTERFACE_DETAIL_REQUIRED_TOKENS, label, errors)
    assert_no_unresolved_placeholders(text, label, errors)
    assert_no_design_residuals(text, label, errors)


def source_refs(value: str) -> tuple[set[str], set[str], bool, bool]:
    return (
        design_refs(value),
        claim_refs(value),
        "interface-details/" in value or "interface-details\\" in value,
        "04-schema.sql" in value,
    )


def assert_source_value_traceability(
    label: str,
    source: str,
    errors: list[str],
    valid_design_ids: set[str] | None = None,
    valid_claim_ids: set[str] | None = None,
    schema_exists: bool = False,
) -> None:
    source = source.strip()
    d_refs, c_refs, has_interface_ref, has_schema_ref = source_refs(source)
    if not source or source in {"-", "无", "不涉及"}:
        errors.append(f"{label} 缺少来源依据")
        return
    if not (d_refs or c_refs or has_interface_ref or has_schema_ref):
        errors.append(f"{label} 来源依据必须引用 Dxx/Cxx/interface-details/04-schema.sql，当前为: {source}")
    assert_design_refs_exist(label, d_refs, valid_design_ids, errors)
    assert_claim_refs_exist(label, c_refs, valid_claim_ids, errors)
    if has_schema_ref and not schema_exists:
        errors.append(f"{label} 引用了 04-schema.sql，但当前需求目录未发现该文件")


def assert_task_source_traceability(
    overview: str,
    errors: list[str],
    valid_design_ids: set[str] | None = None,
    valid_claim_ids: set[str] | None = None,
    schema_exists: bool = False,
) -> None:
    headers, rows = extract_first_table(overview)
    if "来源依据" not in headers:
        errors.append("03-tasks.md 任务总览缺少来源依据列")
        return

    for row in rows:
        task_id = table_cell(headers, row, "编号")
        if not re.fullmatch(r"T\d+", task_id or ""):
            continue
        source = table_cell(headers, row, "来源依据")
        assert_source_value_traceability(
            f"03-tasks.md {task_id}",
            source,
            errors,
            valid_design_ids,
            valid_claim_ids,
            schema_exists,
        )


def assert_task_detail_source_traceability(
    detail: str,
    errors: list[str],
    valid_design_ids: set[str] | None = None,
    valid_claim_ids: set[str] | None = None,
    schema_exists: bool = False,
) -> None:
    current_task: str | None = None
    current_source: str | None = None

    def flush_current_task() -> None:
        if current_task is None:
            return
        assert_source_value_traceability(
            f"03-tasks.md {current_task} 详细任务",
            current_source or "",
            errors,
            valid_design_ids,
            valid_claim_ids,
            schema_exists,
        )

    for raw in detail.splitlines():
        task_match = re.match(r"^\s*-\s*(T\d+)\s*[：:]", raw)
        if task_match:
            flush_current_task()
            current_task = task_match.group(1)
            current_source = None
            continue
        if current_task is None:
            continue
        source_match = re.match(r"^\s*-\s*来源依据[：:]\s*(.*)$", raw)
        if source_match:
            current_source = source_match.group(1).strip()

    flush_current_task()


def task_mapping_table_name(headers: list[str]) -> str:
    if "接口文档" in headers:
        return "接口映射"
    if "风险点" in headers:
        return "风险映射"
    if "变更项" in headers:
        return "SQL / 配置 / 缓存 / MQ 验证映射"
    return "映射表"


def task_mapping_row_name(headers: list[str], row: list[str], fallback_index: int) -> str:
    for header in ["接口文档", "风险点", "变更项", "实现任务", "验证任务", "测试任务"]:
        value = table_cell(headers, row, header)
        if value and value not in {"-", "无", "不涉及"}:
            return value.strip("`")
    return f"第{fallback_index}行"


def assert_mapping_source_traceability(
    mapping: str,
    errors: list[str],
    valid_design_ids: set[str] | None = None,
    valid_claim_ids: set[str] | None = None,
    schema_exists: bool = False,
) -> None:
    for headers, rows in iter_markdown_tables(mapping):
        known_mapping_table = any(header in headers for header in ["接口文档", "风险点", "变更项"])
        if not known_mapping_table:
            continue
        table_name = task_mapping_table_name(headers)
        if "来源依据" not in headers:
            errors.append(f"03-tasks.md {table_name} 缺少来源依据列")
            continue
        for index, row in enumerate(rows, start=1):
            if not any(cell.strip() for cell in row):
                continue
            row_name = task_mapping_row_name(headers, row, index)
            source = table_cell(headers, row, "来源依据")
            assert_source_value_traceability(
                f"03-tasks.md {table_name} 行“{row_name}”",
                source,
                errors,
                valid_design_ids,
                valid_claim_ids,
                schema_exists,
            )


def assert_tasks_quality(
    text: str,
    errors: list[str],
    interface_details: Path | None = None,
    valid_design_ids: set[str] | None = None,
    valid_claim_ids: set[str] | None = None,
    schema_exists: bool = False,
) -> None:
    overview = extract_section(text, "## 4. 任务总览")
    detail = extract_section(text, "## 5. 详细任务")
    mapping = extract_section(text, "## 6. 接口、风险和测试映射")
    done = extract_section(text, "## 8. 完成定义")
    parallel_level = extract_parallel_execution_level(text)

    assert_regex_exists(
        text,
        r"\|\s*T\d+\s*\|",
        "03-tasks.md 缺少已填写的任务行",
        errors,
    )
    for token in ["来源依据", "预计写入文件/目录", "依赖", "可并行组", "初始状态", "输出物", "完成标准"]:
        if token not in overview:
            errors.append(f"03-tasks.md 任务总览缺少列或内容: {token}")
    if not parallel_level:
        errors.append("03-tasks.md 缺少并行执行等级: L0 / L1 / L2")
    elif parallel_level == "L0":
        assert_l0_parallel_reason(text, errors)
    elif parallel_level == "L1":
        assert_l1_or_l2_parallel_matrix(text, errors)
        if extract_worker_assignment_rows(text):
            errors.append("03-tasks.md 并行等级为 L1 时不应输出多 agent Worker 分配行")
    elif parallel_level == "L2":
        assert_l1_or_l2_parallel_matrix(text, errors)
        assert_l2_worker_assignment(text, errors)
    assert_regex_exists(
        overview,
        r"\|\s*T\d+\s*\|",
        "03-tasks.md 任务总览缺少结构化任务行",
        errors,
    )
    assert_regex_exists(
        overview,
        r"P\d+",
        "03-tasks.md 任务总览缺少可并行组标记",
        errors,
    )
    assert_regex_exists(
        overview,
        r"\b(ready|pending|blocked)\b",
        "03-tasks.md 任务总览缺少 ready/pending/blocked 初始状态",
        errors,
    )
    assert_task_source_traceability(overview, errors, valid_design_ids, valid_claim_ids, schema_exists)
    assert_task_detail_source_traceability(detail, errors, valid_design_ids, valid_claim_ids, schema_exists)
    assert_section_has_substance(detail, "## 5. 详细任务", "03-tasks.md", errors, min_lines=5)
    assert_section_has_substance(mapping, "## 6. 接口、风险和测试映射", "03-tasks.md", errors, min_lines=3)
    assert_table_has_headers(
        mapping,
        ["接口文档", "实现任务", "测试任务"],
        "03-tasks.md 接口映射缺少关键表头: 接口文档、实现任务、测试任务",
        errors,
    )
    assert_mapping_source_traceability(mapping, errors, valid_design_ids, valid_claim_ids, schema_exists)
    if interface_details is not None and interface_details.exists() and interface_details.is_dir():
        for detail_file in sorted(interface_details.glob("*.md")):
            if detail_file.name not in mapping and detail_file.stem not in mapping:
                errors.append(f"03-tasks.md 接口映射缺少接口明细对应测试任务: {detail_file.name}")
    assert_section_has_substance(done, "## 8. 完成定义", "03-tasks.md", errors, min_lines=3)


def assert_schema_quality(text: str, errors: list[str]) -> None:
    assert_regex_exists(
        text,
        r"\b(CREATE|ALTER|INSERT|UPDATE|DELETE)\b",
        "04-schema.sql 缺少实际 SQL 语句",
        errors,
    )


def validate_baseline_doc(path: Path) -> list[str]:
    errors: list[str] = []
    text = read_text(path)
    if not text:
        return [f"缺少 {path.name}"]
    assert_contains(text, BASELINE_REQUIRED_TOKENS, path.name, errors)
    assert_baseline_quality(text, errors)
    return errors


def validate_research_doc(path: Path, repo_root: Path | None = None) -> list[str]:
    errors: list[str] = []
    text = read_text(path)
    if not text:
        return [f"缺少 {path.name}"]
    if repo_root is None:
        repo_root = infer_repo_root_from_doc(path)
    assert_contains(text, RESEARCH_REQUIRED_TOKENS, path.name, errors)
    assert_no_unresolved_placeholders(text, path.name, errors)
    assert_research_quality(text, errors, repo_root)
    return errors


def validate_interface_details_dir(interface_details: Path) -> list[str]:
    errors: list[str] = []
    if interface_details.exists() and not interface_details.is_dir():
        return ["interface-details/ 必须是目录"]

    if interface_details.exists() and interface_details.is_dir():
        detail_files = sorted(interface_details.glob("*.md"))
        if not detail_files:
            errors.append("interface-details/ 已创建但没有任何接口明细文档")
        for detail_file in detail_files:
            assert_interface_detail_quality(detail_file, read_text(detail_file), errors)
    return errors


def validate_design_doc(
    path: Path,
    interface_details: Path | None = None,
    valid_claim_ids: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    text = read_text(path)
    if not text:
        return [f"缺少 {path.name}"]
    assert_contains(text, DESIGN_REQUIRED_TOKENS, path.name, errors)
    assert_no_unresolved_placeholders(text, path.name, errors)
    assert_no_design_residuals(text, path.name, errors, allow_risk_confirmation=True)
    assert_design_quality(text, errors, valid_claim_ids)
    if interface_details is not None:
        errors.extend(validate_interface_details_dir(interface_details))
    return errors


def validate_tasks_doc(
    path: Path,
    interface_details: Path | None = None,
    valid_design_ids: set[str] | None = None,
    valid_claim_ids: set[str] | None = None,
    schema_exists: bool = False,
) -> list[str]:
    errors: list[str] = []
    text = read_text(path)
    if not text:
        return [f"缺少 {path.name}"]
    assert_contains(text, TASK_REQUIRED_TOKENS, path.name, errors)
    assert_no_unresolved_placeholders(text, path.name, errors)
    assert_tasks_quality(text, errors, interface_details, valid_design_ids, valid_claim_ids, schema_exists)
    return errors


def validate_schema_doc(path: Path, meta: dict) -> list[str]:
    errors: list[str] = []
    text = read_text(path)
    if not text:
        return [f"缺少 {path.name}"]
    assert_no_design_residuals(text, path.name, errors)
    assert_schema_quality(text, errors)
    return errors


def validate_implementation_log(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return errors
    text = read_text(path)
    assert_contains(text, IMPLEMENTATION_LOG_REQUIRED_TOKENS, path.name, errors)
    assert_table_has_headers(
        text,
        ["轮次", "任务", "实际修改文件", "验证结果"],
        "05-implementation-log.md 实现记录索引缺少关键表头: 轮次、任务、实际修改文件、验证结果",
        errors,
    )
    assert_table_has_headers(
        text,
        ["偏差", "影响文档", "处理结果"],
        "05-implementation-log.md 偏差与回写记录缺少关键表头: 偏差、影响文档、处理结果",
        errors,
    )
    return errors


def validate_code_review_artifacts(index_path: Path, rounds_dir: Path) -> list[str]:
    errors: list[str] = []
    if index_path.exists():
        text = read_text(index_path)
        assert_contains(text, CODE_REVIEW_INDEX_REQUIRED_TOKENS, index_path.name, errors)
        assert_table_has_headers(
            text,
            ["轮次", "结论", "明细文档", "未关闭问题"],
            "06-code-review.md Review 轮次索引缺少关键表头: 轮次、结论、明细文档、未关闭问题",
            errors,
        )

    if rounds_dir.exists() and rounds_dir.is_dir():
        for round_file in sorted(rounds_dir.glob("*.md")):
            text = read_text(round_file)
            assert_contains(text, CODE_REVIEW_ROUND_REQUIRED_TOKENS, round_file.name, errors)
            assert_table_has_headers(
                text,
                ["级别", "文件行号", "问题", "状态"],
                f"{round_file.name} 问题清单缺少关键表头: 级别、文件行号、问题、状态",
                errors,
            )
            assert_table_has_headers(
                extract_section(text, "## 5. 幻觉审计"),
                ["审计项", "结论", "证据", "风险", "处理建议"],
                f"{round_file.name} 幻觉审计缺少关键表头: 审计项、结论、证据、风险、处理建议",
                errors,
            )
    return errors


def validate_test_report_artifacts(index_path: Path, rounds_dir: Path) -> list[str]:
    errors: list[str] = []
    if index_path.exists():
        text = read_text(index_path)
        assert_contains(text, TEST_REPORT_INDEX_REQUIRED_TOKENS, index_path.name, errors)
        assert_table_has_headers(
            text,
            ["轮次", "结论", "明细文档", "未关闭缺口"],
            "07-test-report.md 测试轮次索引缺少关键表头: 轮次、结论、明细文档、未关闭缺口",
            errors,
        )

    if rounds_dir.exists() and rounds_dir.is_dir():
        for round_file in sorted(rounds_dir.glob("*.md")):
            text = read_text(round_file)
            assert_contains(text, TEST_REPORT_ROUND_REQUIRED_TOKENS, round_file.name, errors)
            assert_table_has_headers(
                text,
                ["场景ID", "应测场景", "状态", "证据"],
                f"{round_file.name} 应测场景清单缺少关键表头: 场景ID、应测场景、状态、证据",
                errors,
            )
    return errors


def validate_feature_dir(feature_dir: Path) -> list[str]:
    errors: list[str] = []
    meta_path = feature_dir / "meta.json"
    if not meta_path.exists():
        return ["缺少 meta.json"]
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    phase = meta.get("current_phase")
    repo_root = infer_repo_root_from_feature(feature_dir)

    if phase not in ALL_PHASES:
        errors.append(f"meta.json.current_phase 非法或缺失: {phase}")
        return errors
    phase_index = PUBLIC_PHASES.index(phase)

    def reached(target_phase: str) -> bool:
        return phase_index >= PUBLIC_PHASES.index(target_phase)

    baseline = feature_dir / "00-baseline.md"
    research = feature_dir / "01-research.md"
    design = feature_dir / "02-design.md"
    tasks = feature_dir / "03-tasks.md"
    schema = feature_dir / "04-schema.sql"
    implementation_log = feature_dir / "05-implementation-log.md"
    code_review_index = feature_dir / "06-code-review.md"
    test_report_index = feature_dir / "07-test-report.md"
    code_review_rounds = feature_dir / "review-rounds"
    test_report_rounds = feature_dir / "test-rounds"
    interface_details = feature_dir / "interface-details"
    review_flags = meta.get("review_flags", {})

    assert_stage_doc_naming(feature_dir, errors)

    if phase == "需求受理":
        assert_not_exists(research, "01-research.md", errors)
        assert_not_exists(design, "02-design.md", errors)
        assert_not_exists(tasks, "03-tasks.md", errors)
        assert_not_exists(schema, "04-schema.sql", errors)
        assert_not_exists(interface_details, "interface-details/", errors)

    if phase == "需求对齐":
        assert_not_exists(design, "02-design.md", errors)
        assert_not_exists(tasks, "03-tasks.md", errors)
        assert_not_exists(schema, "04-schema.sql", errors)
        assert_not_exists(interface_details, "interface-details/", errors)

    if phase == "技术方案":
        assert_not_exists(tasks, "03-tasks.md", errors)

    errors.extend(validate_baseline_doc(baseline))
    research_claim_ids = extract_claim_ids_from_research(read_text(research)) if research.exists() else set()
    design_ids = extract_design_ids_from_design(read_text(design)) if design.exists() else set()

    if reached("需求对齐"):
        errors.extend(validate_research_doc(research, repo_root))

    if reached("技术方案"):
        errors.extend(validate_design_doc(design, interface_details, research_claim_ids))

    if reached("任务拆分"):
        errors.extend(validate_tasks_doc(tasks, interface_details, design_ids, research_claim_ids, schema.exists()))

    if reached("编码实现") and not implementation_log.exists():
        errors.append("当前阶段已进入编码实现，缺少 05-implementation-log.md")
    if reached("代码检查") and not code_review_index.exists():
        errors.append("当前阶段已进入代码检查，缺少 06-code-review.md")
    if reached("测试验证") and not test_report_index.exists():
        errors.append("当前阶段已进入测试验证，缺少 07-test-report.md")

    if schema.exists():
        errors.extend(validate_schema_doc(schema, meta))

    errors.extend(validate_implementation_log(implementation_log))
    errors.extend(validate_code_review_artifacts(code_review_index, code_review_rounds))
    errors.extend(validate_test_report_artifacts(test_report_index, test_report_rounds))

    if review_flags.get("alignment_needs_review") and reached("技术方案"):
        errors.append("需求对齐结论已被澄清影响，需重新确认后再继续当前阶段")
    if review_flags.get("design_needs_review") and reached("技术方案"):
        errors.append("技术方案已被澄清影响，需重新评审后再继续当前阶段")
    if review_flags.get("tasks_needs_review") and reached("任务拆分"):
        errors.append("任务拆分已被澄清影响，需重新确认后再继续当前阶段")

    return errors


def ensure_review_flags(meta: dict) -> dict:
    review_flags = meta.setdefault("review_flags", {})
    for key in REVIEW_FLAG_KEYS:
        review_flags.setdefault(key, False)
    return review_flags


def sync_primary_project_from_baseline(meta: dict, baseline_path: Path) -> None:
    baseline_text = read_text(baseline_path)
    if not baseline_text:
        return
    primary_project = extract_line_value(baseline_text, "- 主项目：")
    if primary_project:
        meta["primary_project"] = primary_project


def unresolved_blockers(text: str) -> int:
    """解析 01-blocking-issues.md，返回未解决的阻塞问题数量。

    判定规则：表格行中编号列匹配 B\\d+，且「是否已确认」列为「否」或为空。
    """
    count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.split("|")]
        # 去掉首尾空元素（split '|' 产生的）
        cells = [c for c in cells if c]
        if len(cells) < 2:
            continue
        # 编号列匹配 B1, B2, ...
        if not re.match(r"^B\d+$", cells[0]):
            continue
        # 最后一列是「是否已确认」
        confirmed = cells[-1].strip() if cells else ""
        if confirmed != "是":
            count += 1
    return count


def current_scope_note() -> str:
    return f"当前 ggg dist 支持到 {PUBLIC_PHASES[-1]} 阶段"
