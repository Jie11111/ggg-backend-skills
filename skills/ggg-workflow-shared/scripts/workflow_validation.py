#!/usr/bin/env python3
"""GGG 工作流的共享校验逻辑。"""

from __future__ import annotations

import json
import hashlib
import re
import sys
from pathlib import Path

# 确保从任意目录调用时都能正确 import 同目录下的模块
sys.path.insert(0, str(Path(__file__).resolve().parent))

from workflow_contracts import (
    ALL_PHASES,
    BASELINE_REQUIRED_TOKENS,
    BASELINE_V5_REQUIRED_TOKENS,
    CANONICAL_STAGE_FILES,
    CODE_REVIEW_INDEX_REQUIRED_TOKENS,
    CODE_REVIEW_ROUND_REQUIRED_TOKENS,
    CODE_REVIEW_SIMPLE_REQUIRED_TOKENS,
    DESIGN_HARD_RESIDUAL_TOKENS,
    DESIGN_RISK_ONLY_TOKENS,
    DESIGN_REQUIRED_TOKENS,
    DESIGN_V4_REQUIRED_TOKENS,
    DESIGN_V5_REQUIRED_TOKENS,
    DESIGN_V6_REQUIRED_TOKENS,
    IMPLEMENTATION_LOG_REQUIRED_TOKENS,
    INTERFACE_DETAIL_FILENAME,
    INTERFACE_DETAIL_REQUIRED_TOKENS,
    INTERFACE_DETAIL_V3_REQUIRED_TOKENS,
    INTERFACE_DETAIL_V4_REQUIRED_TOKENS,
    LEGACY_RESEARCH_REQUIRED_TOKENS,
    PLACEHOLDER_TOKENS,
    PUBLIC_PHASES,
    RESEARCH_REQUIRED_TOKENS,
    RESEARCH_V2_REQUIRED_TOKENS,
    RESEARCH_V3_REQUIRED_TOKENS,
    REVIEW_FLAG_KEYS,
    STAGE_FILE_ALIASES,
    TASK_REQUIRED_TOKENS,
    TASK_V2_REQUIRED_TOKENS,
    TASK_V3_REQUIRED_TOKENS,
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


def extract_sections(text: str, heading: str) -> list[str]:
    """提取所有同名章节；用于发现重复账本，避免只读取第一份造成穿透。"""
    lines = text.splitlines()
    sections: list[str] = []
    for start, line in enumerate(lines):
        if line.strip() != heading:
            continue
        level = len(line) - len(line.lstrip("#"))
        section_lines: list[str] = []
        for index in range(start, len(lines)):
            current = lines[index]
            if index > start and current.lstrip().startswith("#"):
                current_level = len(current) - len(current.lstrip("#"))
                if current_level <= level:
                    break
            section_lines.append(current)
        sections.append("\n".join(section_lines))
    return sections


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


def baseline_source_refs(value: str) -> set[str]:
    return set(re.findall(r"\bQ\d+\b", value))


def baseline_material_refs(value: str) -> set[str]:
    return set(re.findall(r"\bS\d+\b", value))


def baseline_business_fingerprint(text: str) -> str:
    """只对需求基线本体取指纹，排除后续阶段补写的代码现状和差异。"""
    basic_values = [
        extract_line_value(text, "- 需求名称："),
        extract_line_value(text, "- 主项目："),
        extract_line_value(text, "- 主项目判断依据："),
        extract_line_value(text, "- 依赖项目："),
        extract_line_value(text, "- 依赖项目判断依据："),
    ]
    if document_schema_version(text) >= 5:
        basic_values.extend(
            [
                extract_line_value(text, "- 推荐模式："),
                extract_line_value(text, "- 推荐依据："),
                extract_line_value(text, "- 最终模式："),
                extract_line_value(text, "- 模式选择来源："),
            ]
        )
    tracked_sections = [
        extract_section(text, "### 1.1 原始材料覆盖"),
        *(extract_section(text, f"## {index}. {title}") for index, title in [
            (2, "需求理解"),
            (3, "范围边界"),
            (4, "用户路径与前后端职责"),
            (5, "业务规则矩阵"),
            (6, "数据身份矩阵"),
            (7, "旧链路复用与隔离"),
            (8, "验收标准"),
            (9, "疑问与确认记录"),
        ]),
    ]
    normalized = "\n".join(line.rstrip() for line in [*basic_values, *tracked_sections]).strip() + "\n"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def document_schema_version(text: str) -> int:
    match = re.search(r"<!--\s*GGG_SCHEMA_VERSION:\s*(\d+)\s*-->", text)
    return int(match.group(1)) if match else 1


def design_schema_version(text: str) -> int:
    match = re.search(r"<!--\s*GGG_DESIGN_SCHEMA_VERSION:\s*(\d+)\s*-->", text)
    return int(match.group(1)) if match else 1


def task_schema_version(text: str) -> int:
    match = re.search(r"<!--\s*GGG_TASK_SCHEMA_VERSION:\s*(\d+)\s*-->", text)
    return int(match.group(1)) if match else 1


def implementation_schema_version(text: str) -> int:
    match = re.search(
        r"<!--\s*GGG_IMPLEMENTATION_SCHEMA_VERSION:\s*(\d+)\s*-->",
        text,
    )
    return int(match.group(1)) if match else 1


def quick_schema_version(text: str) -> int:
    match = re.search(r"<!--\s*GGG_QUICK_SCHEMA_VERSION:\s*(\d+)\s*-->", text)
    return int(match.group(1)) if match else 1


def review_schema_version(text: str) -> int:
    match = re.search(r"<!--\s*GGG_REVIEW_SCHEMA_VERSION:\s*(\d+)\s*-->", text)
    return int(match.group(1)) if match else 1


def research_schema_version(text: str) -> int:
    match = re.search(r"<!--\s*GGG_RESEARCH_SCHEMA_VERSION:\s*(\d+)\s*-->", text)
    return int(match.group(1)) if match else 1


def sql_schema_version(text: str) -> int:
    match = re.search(r"(?mi)^\s*--\s*GGG_SQL_SCHEMA_VERSION:\s*(\d+)\s*$", text)
    return int(match.group(1)) if match else 1


def sql_draft_version(text: str) -> int:
    match = re.search(r"(?mi)^\s*--\s*GGG_SQL_DRAFT_VERSION:\s*(\d+)\s*$", text)
    return int(match.group(1)) if match else 0


def interface_schema_version(text: str) -> int:
    match = re.search(r"<!--\s*GGG_INTERFACE_SCHEMA_VERSION:\s*(\d+)\s*-->", text)
    return int(match.group(1)) if match else 1


def schema_fingerprint(text: str) -> str:
    normalized = "\n".join(line.rstrip() for line in text.splitlines()).strip() + "\n"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


SQL_IMPACT_TYPES = {
    "不涉及": "none",
    "查询或DML": "query_dml",
    "DDL": "ddl",
}
SQL_DRAFT_TYPES = {"SELECT", "INSERT", "UPDATE", "DELETE", "DDL"}
SQL_DRAFT_MARKER_PATTERN = re.compile(
    r"(?m)^[ \t]*--[ \t]*GGG_SQL:[ \t]*(\{.*\})[ \t]*$"
)


def research_sql_section(text: str) -> str:
    return extract_section(text, "### 7.1 SQL 影响与确认准备")


def research_sql_semantic_fingerprint(text: str) -> str:
    """锁定 Research 中用户确认的 SQL 范围，排除确认动作自身回写字段。"""
    section = research_sql_section(text)
    retained = []
    ignored_prefixes = {
        "- SQL 确认状态：",
        "- SQL 确认来源：",
        "- SQL 语义指纹：",
    }
    for line in section.splitlines():
        stripped = line.strip()
        if any(stripped.startswith(prefix) for prefix in ignored_prefixes):
            continue
        retained.append(line.rstrip())
    normalized = "\n".join(retained).strip() + "\n"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_sql_semantics(text: str) -> str:
    """忽略注释、大小写和空白，保留字符串、标识符和操作顺序。"""
    output: list[str] = []
    index = 0
    state = "normal"
    quote = ""
    pending_space = False
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if state == "normal":
            if char == "-" and next_char == "-":
                state = "line_comment"
                index += 2
                continue
            if char == "#":
                state = "line_comment"
                index += 1
                continue
            if char == "/" and next_char == "*":
                state = "block_comment"
                index += 2
                continue
            if char in {"'", '"', "`"}:
                if pending_space and output and output[-1] != " ":
                    output.append(" ")
                pending_space = False
                state = "quoted"
                quote = char
                output.append(char)
                index += 1
                continue
            if char.isspace():
                pending_space = True
                index += 1
                continue
            if pending_space and output and output[-1] != " ":
                output.append(" ")
            pending_space = False
            output.append(char.lower())
            index += 1
            continue
        if state == "line_comment":
            if char in "\r\n":
                state = "normal"
                pending_space = True
            index += 1
            continue
        if state == "block_comment":
            if char == "*" and next_char == "/":
                state = "normal"
                pending_space = True
                index += 2
            else:
                index += 1
            continue

        output.append(char)
        if char == quote:
            if next_char == quote:
                output.append(next_char)
                index += 2
                continue
            if index == 0 or text[index - 1] != "\\":
                state = "normal"
        index += 1
    return re.sub(r"\s+", " ", "".join(output)).strip()


def extract_sql_draft_entries(
    text: str,
    errors: list[str],
) -> list[dict[str, object]]:
    markers = list(SQL_DRAFT_MARKER_PATTERN.finditer(text))
    entries: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for index, marker in enumerate(markers):
        try:
            metadata = json.loads(marker.group(1))
        except json.JSONDecodeError as exc:
            errors.append(f"sql-draft.sql GGG_SQL JSON 无法解析: {exc.msg}")
            continue
        if not isinstance(metadata, dict):
            errors.append("sql-draft.sql GGG_SQL 必须是 JSON 对象")
            continue
        sql_id = str(metadata.get("id", "")).strip()
        sql_type = str(metadata.get("type", "")).strip().upper()
        objects = metadata.get("objects")
        claims = metadata.get("claims")
        if not re.fullmatch(r"SQL\d+", sql_id):
            errors.append(f"sql-draft.sql GGG_SQL id 非法或缺失: {sql_id or '空'}")
        elif sql_id in seen_ids:
            errors.append(f"sql-draft.sql SQL ID 重复: {sql_id}")
        else:
            seen_ids.add(sql_id)
        if sql_type not in SQL_DRAFT_TYPES:
            errors.append(f"sql-draft.sql {sql_id or '未知 SQL'} type 非法: {sql_type or '空'}")
        for label, values, pattern in [
            ("objects", objects, r"[A-Za-z_`][A-Za-z0-9_.$`-]*"),
            ("claims", claims, r"C\d+"),
        ]:
            if not isinstance(values, list) or not values:
                errors.append(f"sql-draft.sql {sql_id or '未知 SQL'} {label} 必须是非空数组")
                continue
            normalized_values = [str(value).strip() for value in values]
            if any(not re.fullmatch(pattern, value) for value in normalized_values):
                errors.append(
                    f"sql-draft.sql {sql_id or '未知 SQL'} {label} 包含非法值"
                )
            if len(set(normalized_values)) != len(normalized_values):
                errors.append(
                    f"sql-draft.sql {sql_id or '未知 SQL'} {label} 包含重复值"
                )
        statement_end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        statement = text[marker.end():statement_end].strip()
        normalized_statement = normalize_sql_semantics(statement)
        expected_pattern = {
            "SELECT": r"^select\b",
            "INSERT": r"^insert\b",
            "UPDATE": r"^update\b",
            "DELETE": r"^delete\b",
            "DDL": r"^(?:create|alter|drop|truncate|rename)\b",
        }.get(sql_type, r"$^")
        if not normalized_statement or not re.search(expected_pattern, normalized_statement):
            errors.append(
                f"sql-draft.sql {sql_id or '未知 SQL'} 后缺少与 type={sql_type or '空'} 匹配的 SQL"
            )
        if normalized_statement and not normalized_statement.rstrip().endswith(";"):
            errors.append(f"sql-draft.sql {sql_id or '未知 SQL'} 语句缺少结束分号")
        entries.append(
            {
                "id": sql_id,
                "type": sql_type,
                "objects": tuple(str(value).strip() for value in objects)
                if isinstance(objects, list)
                else tuple(),
                "claims": tuple(str(value).strip() for value in claims)
                if isinstance(claims, list)
                else tuple(),
                "statement": normalized_statement,
            }
        )
    return entries


def sql_draft_semantic_fingerprint(text: str) -> str:
    errors: list[str] = []
    entries = extract_sql_draft_entries(text, errors)
    if errors:
        return ""
    payload = json.dumps(entries, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256((payload + "\n").encode("utf-8")).hexdigest()


def research_sql_gate_snapshot(
    text: str,
    errors: list[str],
    valid_claim_ids: set[str] | None = None,
) -> dict[str, object]:
    section = research_sql_section(text)
    if not section:
        errors.append("01-research.md 缺少 SQL 影响与确认准备")
        return {
            "impact_type": "",
            "draft": "",
            "status": "",
            "source": "",
            "semantic_fingerprint": "",
            "rows": {},
        }
    display_impact = extract_line_value(section, "- SQL 影响类型：").strip()
    impact_type = SQL_IMPACT_TYPES.get(display_impact, "")
    if not impact_type:
        errors.append(
            "01-research.md SQL 影响类型必须为“不涉及 / 查询或DML / DDL”之一"
        )
    draft = extract_line_value(section, "- SQL 草案：").strip().strip("`")
    status = extract_line_value(section, "- SQL 确认状态：").strip()
    source = extract_line_value(section, "- SQL 确认来源：").strip()
    semantic_fingerprint = extract_line_value(section, "- SQL 语义指纹：").strip()
    if status not in {"待确认", "已确认"}:
        errors.append("01-research.md SQL 确认状态必须为“待确认”或“已确认”")

    required_headers = [
        "SQL ID",
        "类型",
        "表/对象",
        "JOIN/关联",
        "过滤/权限条件",
        "排序/分页",
        "写入字段",
        "更新条件/影响行数",
        "并发/兼容边界",
        "来源Cxx",
        "证据ID",
    ]
    headers, rows = find_table(section, required_headers)
    if not headers:
        errors.append("01-research.md SQL 影响表缺少固定表头")
        return {
            "impact_type": impact_type,
            "draft": draft,
            "status": status,
            "source": source,
            "semantic_fingerprint": semantic_fingerprint,
            "rows": {},
        }
    actual_rows: dict[str, dict[str, str]] = {}
    for row in actual_table_rows(headers, rows, "SQL ID"):
        sql_id = table_cell(headers, row, "SQL ID")
        sql_type = table_cell(headers, row, "类型").upper()
        if not re.fullmatch(r"SQL\d+", sql_id or ""):
            errors.append(f"01-research.md SQL 影响表包含非法 SQL ID: {sql_id or '空'}")
            continue
        if sql_id in actual_rows:
            errors.append(f"01-research.md SQL ID 重复: {sql_id}")
            continue
        if sql_type not in SQL_DRAFT_TYPES | {"不涉及"}:
            errors.append(f"01-research.md {sql_id} 类型非法: {sql_type or '空'}")
        claims = claim_refs(table_cell(headers, row, "来源Cxx"))
        evidence = evidence_refs(table_cell(headers, row, "证据ID"))
        if not claims:
            errors.append(f"01-research.md {sql_id} 缺少 Cxx 来源")
        if not evidence:
            errors.append(f"01-research.md {sql_id} 缺少 Exx 证据")
        assert_claim_refs_exist(
            f"01-research.md {sql_id}",
            claims,
            valid_claim_ids,
            errors,
        )
        object_value = table_cell(headers, row, "表/对象")
        if not meaningful_design_value(object_value):
            errors.append(f"01-research.md {sql_id} 缺少表或对象")
        actual_rows[sql_id] = {
            header: table_cell(headers, row, header)
            for header in required_headers
        }

    if impact_type == "none":
        if len(actual_rows) != 1 or any(
            row["类型"] != "不涉及" for row in actual_rows.values()
        ):
            errors.append("01-research.md SQL 不涉及时必须且只能保留一条“不涉及”SQL 行")
        if not draft.startswith("不涉及：") or len(draft) <= len("不涉及："):
            errors.append("01-research.md SQL 不涉及时必须在 SQL 草案写“不涉及：具体原因”")
    elif impact_type in {"query_dml", "ddl"}:
        if draft != "sql-draft.sql":
            errors.append("01-research.md 涉及 SQL 时 SQL 草案必须填写 `sql-draft.sql`")
        if not actual_rows:
            errors.append("01-research.md 涉及 SQL 时 SQL 影响表必须包含真实 SQL 行")
        if any(row["类型"] == "不涉及" for row in actual_rows.values()):
            errors.append("01-research.md 涉及 SQL 时不能保留“不涉及”SQL 行")
        if impact_type == "query_dml" and any(
            row["类型"] == "DDL" for row in actual_rows.values()
        ):
            errors.append("01-research.md 查询或DML 类型不能包含 DDL 行")
        if impact_type == "ddl" and not any(
            row["类型"] == "DDL" for row in actual_rows.values()
        ):
            errors.append("01-research.md DDL 类型至少需要一条 DDL 行")

    if status == "已确认":
        if not meaningful_design_value(source):
            errors.append("01-research.md SQL 已确认但缺少确认来源")
        if not re.fullmatch(r"[0-9a-f]{64}", semantic_fingerprint):
            errors.append("01-research.md SQL 已确认但缺少合法 64 位语义指纹")
    return {
        "impact_type": impact_type,
        "draft": draft,
        "status": status,
        "source": source,
        "semantic_fingerprint": semantic_fingerprint,
        "rows": actual_rows,
    }


def validate_sql_draft_doc(
    path: Path,
    valid_claim_ids: set[str] | None = None,
    expected_rows: dict[str, dict[str, str]] | None = None,
    expected_impact_type: str | None = None,
) -> list[str]:
    errors: list[str] = []
    text = read_text(path)
    if not text:
        return [f"缺少 {path.name}"]
    if sql_draft_version(text) != 1:
        errors.append("sql-draft.sql 缺少或使用不支持的 GGG_SQL_DRAFT_VERSION")
    assert_no_unresolved_placeholders(text, path.name, errors)
    entries = extract_sql_draft_entries(text, errors)
    if not entries:
        errors.append("sql-draft.sql 未登记任何 GGG_SQL 语句")
    entry_map = {str(entry["id"]): entry for entry in entries if entry["id"]}
    expected_rows = expected_rows or {}
    if expected_rows:
        for missing in sorted(set(expected_rows) - set(entry_map)):
            errors.append(f"sql-draft.sql 缺少 01-research.md 中的 SQL: {missing}")
        for extra in sorted(set(entry_map) - set(expected_rows)):
            errors.append(f"sql-draft.sql 包含 01-research.md 未登记的 SQL: {extra}")
    for sql_id, entry in entry_map.items():
        claims = set(entry["claims"])
        assert_claim_refs_exist(f"sql-draft.sql {sql_id}", claims, valid_claim_ids, errors)
        expected = expected_rows.get(sql_id)
        if expected and entry["type"] != expected["类型"].upper():
            errors.append(
                f"sql-draft.sql {sql_id} 类型与 01-research.md 不一致:"
                f" draft={entry['type']} research={expected['类型']}"
            )
    if expected_impact_type == "query_dml" and any(
        entry["type"] == "DDL" for entry in entries
    ):
        errors.append("sql-draft.sql 查询或DML Gate 不能包含 DDL")
    if expected_impact_type == "ddl" and not any(
        entry["type"] == "DDL" for entry in entries
    ):
        errors.append("sql-draft.sql DDL Gate 至少需要一条 DDL")
    return errors


def validate_sql_gate_binding(
    feature_dir: Path,
    meta: dict,
    research_text: str,
    valid_claim_ids: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    snapshot = research_sql_gate_snapshot(research_text, errors, valid_claim_ids)
    gates = meta.get("gates", {})
    confirmation = meta.get("sql_confirmation", {})
    if not gates.get("sql_confirmed"):
        errors.append("SQL Gate 尚未完成用户确认，不能进入技术方案")
        return errors
    if snapshot["status"] != "已确认":
        errors.append("meta.json 已标记 SQL 确认，但 01-research.md SQL 确认状态不是已确认")
    impact_type = str(snapshot["impact_type"])
    if confirmation.get("impact_type") != impact_type:
        errors.append("meta.json SQL impact_type 与 01-research.md 不一致")
    current_research_fingerprint = research_sql_semantic_fingerprint(research_text)
    confirmed_research_fingerprint = str(
        confirmation.get("research_semantic_fingerprint", "")
    )
    if confirmed_research_fingerprint != current_research_fingerprint:
        errors.append("01-research.md SQL 语义在用户确认后发生变化，必须重新执行 confirm-sql")
    if confirmation.get("confirmation_source") != snapshot["source"]:
        errors.append("meta.json SQL 确认来源与 01-research.md 不一致")

    draft_path = feature_dir / "sql-draft.sql"
    if impact_type == "none":
        if draft_path.exists():
            errors.append("SQL Gate 为 none 时不应创建 sql-draft.sql")
        current_draft_fingerprint = ""
    else:
        errors.extend(
            validate_sql_draft_doc(
                draft_path,
                valid_claim_ids,
                snapshot["rows"],  # type: ignore[arg-type]
                impact_type,
            )
        )
        current_draft_fingerprint = sql_draft_semantic_fingerprint(read_text(draft_path))
        if not current_draft_fingerprint:
            errors.append("sql-draft.sql 无法生成有效语义指纹")
    if str(confirmation.get("draft_semantic_fingerprint", "")) != current_draft_fingerprint:
        errors.append("sql-draft.sql 语义在用户确认后发生变化，必须重新执行 confirm-sql")
    combined = hashlib.sha256(
        f"{impact_type}\n{current_research_fingerprint}\n{current_draft_fingerprint}\n".encode(
            "utf-8"
        )
    ).hexdigest()
    if snapshot["semantic_fingerprint"] != combined:
        errors.append("01-research.md SQL 语义指纹与当前 SQL Gate 不一致")
    if confirmation.get("semantic_fingerprint") != combined:
        errors.append("meta.json SQL 语义指纹与当前 SQL Gate 不一致")
    return errors


def validate_design_sql_gate_binding(
    design_text: str,
    research_text: str,
    meta: dict,
) -> list[str]:
    """确保 Design v6 只引用当前已锁定的 SQL Gate，而不是重新设计 SQL。"""
    errors: list[str] = []
    confirmation = meta.get("sql_confirmation", {})
    expected_impact = str(confirmation.get("impact_type", ""))
    actual_impact = SQL_IMPACT_TYPES.get(
        extract_line_value(design_text, "- SQL 影响类型：").strip(),
        "",
    )
    if actual_impact != expected_impact:
        errors.append("02-design.md SQL 影响类型与已确认 SQL Gate 不一致")
    if (
        extract_line_value(design_text, "- SQL 确认来源：").strip()
        != str(confirmation.get("confirmation_source", ""))
    ):
        errors.append("02-design.md SQL 确认来源与已确认 SQL Gate 不一致")
    if (
        extract_line_value(design_text, "- SQL 语义指纹：").strip()
        != str(confirmation.get("semantic_fingerprint", ""))
    ):
        errors.append("02-design.md SQL 语义指纹与已确认 SQL Gate 不一致")

    if expected_impact == "none":
        return errors
    snapshot_errors: list[str] = []
    snapshot = research_sql_gate_snapshot(research_text, snapshot_errors)
    errors.extend(snapshot_errors)
    expected_rows = snapshot["rows"]
    if not isinstance(expected_rows, dict):
        return errors
    section = extract_section(design_text, "## 五、已确认 SQL 引用")
    headers, rows = find_table(
        section,
        ["SQL ID/对象", "SQL 类型"],
    )
    design_rows: dict[str, str] = {}
    for row in actual_table_rows(headers, rows, "SQL ID/对象"):
        key = table_cell(headers, row, "SQL ID/对象")
        if key.startswith("不涉及："):
            continue
        sql_ids = re.findall(r"\bSQL\d+\b", key)
        for sql_id in sql_ids:
            design_rows[sql_id] = table_cell(headers, row, "SQL 类型").upper()
    if set(design_rows) != set(expected_rows):
        errors.append(
            "02-design.md 已确认 SQL 引用与 01-research.md 不一致:"
            f" design={sorted(design_rows)} research={sorted(expected_rows)}"
        )
    for sql_id in sorted(set(design_rows) & set(expected_rows)):
        expected_type = str(expected_rows[sql_id].get("类型", "")).upper()
        if design_rows[sql_id] != expected_type:
            errors.append(
                f"02-design.md {sql_id} 类型与 01-research.md 不一致:"
                f" design={design_rows[sql_id]} research={expected_type}"
            )
    return errors


DDL_MARKER_PATTERN = re.compile(
    r"(?m)^[ \t]*--[ \t]*GGG_DDL_OBJECT:[ \t]*(\{.*\})[ \t]*$"
)
DDL_START_PATTERN = re.compile(
    r"(?i)\b(?:CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE|TRUNCATE\s+TABLE|RENAME\s+TABLE)\b"
)
DDL_OBJECT_PATTERN = (
    r"(?:`[^`]+`|[A-Za-z_][A-Za-z0-9_$]*)"
    r"(?:\s*\.\s*(?:`[^`]+`|[A-Za-z_][A-Za-z0-9_$]*))?"
)
DDL_OPERATIONS = {"create", "alter", "drop", "truncate", "rename"}
DDL_RISK_LEVELS = {"普通", "高风险"}
CONTRACT_TYPES = {"HTTP", "RPC", "MQ", "Job", "内部方法"}
MANIFEST_EMPTY_VALUES = {"", "-", "无", "不涉及", "无返回"}


def mask_sql_comments_and_literals(text: str) -> str:
    """保留长度和换行，只屏蔽 SQL 注释及字符串，避免把回滚说明或注释误识别为 DDL。"""
    result = list(text)
    index = 0
    state = "normal"
    quote = ""
    while index < len(text):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if state == "normal":
            if char == "-" and next_char == "-":
                state = "line_comment"
                result[index] = result[index + 1] = " "
                index += 2
                continue
            if char == "#":
                state = "line_comment"
                result[index] = " "
                index += 1
                continue
            if char == "/" and next_char == "*":
                state = "block_comment"
                result[index] = result[index + 1] = " "
                index += 2
                continue
            if char in {"'", '"'}:
                state = "string"
                quote = char
                result[index] = " "
                index += 1
                continue
            index += 1
            continue
        if state == "line_comment":
            if char in {"\n", "\r"}:
                state = "normal"
            else:
                result[index] = " "
            index += 1
            continue
        if state == "block_comment":
            if char == "*" and next_char == "/":
                result[index] = result[index + 1] = " "
                index += 2
                state = "normal"
                continue
            if char not in {"\n", "\r"}:
                result[index] = " "
            index += 1
            continue
        if state == "string":
            result[index] = " "
            if char == "\\" and next_char:
                if next_char not in {"\n", "\r"}:
                    result[index + 1] = " "
                index += 2
                continue
            if char == quote:
                if next_char == quote:
                    result[index + 1] = " "
                    index += 2
                    continue
                state = "normal"
            index += 1
    return "".join(result)


def split_sql_top_level(value: str) -> list[str]:
    """按括号外逗号切分字段或 ALTER 子句。"""
    parts: list[str] = []
    start = 0
    depth = 0
    quote = ""
    index = 0
    while index < len(value):
        char = value[index]
        if quote:
            if char == quote:
                quote = ""
            index += 1
            continue
        if char == "`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1
        index += 1
    parts.append(value[start:].strip())
    return [part for part in parts if part]


def normalize_sql_object(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().strip("`")).replace("`", "")


def normalize_ddl_member(value: str) -> str:
    normalized = value.strip().strip("`")
    return re.sub(r"\s+", " ", normalized)


def ddl_statement_identity(masked_statement: str) -> tuple[str, str] | None:
    alter_rename = re.match(
        rf"(?is)^\s*ALTER\s+TABLE\s+({DDL_OBJECT_PATTERN})"
        rf"\s+RENAME\s+(?:TO|AS)\s+({DDL_OBJECT_PATTERN})",
        masked_statement,
    )
    if alter_rename:
        return (
            "rename",
            f"{normalize_sql_object(alter_rename.group(1))}->{normalize_sql_object(alter_rename.group(2))}",
        )
    for operation, pattern in [
        ("create", rf"(?is)^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?({DDL_OBJECT_PATTERN})"),
        ("alter", rf"(?is)^\s*ALTER\s+TABLE\s+({DDL_OBJECT_PATTERN})"),
        ("drop", rf"(?is)^\s*DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?({DDL_OBJECT_PATTERN})"),
        ("truncate", rf"(?is)^\s*TRUNCATE\s+TABLE\s+({DDL_OBJECT_PATTERN})"),
    ]:
        match = re.match(pattern, masked_statement)
        if match:
            return operation, normalize_sql_object(match.group(1))
    rename = re.match(
        rf"(?is)^\s*RENAME\s+TABLE\s+({DDL_OBJECT_PATTERN})\s+TO\s+({DDL_OBJECT_PATTERN})",
        masked_statement,
    )
    if rename:
        return "rename", f"{normalize_sql_object(rename.group(1))}->{normalize_sql_object(rename.group(2))}"
    return None


def ddl_statement_has_multiple_objects(masked_statement: str, operation: str) -> bool:
    if operation == "drop":
        match = re.match(
            rf"(?is)^\s*DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?{DDL_OBJECT_PATTERN}",
            masked_statement,
        )
        return bool(match and re.match(r"\s*,", masked_statement[match.end():]))
    if operation == "rename":
        match = re.match(
            rf"(?is)^\s*RENAME\s+TABLE\s+{DDL_OBJECT_PATTERN}\s+TO\s+{DDL_OBJECT_PATTERN}",
            masked_statement,
        )
        return bool(match and re.match(r"\s*,", masked_statement[match.end():]))
    return False


def ddl_statement_members(statement: str, masked_statement: str, operation: str) -> set[str]:
    if operation in {"drop", "truncate", "rename"}:
        return {"*"}
    if operation == "create":
        start = masked_statement.find("(")
        end = masked_statement.rfind(")")
        body = statement[start + 1:end] if start >= 0 and end > start else ""
    else:
        identity = re.match(rf"(?is)^\s*ALTER\s+TABLE\s+{DDL_OBJECT_PATTERN}", masked_statement)
        body = statement[identity.end():] if identity else ""

    members: set[str] = set()
    for clause in split_sql_top_level(body.rstrip().rstrip(";")):
        stripped = clause.strip()
        if re.match(r"(?is)^(?:ADD\s+|DROP\s+)?PRIMARY\s+KEY\b", stripped):
            members.add("PRIMARY KEY")
            continue
        if operation == "alter":
            renamed_key = re.match(
                r"(?is)^RENAME\s+(?:INDEX|KEY)\s+`?([A-Za-z0-9_$]+)`?"
                r"\s+TO\s+`?([A-Za-z0-9_$]+)`?",
                stripped,
            )
            if renamed_key:
                members.update(normalize_ddl_member(value) for value in renamed_key.groups())
                continue
            dropped_key = re.match(
                r"(?is)^DROP\s+(?:INDEX|KEY)\s+`?([A-Za-z0-9_$]+)`?",
                stripped,
            )
            if dropped_key:
                members.add(normalize_ddl_member(dropped_key.group(1)))
                continue
            dropped_foreign_key = re.match(
                r"(?is)^DROP\s+(?:FOREIGN\s+KEY|CONSTRAINT)\s+`?([A-Za-z0-9_$]+)`?",
                stripped,
            )
            if dropped_foreign_key:
                members.add(normalize_ddl_member(dropped_foreign_key.group(1)))
                continue
        key_match = re.match(
            r"(?is)^(?:ADD\s+)?(?:UNIQUE\s+)?(?:KEY|INDEX)\s+`?([A-Za-z0-9_$]+)`?",
            stripped,
        )
        if key_match:
            members.add(normalize_ddl_member(key_match.group(1)))
            continue
        constraint_match = re.match(
            r"(?is)^(?:ADD\s+)?CONSTRAINT\s+`?([A-Za-z0-9_$]+)`?",
            stripped,
        )
        if constraint_match:
            members.add(normalize_ddl_member(constraint_match.group(1)))
            continue
        if operation == "alter":
            rename_column = re.match(
                r"(?is)^RENAME\s+(?:COLUMN\s+)?`?([A-Za-z0-9_$]+)`?"
                r"\s+TO\s+`?([A-Za-z0-9_$]+)`?",
                stripped,
            )
            if rename_column:
                members.update(normalize_ddl_member(value) for value in rename_column.groups())
                continue
            column_match = re.match(
                r"(?is)^(?:ADD|MODIFY|DROP|RENAME)\s+(?:COLUMN\s+)?`?([A-Za-z0-9_$]+)`?",
                stripped,
            )
            if column_match:
                members.add(normalize_ddl_member(column_match.group(1)))
                continue
            change_match = re.match(
                r"(?is)^CHANGE\s+(?:COLUMN\s+)?`?([A-Za-z0-9_$]+)`?\s+`?([A-Za-z0-9_$]+)`?",
                stripped,
            )
            if change_match:
                members.update(normalize_ddl_member(value) for value in change_match.groups())
                continue
            if re.match(r"(?is)^(?:ALGORITHM|LOCK)\s*=", stripped):
                continue
            members.add("*")
            continue
        field_match = re.match(r"(?is)^`?([A-Za-z_][A-Za-z0-9_$]*)`?\s+[A-Za-z]", stripped)
        if field_match:
            members.add(normalize_ddl_member(field_match.group(1)))
    return members


def ordinary_alter_candidate(masked_statement: str, risk_reason: str) -> bool:
    identity = re.match(rf"(?is)^\s*ALTER\s+TABLE\s+{DDL_OBJECT_PATTERN}", masked_statement)
    if not identity or re.search(r"未知|不清楚|待确认|未确认", risk_reason):
        return False
    body = masked_statement[identity.end():].rstrip().rstrip(";")
    clauses = split_sql_top_level(body)
    if not clauses:
        return False
    for clause in clauses:
        stripped = clause.strip()
        if re.match(r"(?is)^(?:ALGORITHM|LOCK)\s*=", stripped):
            continue
        if re.match(r"(?is)^ADD\s+(?:INDEX|KEY)\s+`?[A-Za-z0-9_$]+`?\s*\(", stripped):
            continue
        if re.match(r"(?is)^ADD\s+(?:COLUMN\s+)?`?[A-Za-z0-9_$]+`?\s+", stripped):
            if not re.search(r"(?i)\bNULL\b", stripped) or re.search(r"(?i)\bNOT\s+NULL\b", stripped):
                return False
            default_match = re.search(r"(?i)\bDEFAULT\s+([^\s,]+)", stripped)
            if default_match and default_match.group(1).upper() != "NULL":
                return False
            if re.search(r"(?i)\b(?:UNIQUE|PRIMARY|REFERENCES)\b", stripped):
                return False
            continue
        return False
    return True


def ddl_risk_floor(operation: str, masked_statement: str, risk_reason: str) -> str:
    if operation == "create":
        return "普通"
    if operation == "alter" and ordinary_alter_candidate(masked_statement, risk_reason):
        return "普通"
    return "高风险"


def ddl_marker_list(value: object, pattern: str, label: str, errors: list[str]) -> set[str]:
    if not isinstance(value, list) or not value:
        errors.append(f"04-schema.sql DDL 对象元数据 {label} 必须是非空数组")
        return set()
    result: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not re.fullmatch(pattern, item.strip()):
            errors.append(f"04-schema.sql DDL 对象元数据 {label} 包含非法值: {item}")
            continue
        result.add(item.strip())
    if len(result) != len(value):
        errors.append(f"04-schema.sql DDL 对象元数据 {label} 包含重复值")
    return result


def extract_sql_v3_ddl_entries(text: str, errors: list[str]) -> list[dict[str, object]]:
    """解析 SQL v3 的逐语句对象元数据，并与真实 DDL target/member 闭环。"""
    markers: list[dict[str, object]] = []
    for match in DDL_MARKER_PATTERN.finditer(text):
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            errors.append(f"04-schema.sql GGG_DDL_OBJECT JSON 无法解析: {exc.msg}")
            payload = {}
        if not isinstance(payload, dict):
            errors.append("04-schema.sql GGG_DDL_OBJECT 必须是 JSON 对象")
            payload = {}
        markers.append({"start": match.start(), "end": match.end(), "payload": payload, "used": False})

    masked = mask_sql_comments_and_literals(text)
    entries: list[dict[str, object]] = []
    cursor = 0
    previous_end = 0
    while True:
        start_match = DDL_START_PATTERN.search(masked, cursor)
        if not start_match:
            break
        start = start_match.start()
        end = masked.find(";", start)
        if end < 0:
            errors.append("04-schema.sql 结构 DDL 缺少结束分号")
            end = len(masked) - 1
        statement = text[start:end + 1]
        masked_statement = masked[start:end + 1]
        candidates = [
            marker for marker in markers
            if not marker["used"] and previous_end <= int(marker["start"]) < start
        ]
        if len(candidates) != 1:
            errors.append("04-schema.sql 每条结构 DDL 前必须且只能有一条 GGG_DDL_OBJECT")
            marker = candidates[-1] if candidates else None
        else:
            marker = candidates[0]
        if marker:
            marker["used"] = True
        identity = ddl_statement_identity(masked_statement)
        if not identity:
            errors.append("04-schema.sql 存在无法识别对象或操作的结构 DDL")
            cursor = end + 1
            previous_end = end + 1
            continue
        actual_operation, actual_object = identity
        if ddl_statement_has_multiple_objects(masked_statement, actual_operation):
            errors.append(
                "04-schema.sql 单条 DROP/RENAME TABLE 只能包含一个对象；多对象必须拆成独立 DDL 并逐条标注"
            )
        actual_members = ddl_statement_members(statement, masked_statement, actual_operation)
        if not actual_members:
            errors.append(f"04-schema.sql DDL 对象 {actual_object} 未解析到字段、索引或约束覆盖")

        payload = marker["payload"] if marker else {}
        raw_object = str(payload.get("object", "")).strip() if isinstance(payload, dict) else ""
        raw_operation = str(payload.get("operation", "")).strip().lower() if isinstance(payload, dict) else ""
        raw_risk = str(payload.get("risk", "")).strip() if isinstance(payload, dict) else ""
        risk_reason = str(payload.get("risk_reason", "")).strip() if isinstance(payload, dict) else ""
        marker_object = normalize_sql_object(raw_object)
        if not marker_object:
            errors.append("04-schema.sql DDL 对象元数据缺少 object")
        elif marker_object != actual_object:
            errors.append(
                f"04-schema.sql DDL 对象元数据 object={marker_object} 与真实对象 {actual_object} 不一致"
            )
        if raw_operation not in DDL_OPERATIONS:
            errors.append(f"04-schema.sql DDL 对象 {actual_object} operation 非法或缺失: {raw_operation}")
        elif raw_operation != actual_operation:
            errors.append(
                f"04-schema.sql DDL 对象 {actual_object} operation={raw_operation} 与真实操作 {actual_operation} 不一致"
            )
        raw_members = payload.get("members", []) if isinstance(payload, dict) else []
        if not isinstance(raw_members, list) or not raw_members:
            errors.append(f"04-schema.sql DDL 对象 {actual_object} members 必须是非空数组")
            marker_members: set[str] = set()
        else:
            marker_members = {
                normalize_ddl_member(str(value))
                for value in raw_members
                if isinstance(value, str) and normalize_ddl_member(value)
            }
            if len(marker_members) != len(raw_members):
                errors.append(f"04-schema.sql DDL 对象 {actual_object} members 包含空值、非字符串或重复值")
        if marker_members != actual_members:
            errors.append(
                f"04-schema.sql DDL 对象 {actual_object} members 与真实 DDL 不一致:"
                f" 元数据={sorted(marker_members)}，真实={sorted(actual_members)}"
            )
        if raw_risk not in DDL_RISK_LEVELS:
            errors.append(f"04-schema.sql DDL 对象 {actual_object} risk 必须为普通或高风险")
        if not risk_reason or vague_design_value(risk_reason):
            errors.append(f"04-schema.sql DDL 对象 {actual_object} 缺少具体 risk_reason")
        floor = ddl_risk_floor(actual_operation, masked_statement, risk_reason)
        if raw_risk == "普通" and floor == "高风险":
            errors.append(f"04-schema.sql DDL 对象 {actual_object} 的语法风险下限为高风险，不能声明普通")
        claims = ddl_marker_list(
            payload.get("claims") if isinstance(payload, dict) else None,
            r"C\d+",
            "claims",
            errors,
        )
        designs = ddl_marker_list(
            payload.get("designs") if isinstance(payload, dict) else None,
            r"D\d+",
            "designs",
            errors,
        )
        entries.append({
            "object": actual_object,
            "operation": actual_operation,
            "members": actual_members,
            "risk": "高风险" if floor == "高风险" or raw_risk == "高风险" else "普通",
            "risk_reason": risk_reason,
            "claims": claims,
            "designs": designs,
            "statement": statement,
        })
        cursor = end + 1
        previous_end = end + 1

    for marker in markers:
        if not marker["used"]:
            errors.append("04-schema.sql 存在未绑定结构 DDL 的孤立 GGG_DDL_OBJECT")
    return entries


def baseline_row_has_claim(headers: list[str], row: list[str]) -> bool:
    placeholder_values = {
        "",
        "-",
        "无",
        "是 / 否",
        "可直接复用 / 可扩展复用 / 只可参考 / 禁止复用 / 必须新增",
        "待确认 / 已确认 / 转下游",
        "用户 / 需求对齐 / 技术方案",
        "用户意图 / 代码事实 / 设计选择",
    }
    for header, value in zip(headers, row):
        if header in {"基线ID", "编号", "来源"}:
            continue
        if value.strip() not in placeholder_values:
            return True
    return False


def baseline_verification_sections(text: str) -> list[tuple[str, str]]:
    return [
        ("用户路径", extract_section(text, "## 4. 用户路径与前后端职责")),
        ("业务规则", extract_section(text, "## 5. 业务规则矩阵")),
        ("数据身份", extract_section(text, "## 6. 数据身份矩阵")),
        ("旧链路复用与隔离", extract_section(text, "## 7. 旧链路复用与隔离")),
        ("验收标准", extract_section(text, "## 8. 验收标准")),
    ]


def extract_baseline_verification_ids(text: str) -> list[str]:
    ids: list[str] = []
    for _label, section in baseline_verification_sections(text):
        headers, rows = extract_first_table(section)
        for row in rows:
            if not baseline_row_has_claim(headers, row):
                continue
            baseline_id = table_cell(headers, row, "基线ID")
            if re.fullmatch(r"B\d+", baseline_id or ""):
                ids.append(baseline_id)
    return ids


def assert_strict_baseline_ids(text: str, errors: list[str]) -> None:
    ids: list[str] = []
    for label, section in baseline_verification_sections(text):
        headers, rows = extract_first_table(section)
        if "基线ID" not in headers:
            errors.append(f"00-baseline.md {label}缺少基线ID列")
            continue
        for index, row in enumerate(rows, start=1):
            if not baseline_row_has_claim(headers, row):
                continue
            baseline_id = table_cell(headers, row, "基线ID")
            if not re.fullmatch(r"B\d+", baseline_id or ""):
                errors.append(f"00-baseline.md {label}第{index}条真实业务行缺少合法 Bxx 基线ID")
                continue
            ids.append(baseline_id)
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    for baseline_id in duplicates:
        errors.append(f"00-baseline.md 基线ID重复: {baseline_id}")


def assert_baseline_source_traceability(
    text: str,
    sections: list[tuple[str, str]],
    valid_material_ids: set[str],
    valid_question_ids: set[str],
    errors: list[str],
) -> None:
    for prefix in [
        "- 一句话目标：",
        "- 核心流程：",
        "- 输入对象：",
        "- 输出对象：",
        "- 使用角色：",
        "- 本期包含：",
        "- 本期不做：",
        "- 不做原因：",
    ]:
        value = extract_line_value(text, prefix)
        refs = baseline_material_refs(value) | baseline_source_refs(value)
        if value and not refs:
            errors.append(f"00-baseline.md {prefix.rstrip('：')} 缺少有效 Sxx/Qxx 来源")
        for ref in baseline_material_refs(value):
            if ref not in valid_material_ids:
                errors.append(f"00-baseline.md {prefix.rstrip('：')} 引用了不存在的原始材料编号: {ref}")
        for ref in baseline_source_refs(value):
            if ref not in valid_question_ids:
                errors.append(f"00-baseline.md {prefix.rstrip('：')} 引用了不存在的疑问编号: {ref}")

    for label, section in sections:
        headers, rows = extract_first_table(section)
        if "来源" not in headers:
            errors.append(f"00-baseline.md {label}缺少来源列")
            continue
        for index, row in enumerate(rows, start=1):
            if not baseline_row_has_claim(headers, row):
                continue
            source = table_cell(headers, row, "来源")
            row_label = table_cell(headers, row, "编号") or (row[0].strip() if row else "") or f"第{index}行"
            if not source or source in {"-", "无"}:
                errors.append(f"00-baseline.md {label}{row_label} 缺少准确来源")
                continue
            refs = baseline_material_refs(source) | baseline_source_refs(source)
            if not refs:
                errors.append(f"00-baseline.md {label}{row_label} 来源必须引用 Sxx 或 Qxx")
            for ref in baseline_material_refs(source):
                if ref not in valid_material_ids:
                    errors.append(f"00-baseline.md {label}{row_label} 引用了不存在的原始材料编号: {ref}")
            for ref in baseline_source_refs(source):
                if ref not in valid_question_ids:
                    errors.append(f"00-baseline.md {label}{row_label} 引用了不存在的疑问编号: {ref}")


def assert_baseline_has_substantive_rows(section: str, label: str, errors: list[str]) -> None:
    headers, rows = extract_first_table(section)
    if not any(baseline_row_has_claim(headers, row) for row in rows):
        errors.append(f"00-baseline.md {label}没有真实业务行，不能用空模板通过")


def evidence_refs(value: str) -> set[str]:
    return set(re.findall(r"\bE\d+\b", value))


def claim_refs(value: str) -> set[str]:
    return set(re.findall(r"\bC\d+\b", value))


def question_refs(value: str) -> set[str]:
    return set(re.findall(r"\bQ\d+\b", value))


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


def extract_table_id_list(section_text: str, id_pattern: str) -> list[str]:
    _headers, rows = extract_first_table(section_text)
    compiled = re.compile(id_pattern)
    return [row[0].strip() for row in rows if row and compiled.fullmatch(row[0].strip())]


def assert_unique_table_ids(section_text: str, id_pattern: str, label: str, errors: list[str]) -> None:
    ids = extract_table_id_list(section_text, id_pattern)
    for item in sorted({value for value in ids if ids.count(value) > 1}):
        errors.append(f"01-research.md {label}编号重复: {item}")


def extract_claim_ids_from_research(text: str) -> set[str]:
    heading = (
        "## 8. 结论账本（Claim Ledger）"
        if "## 8. 结论账本（Claim Ledger）" in text
        else "## 9. 结论账本（Claim Ledger）"
    )
    return extract_table_ids(extract_section(text, heading), r"C\d+")


def extract_design_eligible_claim_ids_from_research(text: str) -> set[str]:
    heading = (
        "## 8. 结论账本（Claim Ledger）"
        if "## 8. 结论账本（Claim Ledger）" in text
        else "## 9. 结论账本（Claim Ledger）"
    )
    headers, rows = extract_first_table(extract_section(text, heading))
    eligible: set[str] = set()
    for row in rows:
        claim_id = table_cell(headers, row, "结论ID")
        level = table_cell(headers, row, "证据等级")
        confidence = table_cell(headers, row, "置信度")
        uncovered = table_cell(headers, row, "未覆盖范围")
        runtime_gap = table_cell(headers, row, "运行时证据缺口")
        if (
            re.fullmatch(r"C\d+", claim_id or "")
            and level in {"代码已证实", "编译已证实", "接口已证实", "数据已证实"}
            and confidence == "高"
            and uncovered in EMPTY_VALUES
            and runtime_gap in EMPTY_VALUES
        ):
            eligible.add(claim_id)
    return eligible


def extract_transferred_design_question_ids_from_research(text: str) -> set[str]:
    heading = (
        "## 9. 进入技术方案前疑问账本"
        if "## 9. 进入技术方案前疑问账本" in text
        else "## 10. 进入技术方案前阻塞问题"
    )
    headers, rows = extract_first_table(extract_section(text, heading))
    result: set[str] = set()
    for row in rows:
        question_id = table_cell(headers, row, "编号")
        if (
            re.fullmatch(r"Q\d+", question_id or "")
            and table_cell(headers, row, "问题类型") == "设计选择"
            and table_cell(headers, row, "应由谁确认") == "技术方案"
            and table_cell(headers, row, "状态") == "转下游"
        ):
            result.add(question_id)
    return result


def extract_design_ids_from_design(text: str) -> set[str]:
    ids: set[str] = set()
    for headers, rows in iter_markdown_tables(text):
        for header in ["设计ID", "来源Dxx", "对应Dxx/章节", "对应Dxx/章节或原因"]:
            if header not in headers:
                continue
            for row in rows:
                ids.update(design_refs(table_cell(headers, row, header)))
    return ids


def extract_core_change_design_ids_from_design(text: str) -> set[str]:
    section = extract_section(text, "## 六、核心改动")
    headers, rows = extract_first_table(section)
    if "设计ID" not in headers:
        return set()
    result: set[str] = set()
    for row in rows:
        result.update(design_refs(table_cell(headers, row, "设计ID")))
    return result


EVIDENCE_LEVELS = {
    "代码已证实",
    "编译已证实",
    "接口已证实",
    "数据已证实",
    "推断",
    "未覆盖",
    "阻塞",
}

CLAIM_TYPES = {
    "主链路",
    "复用边界",
    "旧链路副作用",
    "数据身份",
    "共享语义影响",
    "跨项目依赖",
    "技术可行性",
}

CONFIDENCE_LEVELS = {"高", "中", "低"}
BASELINE_VERIFICATION_STATUSES = {"已验证", "部分验证", "未覆盖", "阻塞"}
RUNTIME_GAP_LEVELS = {
    "配置确认", "接口验证", "日志运行时确认", "测试数据确认", "用户口径确认", "无", "-", "不涉及",
}
EMPTY_VALUES = {"", "-", "无", "不涉及", "暂无", "无阻塞风险"}
UNRESOLVED_EMPTY_VALUES = EMPTY_VALUES | {"无需确认", "无须确认", "无需后续确认", "无须后续确认"}


def has_blocking_signal(value: str) -> bool:
    """识别明确阻塞语义，同时排除常见的非阻塞否定表达。"""
    normalized = value
    for pattern in [
        r"非阻塞",
        r"无阻塞",
        r"不会阻塞",
        r"不构成阻塞",
        r"不会构成阻塞",
        r"不是阻塞",
        r"未形成阻塞",
        r"未构成阻塞",
        r"不阻塞",
    ]:
        normalized = re.sub(pattern, "", normalized)
    return "阻塞" in normalized

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
    # Path 在 Windows 同样接受正斜杠；统一成正斜杠可避免在 POSIX 上把相对路径变成含反斜杠的文件名。
    normalized = raw_path.replace("\\", "/")
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


def assert_baseline_quality(
    text: str,
    errors: list[str],
    clarification_gate_required: bool | None = None,
) -> None:
    materials = extract_section(text, "### 1.1 原始材料覆盖")
    understanding = extract_section(text, "## 2. 需求理解")
    scope = extract_section(text, "## 3. 范围边界")
    user_path = extract_section(text, "## 4. 用户路径与前后端职责")
    business_rules = extract_section(text, "## 5. 业务规则矩阵")
    data_identity = extract_section(text, "## 6. 数据身份矩阵")
    old_chain = extract_section(text, "## 7. 旧链路复用与隔离")
    acceptance = extract_section(text, "## 8. 验收标准")
    clarifications = extract_section(text, "## 9. 疑问与确认记录")

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

    baseline_version = document_schema_version(text)
    if baseline_version >= 4:
        assert_strict_baseline_ids(text, errors)
    if baseline_version >= 5:
        recommended_mode = extract_line_value(text, "- 推荐模式：").strip()
        recommendation_reason = extract_line_value(text, "- 推荐依据：").strip()
        selected_mode = extract_line_value(text, "- 最终模式：").strip()
        selection_source = extract_line_value(text, "- 模式选择来源：").strip()
        if recommended_mode not in {"quick", "full"}:
            errors.append("00-baseline.md 推荐模式必须为 quick 或 full")
        if selected_mode != "full":
            errors.append("00-baseline.md full 基线的最终模式必须为 full")
        for value, label in [
            (recommendation_reason, "推荐依据"),
            (selection_source, "模式选择来源"),
        ]:
            if (
                not meaningful_design_value(value)
                or vague_design_value(value)
                or "{{" in value
                or value in {"用户消息", "用户选择", "AI决定", "已授权"}
                or any(token in value for token in ["待确认", "TODO", "TBD", "按需", "视情况"])
            ):
                errors.append(f"00-baseline.md {label}缺少可回查的实质内容")

    # 单文件校验默认根据文档字段识别新版门禁；目录校验以 meta.json 为权威开关。
    gate_enabled = clarification_gate_required if clarification_gate_required is not None else "- 基线状态：" in text
    if gate_enabled:
        if "- 基线状态：" not in text:
            errors.append("00-baseline.md 缺少强制字段：基线状态")
        if "- 最终反向确认：" not in text:
            errors.append("00-baseline.md 缺少强制字段：最终反向确认")
        baseline_status = extract_line_value(text, "- 基线状态：")
        final_confirmation = extract_line_value(text, "- 最终反向确认：")
        if baseline_status != "已确认":
            errors.append("00-baseline.md 基线状态必须为“已确认”后才能进入下一阶段")
        if not final_confirmation.startswith("已确认"):
            errors.append("00-baseline.md 缺少用户最终反向确认记录")
        if not extract_line_value(text, "- 主项目判断依据："):
            errors.append("00-baseline.md 已确认基线缺少主项目判断依据")
        if extract_line_value(text, "- 依赖项目：") and not extract_line_value(text, "- 依赖项目判断依据："):
            errors.append("00-baseline.md 已填写依赖项目但缺少判断依据")

        for prefix in [
            "- 一句话目标：",
            "- 核心流程：",
            "- 输入对象：",
            "- 输出对象：",
            "- 使用角色：",
            "- 本期包含：",
            "- 本期不做：",
            "- 不做原因：",
        ]:
            if not extract_line_value(text, prefix):
                errors.append(f"00-baseline.md 已确认基线缺少实质内容: {prefix.rstrip('：')}")

        assert_table_has_headers(
            materials,
            ["来源ID", "类型", "原始材料定位", "原始要点", "处理结果", "对应基线或疑问"],
            "00-baseline.md 原始材料覆盖表缺少关键表头",
            errors,
        )
        material_headers, material_rows = extract_first_table(materials)
        valid_material_ids: set[str] = set()
        complete_material_count = 0
        for row in material_rows:
            material_id = table_cell(material_headers, row, "来源ID")
            if not re.fullmatch(r"S\d+", material_id or ""):
                continue
            valid_material_ids.add(material_id)
            location = table_cell(material_headers, row, "原始材料定位")
            point = table_cell(material_headers, row, "原始要点")
            result = table_cell(material_headers, row, "处理结果")
            mapping = table_cell(material_headers, row, "对应基线或疑问")
            if result not in {"形成基线", "形成疑问", "明确不适用"}:
                errors.append(f"00-baseline.md {material_id} 原始材料处理结果非法或未收口: {result}")
            if not location or not point or not mapping:
                errors.append(f"00-baseline.md {material_id} 原始材料覆盖记录不完整")
            else:
                complete_material_count += 1
        if complete_material_count == 0:
            errors.append("00-baseline.md 原始材料覆盖表没有已填写的 Sxx 记录")

        for label, section in baseline_verification_sections(text):
            assert_baseline_has_substantive_rows(section, label, errors)

        assert_table_has_headers(
            clarifications,
            ["编号", "疑问", "问题类型", "准确来源", "应由谁确认", "确认结论/转交说明", "状态"],
            "00-baseline.md 疑问账本缺少关键表头: 编号、疑问、问题类型、准确来源、应由谁确认、确认结论/转交说明、状态",
            errors,
        )
        headers, rows = extract_first_table(clarifications)
        valid_question_ids = {
            table_cell(headers, row, "编号")
            for row in rows
            if re.fullmatch(r"Q\d+", table_cell(headers, row, "编号") or "")
        }
        for row in rows:
            question_id = table_cell(headers, row, "编号")
            if not re.fullmatch(r"Q\d+", question_id or ""):
                continue
            status = table_cell(headers, row, "状态")
            question_type = table_cell(headers, row, "问题类型")
            source = table_cell(headers, row, "准确来源")
            owner = table_cell(headers, row, "应由谁确认")
            conclusion = table_cell(headers, row, "确认结论/转交说明")
            if status not in {"已确认", "转下游"}:
                errors.append(f"00-baseline.md {question_id} 疑问状态未清零: {status}")
            if question_type not in {"用户意图", "代码事实", "设计选择"}:
                errors.append(f"00-baseline.md {question_id} 问题类型非法或缺失: {question_type}")
            if not source or source in {"-", "无"}:
                errors.append(f"00-baseline.md {question_id} 缺少准确来源")
            else:
                source_refs = baseline_material_refs(source)
                if not source_refs:
                    errors.append(f"00-baseline.md {question_id} 准确来源必须引用 Sxx")
                for ref in source_refs:
                    if ref not in valid_material_ids:
                        errors.append(f"00-baseline.md {question_id} 引用了不存在的原始材料编号: {ref}")
            if not conclusion or conclusion in {"-", "无"}:
                errors.append(f"00-baseline.md {question_id} 缺少确认结论或转交说明")
            if question_type == "用户意图" and status == "转下游":
                errors.append(f"00-baseline.md {question_id} 用户意图问题不得转下游")
            if question_type == "用户意图" and owner != "用户":
                errors.append(f"00-baseline.md {question_id} 用户意图问题必须由用户确认")
            if status == "转下游":
                expected_owner = "需求对齐" if question_type == "代码事实" else "技术方案" if question_type == "设计选择" else ""
                if owner != expected_owner:
                    errors.append(
                        f"00-baseline.md {question_id} 转下游承接阶段不匹配: {question_type} 应交给 {expected_owner or '用户确认'}"
                    )

        assert_baseline_source_traceability(
            text,
            [
                ("用户路径", user_path),
                ("业务规则", business_rules),
                ("数据身份", data_identity),
                ("旧链路复用与隔离", old_chain),
                ("验收标准", acceptance),
            ],
            valid_material_ids,
            valid_question_ids,
            errors,
        )


def assert_research_evidence_quality(
    baseline_check: str,
    claim_ledger: str,
    question_ledger: str,
    evidence: str,
    errors: list[str],
    repo_root: Path | None = None,
    legacy_coverage: str = "",
    strict: bool = False,
) -> None:
    evidence_ids = extract_table_ids(evidence, r"E\d+")
    claim_ids = extract_table_ids(claim_ledger, r"C\d+")
    question_ids = extract_table_ids(question_ledger, r"Q\d+")
    if not evidence_ids:
        errors.append("01-research.md 代码证据索引缺少可追溯的 E1/E2 证据行")
    if not claim_ids:
        errors.append("01-research.md 结论账本缺少可追溯的 C1/C2 结论行")

    ledger_headers, ledger_rows = extract_first_table(claim_ledger)
    claim_records = {
        table_cell(ledger_headers, row, "结论ID"): {
            "level": table_cell(ledger_headers, row, "证据等级"),
            "confidence": table_cell(ledger_headers, row, "置信度"),
            "uncovered": table_cell(ledger_headers, row, "未覆盖范围"),
            "runtime_gap": table_cell(ledger_headers, row, "运行时证据缺口"),
            "follow_up": table_cell(ledger_headers, row, "后续确认方式"),
        }
        for row in ledger_rows
        if re.fullmatch(r"C\d+", table_cell(ledger_headers, row, "结论ID") or "")
    }

    baseline_headers, baseline_rows = extract_first_table(baseline_check)
    for row in baseline_rows:
        item = table_cell(baseline_headers, row, "baseline 条目") or "未命名条目"
        status = table_cell(baseline_headers, row, "验证状态")
        evidence_value = table_cell(baseline_headers, row, "证据ID")
        claim_value = table_cell(baseline_headers, row, "结论ID")
        code_fact = table_cell(baseline_headers, row, "代码事实")
        conclusion = table_cell(baseline_headers, row, "结论")
        risk = table_cell(baseline_headers, row, "风险")
        evidence_ids_in_row = evidence_refs(evidence_value)
        claim_ids_in_row = claim_refs(claim_value)
        if status not in BASELINE_VERIFICATION_STATUSES:
            errors.append(f"01-research.md Baseline 验证清单中“{item}”验证状态不合法: {status}")
        if status == "已验证" and not evidence_ids_in_row:
            errors.append(f"01-research.md Baseline 验证清单中“{item}”标为已验证但缺少 Exx 证据ID")
        for ref in evidence_ids_in_row:
            if ref not in evidence_ids:
                errors.append(f"01-research.md Baseline 验证清单中“{item}”引用了不存在的证据ID: {ref}")
        if "结论ID" in baseline_headers:
            if not claim_ids_in_row:
                errors.append(f"01-research.md Baseline 验证清单中“{item}”缺少 Cxx 结论引用")
            for ref in claim_ids_in_row:
                if ref not in claim_ids:
                    errors.append(f"01-research.md Baseline 验证清单中“{item}”引用了不存在的结论ID: {ref}")
        if strict and status == "已验证":
            for ref in claim_ids_in_row:
                record = claim_records.get(ref)
                if record and (
                    record["level"] in {"推断", "未覆盖", "阻塞"}
                    or record["confidence"] != "高"
                    or record["uncovered"] not in EMPTY_VALUES
                    or record["runtime_gap"] not in EMPTY_VALUES
                ):
                    errors.append(f"01-research.md Baseline 验证清单中“{item}”标为已验证，但 {ref} 仍存在未闭合缺口")
        if strict and status in {"部分验证", "未覆盖"} and risk in EMPTY_VALUES:
            errors.append(f"01-research.md Baseline 验证清单中“{item}”为{status}时必须写清风险")
        if strict and status == "部分验证":
            has_gap = any(
                record
                and (
                    record["level"] in {"推断", "未覆盖"}
                    or record["uncovered"] not in EMPTY_VALUES
                    or record["runtime_gap"] not in EMPTY_VALUES
                )
                for ref in claim_ids_in_row
                for record in [claim_records.get(ref)]
            )
            if not has_gap:
                errors.append(f"01-research.md Baseline 验证清单中“{item}”为部分验证，但关联 Cxx 没有记录对应缺口")
        if strict and status == "未覆盖":
            for ref in claim_ids_in_row:
                record = claim_records.get(ref)
                if record and record["level"] not in {"推断", "未覆盖", "阻塞"}:
                    errors.append(f"01-research.md Baseline 验证清单中“{item}”为未覆盖，但 {ref} 被写成已证实结论")
        if has_blocking_signal(f"{code_fact} {conclusion} {risk}") and status != "阻塞":
            errors.append(f"01-research.md Baseline 验证清单中“{item}”正文存在阻塞语义但验证状态不是阻塞")
            errors.append(f"01-research.md Baseline 验证清单中“{item}”仍存在阻塞语义，不能完成需求对齐")
        if status == "阻塞":
            refs = question_refs(f"{conclusion} {risk}")
            if not refs:
                errors.append(f"01-research.md Baseline 验证清单中“{item}”标为阻塞时必须在结论或风险中引用 Qxx")
            for ref in refs:
                if ref not in question_ids:
                    errors.append(f"01-research.md Baseline 验证清单中“{item}”引用了不存在的疑问编号: {ref}")
            errors.append(f"01-research.md Baseline 验证清单中“{item}”仍为阻塞，不能完成需求对齐")

    # 兼容旧版 research；新版只在 Claim Ledger 维护证据等级和置信度。
    if legacy_coverage:
        coverage_headers, coverage_rows = extract_first_table(legacy_coverage)
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

    for row in ledger_rows:
        claim_id = table_cell(ledger_headers, row, "结论ID")
        if not re.fullmatch(r"C\d+", claim_id or ""):
            continue
        claim_text = table_cell(ledger_headers, row, "关键结论")
        claim_type = table_cell(ledger_headers, row, "结论类型")
        evidence_value = table_cell(ledger_headers, row, "证据ID")
        level = table_cell(ledger_headers, row, "证据等级")
        confidence = table_cell(ledger_headers, row, "置信度")
        uncovered = table_cell(ledger_headers, row, "未覆盖范围")
        runtime_gap = table_cell(ledger_headers, row, "运行时证据缺口")
        impact = table_cell(ledger_headers, row, "若结论错误的影响")
        follow_up = table_cell(ledger_headers, row, "后续确认方式")
        refs = evidence_refs(evidence_value)

        if not claim_text or claim_text in {"-", "无"}:
            errors.append(f"01-research.md {claim_id} 缺少关键结论文本")
        if claim_type not in CLAIM_TYPES:
            errors.append(f"01-research.md {claim_id} 结论类型不合法或缺失: {claim_type}")
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
        if level in {"推断", "未覆盖", "阻塞"} and (
            uncovered in UNRESOLVED_EMPTY_VALUES or follow_up in UNRESOLVED_EMPTY_VALUES
        ):
            errors.append(f"01-research.md {claim_id} 为“{level}”时必须写清未覆盖范围和后续确认方式")
        if has_blocking_signal(f"{claim_text} {uncovered} {impact} {follow_up}") and level != "阻塞":
            errors.append(f"01-research.md {claim_id} 正文存在阻塞语义但证据等级不是阻塞")
            errors.append(f"01-research.md {claim_id} 仍存在阻塞语义，不能完成需求对齐")
        if "运行时证据缺口" in ledger_headers and runtime_gap not in RUNTIME_GAP_LEVELS:
            errors.append(f"01-research.md {claim_id} 运行时证据缺口不合法: {runtime_gap}")
        if "运行时证据缺口" in ledger_headers and confidence == "高" and (
            uncovered not in EMPTY_VALUES or runtime_gap not in EMPTY_VALUES
        ):
            errors.append(f"01-research.md {claim_id} 存在未覆盖范围或运行时证据缺口时不能标为高置信")
        if level == "阻塞":
            refs = question_refs(f"{uncovered} {follow_up}")
            if not refs:
                errors.append(f"01-research.md {claim_id} 标为阻塞时必须在未覆盖范围或后续确认方式中引用 Qxx")
            for ref in refs:
                if ref not in question_ids:
                    errors.append(f"01-research.md {claim_id} 引用了不存在的疑问编号: {ref}")
            errors.append(f"01-research.md {claim_id} 证据等级仍为阻塞，不能完成需求对齐")

    if repo_root is not None:
        assert_file_evidence_locations(evidence, repo_root, errors)


def assert_research_detail_claim_refs(
    section: str,
    label: str,
    key_header: str,
    valid_claim_ids: set[str],
    errors: list[str],
) -> None:
    headers, rows = extract_first_table(section)
    if "结论ID" not in headers:
        errors.append(f"01-research.md {label}缺少结论ID表头，明细事实必须回链唯一 Claim Ledger")
        return
    for index, row in enumerate(rows, start=1):
        key = table_cell(headers, row, key_header)
        if key in EMPTY_VALUES:
            continue
        if key.startswith("不涉及：") or key.startswith("不涉及:"):
            if len(key.split("：", 1)[-1].split(":", 1)[-1].strip()) < 2:
                errors.append(f"01-research.md {label}写不涉及时必须说明具体原因")
            continue
        refs = claim_refs(table_cell(headers, row, "结论ID"))
        row_label = key or f"第{index}行"
        if not refs:
            errors.append(f"01-research.md {label}“{row_label}”缺少 Cxx 结论引用")
        for ref in refs:
            if ref not in valid_claim_ids:
                errors.append(f"01-research.md {label}“{row_label}”引用了不存在的结论ID: {ref}")


def assert_research_main_flow_content(main_flow: str, errors: list[str]) -> None:
    for prefix in [
        "- 入口：",
        "- 核心处理与异步链路：",
        "- 关联产物不变量及数据承载：",
        "- 失败重试 / 主动再次操作：",
        "- 框架隐式链路（AOP / Filter / Interceptor / 动态 Bean / 事务 / 异常 / 生成代码）：",
        "- 关键依赖和数据落点：",
    ]:
        value = extract_line_value(main_flow, prefix)
        if value in EMPTY_VALUES:
            errors.append(f"01-research.md 主链路代码事实缺少实质内容: {prefix.rstrip('：')}")
        not_applicable = re.fullmatch(r"不涉及[：:](.*)", value)
        if not_applicable and len(not_applicable.group(1).strip()) < 2:
            errors.append(f"01-research.md 主链路代码事实写不涉及时必须说明具体原因: {prefix.rstrip('：')}")


def assert_research_table_content(section: str, label: str, key_header: str, errors: list[str]) -> None:
    headers, rows = extract_first_table(section)
    substantive = False
    for row in rows:
        key = table_cell(headers, row, key_header)
        if key in EMPTY_VALUES:
            continue
        if key.startswith("不涉及：") or key.startswith("不涉及:"):
            reason = re.split(r"[：:]", key, maxsplit=1)[-1].strip()
            if len(reason) < 2:
                errors.append(f"01-research.md {label}写不涉及时必须说明具体原因")
            else:
                substantive = True
            continue
        substantive = True
    if not substantive:
        errors.append(f"01-research.md {label}没有真实业务行；不涉及时必须在首列写“不涉及：原因”")


def assert_shared_semantic_impact(
    section: str,
    claim_ledger: str,
    question_ledger: str,
    evidence: str,
    errors: list[str],
) -> None:
    required_headers = [
        "共享语义",
        "权威载体/存储值",
        "消费场景",
        "读取/传播位置",
        "当前处理规则",
        "新语义预期",
        "代码改动结论",
        "证据ID",
        "结论ID",
        "验证缺口",
    ]
    assert_table_has_headers(
        section,
        required_headers,
        "01-research.md 共享语义影响矩阵缺少关键表头: " + "、".join(required_headers),
        errors,
    )

    judgment = extract_line_value(section, "- 影响面判断：")
    if judgment.startswith("不涉及"):
        match = re.fullmatch(r"不涉及[：:](.+)", judgment)
        if not match or len(match.group(1).strip()) < 2:
            errors.append("01-research.md 共享语义影响判断写不涉及时必须说明具体原因")
        return
    if judgment != "涉及":
        errors.append("01-research.md 共享语义影响判断只允许“涉及”或“不涉及：具体原因”")
        return

    search_scope = extract_line_value(section, "- 检索范围：")
    if search_scope in EMPTY_VALUES or search_scope.startswith("不涉及"):
        errors.append("01-research.md 涉及共享语义变化时必须记录实际检索范围")

    evidence_ids = extract_table_ids(evidence, r"E\d+")
    question_ids = extract_table_ids(question_ledger, r"Q\d+")
    ledger_headers, ledger_rows = extract_first_table(claim_ledger)
    claim_records = {
        table_cell(ledger_headers, row, "结论ID"): {
            "type": table_cell(ledger_headers, row, "结论类型"),
            "level": table_cell(ledger_headers, row, "证据等级"),
            "runtime_gap": table_cell(ledger_headers, row, "运行时证据缺口"),
        }
        for row in ledger_rows
        if re.fullmatch(r"C\d+", table_cell(ledger_headers, row, "结论ID") or "")
    }

    headers, rows = extract_first_table(section)
    substantive = False
    for index, row in enumerate(rows, start=1):
        semantic = table_cell(headers, row, "共享语义")
        if semantic in EMPTY_VALUES:
            continue
        substantive = True
        scenario = table_cell(headers, row, "消费场景") or f"第{index}行"
        for header in [
            "权威载体/存储值",
            "消费场景",
            "读取/传播位置",
            "当前处理规则",
            "新语义预期",
            "代码改动结论",
            "证据ID",
            "结论ID",
            "验证缺口",
        ]:
            if table_cell(headers, row, header) == "":
                errors.append(f"01-research.md 共享语义“{semantic}”消费场景“{scenario}”缺少{header}")

        result = table_cell(headers, row, "代码改动结论")
        if result not in {"需改", "无需改", "仅运行验证", "阻塞"}:
            errors.append(
                f"01-research.md 共享语义“{semantic}”消费场景“{scenario}”代码改动结论不合法: {result}"
            )

        row_evidence_refs = evidence_refs(table_cell(headers, row, "证据ID"))
        if not row_evidence_refs:
            errors.append(f"01-research.md 共享语义“{semantic}”消费场景“{scenario}”缺少 Exx 证据")
        for ref in row_evidence_refs:
            if ref not in evidence_ids:
                errors.append(
                    f"01-research.md 共享语义“{semantic}”消费场景“{scenario}”引用了不存在的证据ID: {ref}"
                )

        row_claim_refs = claim_refs(table_cell(headers, row, "结论ID"))
        shared_claims = [
            ref for ref in row_claim_refs if claim_records.get(ref, {}).get("type") == "共享语义影响"
        ]
        if not shared_claims:
            errors.append(
                f"01-research.md 共享语义“{semantic}”消费场景“{scenario}”"
                "必须引用类型为“共享语义影响”的 Cxx"
            )
        for ref in row_claim_refs:
            if ref not in claim_records:
                errors.append(
                    f"01-research.md 共享语义“{semantic}”消费场景“{scenario}”引用了不存在的结论ID: {ref}"
                )

        gap = table_cell(headers, row, "验证缺口")
        if result == "仅运行验证" and gap in EMPTY_VALUES:
            errors.append(
                f"01-research.md 共享语义“{semantic}”消费场景“{scenario}”"
                "标为仅运行验证时必须写清验证缺口"
            )
        if result == "仅运行验证" and shared_claims and not any(
            claim_records[ref]["runtime_gap"] not in EMPTY_VALUES for ref in shared_claims
        ):
            errors.append(
                f"01-research.md 共享语义“{semantic}”消费场景“{scenario}”"
                "标为仅运行验证时，关联 Cxx 必须记录运行时证据缺口"
            )
        if result == "阻塞":
            gap_questions = question_refs(gap)
            if not gap_questions:
                errors.append(
                    f"01-research.md 共享语义“{semantic}”消费场景“{scenario}”"
                    "标为阻塞时必须在验证缺口中引用 Qxx"
                )
            for ref in gap_questions:
                if ref not in question_ids:
                    errors.append(
                        f"01-research.md 共享语义“{semantic}”消费场景“{scenario}”"
                        f"引用了不存在的疑问编号: {ref}"
                    )
            if shared_claims and not any(claim_records[ref]["level"] == "阻塞" for ref in shared_claims):
                errors.append(
                    f"01-research.md 共享语义“{semantic}”消费场景“{scenario}”"
                    "标为阻塞时，关联 Cxx 的证据等级也必须为阻塞"
                )

    if not substantive:
        errors.append("01-research.md 涉及共享语义变化时，影响矩阵至少需要一个真实消费场景")


def assert_research_baseline_coverage(
    baseline_check: str,
    expected_baseline_ids: set[str],
    errors: list[str],
) -> None:
    headers, rows = extract_first_table(baseline_check)
    if "baseline ID" not in headers:
        errors.append("01-research.md Baseline 验证清单缺少 baseline ID 列")
        return
    actual_ids = [
        table_cell(headers, row, "baseline ID")
        for row in rows
        if re.fullmatch(r"B\d+", table_cell(headers, row, "baseline ID") or "")
    ]
    for baseline_id in sorted({item for item in actual_ids if actual_ids.count(item) > 1}):
        errors.append(f"01-research.md Baseline 验证清单重复验证基线条目: {baseline_id}")
    actual_set = set(actual_ids)
    for baseline_id in sorted(expected_baseline_ids - actual_set):
        errors.append(f"01-research.md Baseline 验证清单遗漏基线条目: {baseline_id}")
    for baseline_id in sorted(actual_set - expected_baseline_ids):
        errors.append(f"01-research.md Baseline 验证清单引用了不存在的基线条目: {baseline_id}")


def assert_research_quality(
    text: str,
    errors: list[str],
    repo_root: Path | None = None,
    expected_baseline_ids: set[str] | None = None,
    strict: bool = False,
) -> None:
    current_format = "## 8. 结论账本（Claim Ledger）" in text
    research_version = research_schema_version(text)
    research_v2 = research_version >= 2
    research_v3 = research_version >= 3
    if current_format:
        for heading in [
            "## 1. Baseline 验证清单",
            "## 2. 主链路代码事实",
            "## 3. 旧链路副作用清单",
            "## 4. 数据身份和状态维度对照",
            "## 5. 复用性分级",
            "## 6. 旧能力反向影响检查",
            "## 7. 跨项目依赖能力",
            "## 8. 结论账本（Claim Ledger）",
            "## 9. 进入技术方案前疑问账本",
            "## 10. 残余风险和后续确认方式",
            "## 11. 代码证据索引",
        ]:
            count = len(re.findall(rf"(?m)^{re.escape(heading)}\s*$", text))
            if count != 1:
                errors.append(f"01-research.md 章节“{heading}”必须且只能出现一次，当前 {count} 次")
        if research_v2:
            shared_heading = "### 6.1 共享状态、枚举和类型语义影响矩阵"
            count = len(re.findall(rf"(?m)^{re.escape(shared_heading)}\s*$", text))
            if count != 1:
                errors.append(f"01-research.md 章节“{shared_heading}”必须且只能出现一次，当前 {count} 次")
        if research_v3:
            sql_heading = "### 7.1 SQL 影响与确认准备"
            count = len(re.findall(rf"(?m)^{re.escape(sql_heading)}\s*$", text))
            if count != 1:
                errors.append(f"01-research.md 章节“{sql_heading}”必须且只能出现一次，当前 {count} 次")
    baseline_check = extract_section(text, "## 1. Baseline 验证清单")
    main_flow = extract_section(text, "## 2. 主链路代码事实")
    old_side_effects = extract_section(text, "## 3. 旧链路副作用清单")
    data_identity = extract_section(text, "## 4. 数据身份和状态维度对照")
    reuse = extract_section(text, "## 5. 复用性分级")
    reverse_impact = extract_section(text, "## 6. 旧能力反向影响检查")
    shared_semantic = extract_section(text, "### 6.1 共享状态、枚举和类型语义影响矩阵")
    if shared_semantic:
        reverse_impact = reverse_impact.split(
            "### 6.1 共享状态、枚举和类型语义影响矩阵",
            maxsplit=1,
        )[0].rstrip()
    cross_project = extract_section(text, "## 7. 跨项目依赖能力")
    sql_gate = research_sql_section(text)
    if sql_gate:
        cross_project = cross_project.split(
            "### 7.1 SQL 影响与确认准备",
            maxsplit=1,
        )[0].rstrip()
    coverage = extract_section(text, "## 8. 代码证据覆盖度、运行时证据缺口和置信度") if not current_format else ""
    claim_ledger = extract_section(
        text,
        "## 8. 结论账本（Claim Ledger）" if current_format else "## 9. 结论账本（Claim Ledger）",
    )
    blocking = extract_section(
        text,
        "## 9. 进入技术方案前疑问账本" if current_format else "## 10. 进入技术方案前阻塞问题",
    )
    residual_risk = extract_section(
        text,
        "## 10. 残余风险和后续确认方式" if current_format else "## 11. 残余风险和后续确认方式",
    )
    evidence = extract_section(text, "## 11. 代码证据索引" if current_format else "## 12. 代码证据索引")

    if strict:
        assert_research_main_flow_content(main_flow, errors)
        for section, label, key_header in [
            (old_side_effects, "旧链路副作用清单", "旧能力"),
            (data_identity, "数据身份和状态维度对照", "业务对象"),
            (reuse, "复用性分级", "能力/代码"),
            (reverse_impact, "旧能力反向影响检查", "准备复用/改造的旧能力"),
            (cross_project, "跨项目依赖能力", "项目"),
        ]:
            assert_research_table_content(section, label, key_header, errors)
        assert_research_baseline_coverage(baseline_check, expected_baseline_ids or set(), errors)

    assert_unique_table_ids(claim_ledger, r"C\d+", "结论", errors)
    assert_unique_table_ids(blocking, r"Q\d+", "疑问", errors)
    assert_unique_table_ids(evidence, r"E\d+", "证据", errors)

    assert_section_has_substance(baseline_check, "## 1. Baseline 验证清单", "01-research.md", errors, min_lines=2)
    assert_section_has_substance(main_flow, "## 2. 主链路代码事实", "01-research.md", errors, min_lines=2)
    assert_section_has_substance(old_side_effects, "## 3. 旧链路副作用清单", "01-research.md", errors, min_lines=2)
    assert_section_has_substance(data_identity, "## 4. 数据身份和状态维度对照", "01-research.md", errors, min_lines=2)
    assert_section_has_substance(reuse, "## 5. 复用性分级", "01-research.md", errors, min_lines=2)
    assert_section_has_substance(reverse_impact, "## 6. 旧能力反向影响检查", "01-research.md", errors, min_lines=2)
    if research_v2:
        assert_section_has_substance(
            shared_semantic,
            "### 6.1 共享状态、枚举和类型语义影响矩阵",
            "01-research.md",
            errors,
            min_lines=2,
        )
    if research_v3:
        assert_section_has_substance(
            sql_gate,
            "### 7.1 SQL 影响与确认准备",
            "01-research.md",
            errors,
            min_lines=3,
        )
    if not current_format:
        assert_section_has_substance(coverage, "## 8. 代码证据覆盖度、运行时证据缺口和置信度", "01-research.md", errors, min_lines=2)
    assert_section_has_substance(
        claim_ledger,
        "## 8. 结论账本（Claim Ledger）" if current_format else "## 9. 结论账本（Claim Ledger）",
        "01-research.md",
        errors,
        min_lines=2,
    )
    assert_section_has_substance(
        residual_risk,
        "## 10. 残余风险和后续确认方式" if current_format else "## 11. 残余风险和后续确认方式",
        "01-research.md",
        errors,
        min_lines=2,
    )
    assert_section_has_substance(
        blocking,
        "## 9. 进入技术方案前疑问账本" if current_format else "## 10. 进入技术方案前阻塞问题",
        "01-research.md",
        errors,
        min_lines=2,
    )
    assert_table_has_headers(
        baseline_check,
        (["baseline ID"] if strict else []) + ["baseline 条目", "验证状态", "代码事实", "证据ID", "结论ID", "风险"] if current_format else
        ["baseline 条目", "验证状态", "代码事实", "证据ID", "风险"],
        "01-research.md Baseline 验证清单缺少关键表头: baseline 条目、验证状态、代码事实、证据ID、结论ID、风险"
        if current_format else
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
    if not current_format:
        assert_table_has_headers(
            coverage,
            ["结论ID", "证据来源", "证据等级", "未覆盖范围", "运行时证据缺口", "置信度"],
            "01-research.md 代码证据覆盖度缺少关键表头: 结论ID、证据来源、证据等级、未覆盖范围、运行时证据缺口、置信度",
            errors,
        )
    claim_headers = ["结论ID", "关键结论", "结论类型", "证据ID", "证据等级", "置信度", "未覆盖范围", "后续确认方式"]
    if current_format:
        claim_headers.append("运行时证据缺口")
    assert_table_has_headers(
        claim_ledger,
        claim_headers,
        "01-research.md 结论账本缺少关键表头: " + "、".join(claim_headers),
        errors,
    )
    assert_table_has_headers(
        evidence,
        ["编号", "项目", "位置", "结论说明"],
        "01-research.md 代码证据索引缺少关键表头: 编号、项目、位置、结论说明",
        errors,
    )
    if current_format:
        valid_claim_ids = extract_table_ids(claim_ledger, r"C\d+")
        for section, label, key_header in [
            (old_side_effects, "旧链路副作用清单", "旧能力"),
            (data_identity, "数据身份和状态维度对照", "业务对象"),
            (reuse, "复用性分级", "能力/代码"),
            (reverse_impact, "旧能力反向影响检查", "准备复用/改造的旧能力"),
            (cross_project, "跨项目依赖能力", "项目"),
        ]:
            assert_research_detail_claim_refs(section, label, key_header, valid_claim_ids, errors)
        if research_v2:
            assert_shared_semantic_impact(shared_semantic, claim_ledger, blocking, evidence, errors)
        if research_v3:
            research_sql_gate_snapshot(text, errors, valid_claim_ids)
    # 新版唯一疑问账本显式区分用户意图、代码事实和设计选择；旧文档保持兼容。
    if current_format or "问题类型" in blocking:
        question_headers = ["编号", "疑问", "问题类型", "准确来源", "应由谁确认", "确认结论/转交说明", "状态"]
        if strict:
            question_headers.append("结论ID")
        assert_table_has_headers(
            blocking,
            question_headers,
            "01-research.md 疑问账本缺少关键表头: 编号、疑问、问题类型、准确来源、应由谁确认、确认结论/转交说明、状态",
            errors,
        )
        blocking_headers, blocking_rows = extract_first_table(blocking)
        for row in blocking_rows:
            question_id = table_cell(blocking_headers, row, "编号")
            if not re.fullmatch(r"Q\d+", question_id or ""):
                continue
            question_type = table_cell(blocking_headers, row, "问题类型")
            source = table_cell(blocking_headers, row, "准确来源")
            owner = table_cell(blocking_headers, row, "应由谁确认")
            conclusion = table_cell(blocking_headers, row, "确认结论/转交说明")
            linked_claims = claim_refs(table_cell(blocking_headers, row, "结论ID"))
            status = table_cell(blocking_headers, row, "状态")
            if status not in {"已确认", "转下游"}:
                errors.append(f"01-research.md {question_id} 疑问未清零: {status}")
            if question_type not in {"用户意图", "代码事实", "设计选择"}:
                errors.append(f"01-research.md {question_id} 问题类型非法或缺失: {question_type}")
            if not source or source in {"-", "无"}:
                errors.append(f"01-research.md {question_id} 缺少准确来源")
            if not conclusion or conclusion in {"-", "无"}:
                errors.append(f"01-research.md {question_id} 缺少确认结论或转交说明")
            if question_type == "用户意图" and (owner != "用户" or status == "转下游"):
                errors.append(f"01-research.md {question_id} 用户意图问题必须由用户确认，不得转下游")
            if question_type == "代码事实":
                if owner != "需求对齐" or status != "已确认":
                    errors.append(f"01-research.md {question_id} 代码事实必须在需求对齐阶段验证完成")
                if not evidence_refs(f"{source} {conclusion}"):
                    errors.append(f"01-research.md {question_id} 已确认代码事实缺少 Exx 证据")
                if strict and not linked_claims:
                    errors.append(f"01-research.md {question_id} 已确认代码事实必须引用已闭合的 Cxx")
                if strict:
                    eligible_claims = extract_design_eligible_claim_ids_from_research(text)
                    for ref in linked_claims:
                        if ref not in eligible_claims:
                            errors.append(f"01-research.md {question_id} 引用的 {ref} 尚未闭合，不能将代码事实标为已确认")
            if question_type == "设计选择" and (owner != "技术方案" or status != "转下游"):
                errors.append(f"01-research.md {question_id} 设计选择只能写明理由后转交技术方案")
    residual_blocks = re.findall(r"(?m)^-\s*阻塞风险[：:]\s*(.*)$", text)
    if current_format and not residual_blocks:
        errors.append("01-research.md 残余风险缺少“阻塞风险”项")
    if current_format and len(residual_blocks) > 1:
        errors.append("01-research.md 残余风险只能有一条“阻塞风险”，禁止用重复条目隐藏真实阻塞")
    for residual_block in residual_blocks:
        residual_block = residual_block.strip().rstrip("。；;")
        if residual_block not in EMPTY_VALUES:
            refs = question_refs(residual_block)
            if not refs:
                errors.append("01-research.md 残余阻塞风险必须引用唯一疑问账本中的 Qxx")
            errors.append("01-research.md 仍存在残余阻塞风险，不能完成需求对齐")
    assert_regex_exists(
        text,
        r"\|\s*E\d+\s*\|\s*[^|\s][^|]*\|",
        "01-research.md 缺少已填写的代码证据行",
        errors,
    )
    assert_research_evidence_quality(
        baseline_check,
        claim_ledger,
        blocking,
        evidence,
        errors,
        repo_root,
        legacy_coverage=coverage,
        strict=strict,
    )


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


def assert_design_claim_eligibility(text: str, eligible_claim_ids: set[str], errors: list[str]) -> None:
    refs: set[str] = set()
    for headers, rows in iter_markdown_tables(text):
        if "来源Cxx" not in headers:
            continue
        for row in rows:
            refs.update(claim_refs(table_cell(headers, row, "来源Cxx")))
    for ref in sorted(refs - eligible_claim_ids):
        errors.append(f"02-design.md 引用了尚未闭合、不能作为确定方案依据的结论ID: {ref}")


DESIGN_TEMPLATE_VALUES = {
    "", "-", "是/否", "是 / 否", "有 / 无", "预检中 / SQL待确认 / 方案编写中 / 已完成",
    "首屏/点击后/提交后", "进入设计 / 仅作为风险 / 不进入设计", "形成设计决策",
    "新增/修改", "业务事实/关系/状态/审计/冗余", "不涉及：具体原因 / 表名",
    "需要 / 不需要", "无需：具体原因", "HTTP / RPC / MQ / Job / 内部方法",
}

VAGUE_DESIGN_VALUES = {
    "确认", "按需", "视情况", "以后可能", "方便扩展", "结构更清晰", "结构清晰",
    "可能高并发", "数据量可能变大", "支持查询", "提升性能", "优化性能", "无影响",
}


def meaningful_design_value(value: str) -> bool:
    value = value.strip().strip("`")
    return bool(value) and value not in DESIGN_TEMPLATE_VALUES


def vague_design_value(value: str) -> bool:
    normalized = value.strip().strip("`").rstrip("。；;")
    return normalized in VAGUE_DESIGN_VALUES


def manifest_is_empty(value: str) -> bool:
    normalized = value.strip().strip("`").rstrip("。；;")
    return (
        normalized in MANIFEST_EMPTY_VALUES
        or normalized.startswith("无：")
        or normalized.startswith("无:")
        or normalized.startswith("不涉及：")
        or normalized.startswith("不涉及:")
    )


def split_manifest_items(value: str) -> list[str]:
    return [
        item.strip().strip("`")
        for item in re.split(r"[、,，;；]", value)
        if item.strip().strip("`")
    ]


def parse_field_manifest(value: str, label: str, errors: list[str]) -> set[str]:
    if manifest_is_empty(value):
        return set()
    items = split_manifest_items(value)
    result: set[str] = set()
    for item in items:
        if not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_$]*(?:\[\])?(?:\.[A-Za-z_][A-Za-z0-9_$]*(?:\[\])?)*",
            item,
        ):
            errors.append(f"{label} 包含非法字段路径: {item}")
            continue
        result.add(item)
    if len(result) != len(items):
        errors.append(f"{label} 包含重复字段")
    if not result and not errors:
        errors.append(f"{label} 缺少字段列表或明确的“无”")
    return result


def parse_trusted_field_manifest(value: str, label: str, errors: list[str]) -> dict[str, str]:
    if manifest_is_empty(value):
        return {}
    result: dict[str, str] = {}
    for item in split_manifest_items(value):
        if "=" not in item:
            errors.append(f"{label} 必须使用“字段=可信来源”: {item}")
            continue
        field, source = [part.strip().strip("`") for part in item.split("=", 1)]
        if not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_$]*(?:\[\])?(?:\.[A-Za-z_][A-Za-z0-9_$]*(?:\[\])?)*",
            field,
        ):
            errors.append(f"{label} 包含非法字段路径: {field}")
            continue
        if not meaningful_design_value(source):
            errors.append(f"{label} 的字段 {field} 缺少可信来源")
            continue
        if field in result:
            errors.append(f"{label} 重复登记字段: {field}")
        result[field] = source
    return result


def parse_side_effect_manifest(value: str, label: str, errors: list[str]) -> set[str]:
    normalized_value = value.strip().strip("`").rstrip("。；;")
    no_effect = re.fullmatch(r"无[：:](.+)", normalized_value)
    if no_effect:
        reason = no_effect.group(1).strip()
        if not meaningful_design_value(reason) or vague_design_value(reason):
            errors.append(f"{label} 选择“无”时必须填写具体原因")
        return set()
    if manifest_is_empty(value):
        errors.append(f"{label} 必须填写具体副作用或“无：具体原因”，不能使用裸“无”")
        return set()
    items = split_manifest_items(value)
    if not items:
        errors.append(f"{label} 缺少具体副作用或明确的“无：原因”")
        return set()
    normalized = {re.sub(r"\s+", " ", item).strip() for item in items}
    if len(normalized) != len(items):
        errors.append(f"{label} 包含重复副作用")
    return normalized


def normalize_contract_identifier(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().strip("`"))


def find_table(section: str, required_headers: list[str]) -> tuple[list[str], list[list[str]]]:
    for headers, rows in iter_markdown_tables(section):
        if all(header in headers for header in required_headers):
            return headers, rows
    return [], []


def actual_table_rows(headers: list[str], rows: list[list[str]], key_header: str) -> list[list[str]]:
    result: list[list[str]] = []
    for row in rows:
        key = table_cell(headers, row, key_header)
        if meaningful_design_value(key):
            result.append(row)
    return result


def assert_required_row_values(
    label: str,
    headers: list[str],
    rows: list[list[str]],
    key_header: str,
    required_headers: list[str],
    errors: list[str],
    allow_not_applicable: bool = False,
) -> list[list[str]]:
    if not headers:
        errors.append(f"02-design.md 缺少{label}或关键表头: {'、'.join(required_headers)}")
        return []
    actual = actual_table_rows(headers, rows, key_header)
    if not actual:
        errors.append(f"02-design.md 的{label}没有真实数据行")
        return []
    for index, row in enumerate(actual, start=1):
        key = table_cell(headers, row, key_header)
        if allow_not_applicable and key.startswith("不涉及：") and len(key) > len("不涉及："):
            continue
        for header in required_headers:
            value = table_cell(headers, row, header)
            if not meaningful_design_value(value):
                errors.append(f"02-design.md 的{label}行“{key or index}”缺少实质字段: {header}")
    return actual


def assert_design_input_coverage(
    text: str,
    errors: list[str],
    eligible_claim_ids: set[str] | None,
    transferred_question_ids: set[str] | None,
) -> None:
    if design_schema_version(text) >= 4:
        section = extract_section(text, "## 〇、设计输入去向")
        required = ["输入ID", "处理方式", "对应Dxx/章节或原因"]
        headers, rows = find_table(section, required)
        if not headers:
            errors.append("02-design.md 缺少设计输入去向表或关键表头")
            return

        ids: list[str] = []
        for row in rows:
            input_id = table_cell(headers, row, "输入ID")
            if not re.fullmatch(r"[CQ]\d+", input_id or ""):
                continue
            ids.append(input_id)
            handling = table_cell(headers, row, "处理方式")
            target = table_cell(headers, row, "对应Dxx/章节或原因")
            if input_id.startswith("C"):
                if handling not in {"进入设计", "仅作为风险", "不进入设计"}:
                    errors.append(f"02-design.md 设计输入 {input_id} 处理方式非法或缺失: {handling}")
                elif handling == "进入设计" and not (design_refs(target) or re.search(r"§\s*\d+", target)):
                    errors.append(f"02-design.md 设计输入 {input_id} 缺少对应 Dxx 或章节")
                elif handling != "进入设计" and not meaningful_design_value(target):
                    errors.append(f"02-design.md 设计输入 {input_id} 必须写明风险落点或不进入原因")
            else:
                if handling != "形成设计决策":
                    errors.append(f"02-design.md 转入的设计选择 {input_id} 必须形成设计决策")
                if not design_refs(target):
                    errors.append(f"02-design.md 转入的设计选择 {input_id} 缺少对应 Dxx")

        for duplicate in sorted({item for item in ids if ids.count(item) > 1}):
            errors.append(f"02-design.md 设计输入去向编号重复: {duplicate}")
        actual_ids = set(ids)
        expected = set(eligible_claim_ids or set()) | set(transferred_question_ids or set())
        for missing in sorted(expected - actual_ids):
            errors.append(f"02-design.md 设计输入去向遗漏 Research 输入: {missing}")
        if eligible_claim_ids is not None and transferred_question_ids is not None:
            for unexpected in sorted(actual_ids - expected):
                errors.append(f"02-design.md 设计输入去向包含非预期或未闭合输入: {unexpected}")
        return

    section = extract_section(text, "## 〇、设计输入覆盖清单")
    required = ["输入ID", "输入类型", "核心内容摘要", "处理方式", "对应Dxx/章节", "不进入设计原因"]
    headers, rows = find_table(section, required)
    if not headers:
        errors.append("02-design.md 缺少设计输入覆盖清单或关键表头")
        return

    ids: list[str] = []
    for row in rows:
        input_id = table_cell(headers, row, "输入ID")
        if not re.fullmatch(r"[CQ]\d+", input_id or ""):
            continue
        ids.append(input_id)
        summary = table_cell(headers, row, "核心内容摘要")
        handling = table_cell(headers, row, "处理方式")
        target = table_cell(headers, row, "对应Dxx/章节")
        excluded_reason = table_cell(headers, row, "不进入设计原因")
        if not meaningful_design_value(summary):
            errors.append(f"02-design.md 设计输入 {input_id} 缺少核心内容摘要")
        if input_id.startswith("C"):
            if handling not in {"进入设计", "仅作为风险", "不进入设计"}:
                errors.append(f"02-design.md 设计输入 {input_id} 处理方式非法或缺失: {handling}")
            elif handling == "不进入设计":
                if not meaningful_design_value(excluded_reason):
                    errors.append(f"02-design.md 设计输入 {input_id} 不进入设计时必须写明原因")
            elif not (design_refs(target) or re.search(r"§\s*\d+", target)):
                errors.append(f"02-design.md 设计输入 {input_id} 缺少对应 Dxx 或章节")
        else:
            if handling != "形成设计决策":
                errors.append(f"02-design.md 转入的设计选择 {input_id} 必须形成设计决策")
            if not design_refs(target):
                errors.append(f"02-design.md 转入的设计选择 {input_id} 缺少对应 Dxx")

    for duplicate in sorted({item for item in ids if ids.count(item) > 1}):
        errors.append(f"02-design.md 设计输入覆盖清单编号重复: {duplicate}")
    actual_ids = set(ids)
    expected = set(eligible_claim_ids or set()) | set(transferred_question_ids or set())
    for missing in sorted(expected - actual_ids):
        errors.append(f"02-design.md 设计输入覆盖清单遗漏 Research 输入: {missing}")
    for unexpected in sorted(actual_ids - expected) if eligible_claim_ids is not None and transferred_question_ids is not None else []:
        errors.append(f"02-design.md 设计输入覆盖清单包含非预期或未闭合输入: {unexpected}")


def assert_design_precheck_tables(text: str, errors: list[str], eligible_claim_ids: set[str] | None) -> None:
    if design_schema_version(text) >= 4:
        assert_design_precheck_tables_v4(text, errors, eligible_claim_ids)
        return

    identity = extract_section(text, "## 二、实例身份与状态隔离")
    headers, rows = find_table(
        identity,
        ["业务对象/记录", "唯一标识", "状态隔离维度", "去重维度", "生命周期", "来源Cxx", "是否已确认"],
    )
    actual = assert_required_row_values(
        "实例身份表", headers, rows, "业务对象/记录",
        ["唯一标识", "状态隔离维度", "去重维度", "生命周期", "来源Cxx", "是否已确认"], errors,
    )
    for row in actual:
        key = table_cell(headers, row, "业务对象/记录")
        if table_cell(headers, row, "是否已确认") != "是":
            errors.append(f"02-design.md 的实例身份表行“{key}”尚未确认")
        assert_claim_refs_exist(f"02-design.md 实例身份行“{key}”", claim_refs(table_cell(headers, row, "来源Cxx")), eligible_claim_ids, errors)

    derive_headers, derive_rows = find_table(
        identity, ["字段/身份", "后端获取方式", "前端是否允许传", "禁止原因", "兜底/校验方式", "来源Cxx"]
    )
    derived = assert_required_row_values(
        "后端自动推导与前端禁止传表", derive_headers, derive_rows, "字段/身份",
        ["后端获取方式", "前端是否允许传", "禁止原因", "兜底/校验方式", "来源Cxx"], errors,
        allow_not_applicable=True,
    )
    for row in derived:
        key = table_cell(derive_headers, row, "字段/身份")
        if key.startswith("不涉及："):
            continue
        if table_cell(derive_headers, row, "前端是否允许传") not in {"是", "否"}:
            errors.append(f"02-design.md 的后端推导表行“{key}”前端是否允许传必须明确为是或否")
        assert_claim_refs_exist(f"02-design.md 后端推导行“{key}”", claim_refs(table_cell(derive_headers, row, "来源Cxx")), eligible_claim_ids, errors)

    contract = extract_section(text, "## 三、前后端接口协作流")
    contract_required = ["页面/动作", "调用接口", "首屏/点击后", "请求关键字段", "后端自动推导", "前端禁止传", "返回粒度", "来源Cxx", "说明"]
    contract_headers, contract_rows = find_table(contract, contract_required)
    contract_actual = assert_required_row_values(
        "前后端接口协作流", contract_headers, contract_rows, "页面/动作", contract_required[1:], errors,
        allow_not_applicable=True,
    )
    for row in contract_actual:
        key = table_cell(contract_headers, row, "页面/动作")
        if key.startswith("不涉及："):
            continue
        assert_claim_refs_exist(f"02-design.md 协作流行“{key}”", claim_refs(table_cell(contract_headers, row, "来源Cxx")), eligible_claim_ids, errors)

    carrier = extract_section(text, "## 四、数据承载设计")
    carrier_required = ["数据/状态", "承载方式", "MySQL", "Redis", "ES", "MQ", "配置/缓存", "选择原因", "一致性/过期策略", "来源Cxx"]
    carrier_headers, carrier_rows = find_table(carrier, carrier_required)
    carrier_actual = assert_required_row_values(
        "数据承载设计", carrier_headers, carrier_rows, "数据/状态", carrier_required[1:], errors,
    )
    selected_non_mysql: set[str] = set()
    carrier_type_map = {"Redis": "Redis", "ES": "ES", "MQ": "MQ", "配置/缓存": "配置"}
    for row in carrier_actual:
        key = table_cell(carrier_headers, row, "数据/状态")
        for flag in ["MySQL", "Redis", "ES", "MQ", "配置/缓存"]:
            if table_cell(carrier_headers, row, flag) not in {"是", "否"}:
                errors.append(f"02-design.md 的数据承载行“{key}”字段 {flag} 必须明确为是或否")
        for flag, carrier_type in carrier_type_map.items():
            if table_cell(carrier_headers, row, flag) == "是":
                selected_non_mysql.add(carrier_type)
        assert_claim_refs_exist(f"02-design.md 数据承载行“{key}”", claim_refs(table_cell(carrier_headers, row, "来源Cxx")), eligible_claim_ids, errors)

    detail_required = ["类型", "标识（Key / Index / Topic / 配置项）", "数据结构/消息体", "生命周期", "一致性/过期策略", "幂等/失败处理", "来源Cxx", "来源Dxx"]
    detail_headers, detail_rows = find_table(carrier, detail_required)
    detail_actual = assert_required_row_values(
        "非 MySQL 承载明细", detail_headers, detail_rows, "类型", detail_required[1:], errors,
        allow_not_applicable=True,
    )
    detailed_types: set[str] = set()
    for row in detail_actual:
        carrier_type = table_cell(detail_headers, row, "类型")
        if carrier_type.startswith("不涉及："):
            if selected_non_mysql:
                errors.append("02-design.md 已选择非 MySQL 承载，不能将承载明细写为不涉及")
            continue
        detailed_types.add("配置" if carrier_type in {"配置", "本地缓存"} else carrier_type)
        assert_claim_refs_exist(f"02-design.md {carrier_type} 承载明细", claim_refs(table_cell(detail_headers, row, "来源Cxx")), eligible_claim_ids, errors)
        if not design_refs(table_cell(detail_headers, row, "来源Dxx")):
            errors.append(f"02-design.md {carrier_type} 承载明细缺少来源 Dxx")
    for missing in sorted(selected_non_mysql - detailed_types):
        errors.append(f"02-design.md 数据承载选择了 {missing}，但缺少对应非 MySQL 承载明细")


def assert_design_precheck_tables_v4(
    text: str,
    errors: list[str],
    eligible_claim_ids: set[str] | None,
) -> None:
    identity = extract_section(text, "## 二、实例身份与可信边界")
    identity_required = [
        "业务对象/记录", "唯一标识", "状态隔离维度", "去重维度", "生命周期", "来源Cxx", "是否已确认",
    ]
    headers, rows = find_table(identity, identity_required)
    actual = assert_required_row_values(
        "实例身份表",
        headers,
        rows,
        "业务对象/记录",
        identity_required[1:],
        errors,
        allow_not_applicable=True,
    )
    for row in actual:
        key = table_cell(headers, row, "业务对象/记录")
        if key.startswith("不涉及："):
            continue
        if table_cell(headers, row, "是否已确认") != "是":
            errors.append(f"02-design.md 的实例身份表行“{key}”尚未确认")
        assert_claim_refs_exist(
            f"02-design.md 实例身份行“{key}”",
            claim_refs(table_cell(headers, row, "来源Cxx")),
            eligible_claim_ids,
            errors,
        )

    derive_required = [
        "字段/身份", "后端获取方式", "外部是否允许传", "可信边界/禁止原因", "兜底/校验方式", "来源Cxx",
    ]
    derive_headers, derive_rows = find_table(identity, derive_required)
    derived = assert_required_row_values(
        "后端推导与可信边界表",
        derive_headers,
        derive_rows,
        "字段/身份",
        derive_required[1:],
        errors,
        allow_not_applicable=True,
    )
    for row in derived:
        key = table_cell(derive_headers, row, "字段/身份")
        if key.startswith("不涉及："):
            continue
        if table_cell(derive_headers, row, "外部是否允许传") not in {"是", "否"}:
            errors.append(f"02-design.md 的后端推导表行“{key}”外部是否允许传必须明确为是或否")
        assert_claim_refs_exist(
            f"02-design.md 后端推导行“{key}”",
            claim_refs(table_cell(derive_headers, row, "来源Cxx")),
            eligible_claim_ids,
            errors,
        )

    contract = extract_section(text, "## 三、调用方与接口契约")
    if design_schema_version(text) >= 5:
        contract_required = [
            "设计ID", "调用方/触发事件", "契约类型", "契约标识", "输入关键字段",
            "后端推导字段/来源", "禁止外部传字段", "输出字段", "副作用",
            "独立明细", "来源Cxx", "说明",
        ]
    else:
        contract_required = [
            "设计ID", "调用方/触发事件", "接口/消息/任务", "类型", "输入关键字段",
            "后端推导/可信边界", "输出结果", "独立明细", "来源Cxx", "说明",
        ]
    contract_headers, contract_rows = find_table(contract, contract_required)
    contract_actual = assert_required_row_values(
        "调用方与接口契约",
        contract_headers,
        contract_rows,
        "调用方/触发事件",
        contract_required[:1] + contract_required[2:-1],
        errors,
        allow_not_applicable=True,
    )
    for row in contract_actual:
        key = table_cell(contract_headers, row, "调用方/触发事件")
        if key.startswith("不涉及："):
            continue
        d_ids = design_refs(table_cell(contract_headers, row, "设计ID"))
        if len(d_ids) != 1:
            errors.append(f"02-design.md 契约行“{key}”必须且只能绑定一个 Dxx")
        refs = claim_refs(table_cell(contract_headers, row, "来源Cxx"))
        if not refs:
            errors.append(f"02-design.md 契约行“{key}”缺少 Cxx 来源")
        assert_claim_refs_exist(f"02-design.md 契约行“{key}”", refs, eligible_claim_ids, errors)
        if design_schema_version(text) >= 5:
            contract_type = table_cell(contract_headers, row, "契约类型")
            identifier = normalize_contract_identifier(table_cell(contract_headers, row, "契约标识"))
            if contract_type not in CONTRACT_TYPES:
                errors.append(f"02-design.md 契约行“{key}”的契约类型非法: {contract_type}")
            if not identifier:
                errors.append(f"02-design.md 契约行“{key}”缺少契约标识")
            elif contract_type == "HTTP" and not re.fullmatch(
                r"(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+/\S+",
                identifier,
            ):
                errors.append(
                    f"02-design.md HTTP 契约行“{key}”的契约标识必须使用“METHOD /path”"
                )
            trusted = parse_trusted_field_manifest(
                table_cell(contract_headers, row, "后端推导字段/来源"),
                f"02-design.md 契约行“{key}”的后端推导字段/来源",
                errors,
            )
            forbidden = parse_field_manifest(
                table_cell(contract_headers, row, "禁止外部传字段"),
                f"02-design.md 契约行“{key}”的禁止外部传字段",
                errors,
            )
            output = parse_field_manifest(
                table_cell(contract_headers, row, "输出字段"),
                f"02-design.md 契约行“{key}”的输出字段",
                errors,
            )
            side_effects = parse_side_effect_manifest(
                table_cell(contract_headers, row, "副作用"),
                f"02-design.md 契约行“{key}”的副作用",
                errors,
            )
            if not set(trusted).issubset(forbidden):
                missing = sorted(set(trusted) - forbidden)
                errors.append(
                    f"02-design.md 契约行“{key}”的后端推导字段必须禁止外部传入: {', '.join(missing)}"
                )
            if not output and not side_effects:
                errors.append(f"02-design.md 契约行“{key}”必须明确输出字段或真实副作用")
        detail = table_cell(contract_headers, row, "独立明细").strip().strip("`").replace("\\", "/")
        if not (
            (detail.startswith("无需：") and len(detail) > len("无需："))
            or re.fullmatch(r"interface-details/02-interface-\d{2}-.+\.md", detail)
        ):
            errors.append(
                f"02-design.md 契约行“{key}”的独立明细必须填写“无需：具体原因”或合法接口明细路径"
            )

    carrier = extract_section(text, "## 四、数据承载设计")
    carrier_required = [
        "数据/状态", "承载方式", "MySQL", "Redis", "ES", "MQ", "配置/缓存",
        "选择原因", "一致性/过期策略", "来源Cxx",
    ]
    carrier_headers, carrier_rows = find_table(carrier, carrier_required)
    carrier_actual = assert_required_row_values(
        "数据承载设计",
        carrier_headers,
        carrier_rows,
        "数据/状态",
        carrier_required[1:],
        errors,
        allow_not_applicable=True,
    )
    selected_non_mysql: set[str] = set()
    selected_mysql = False
    carrier_type_map = {"Redis": "Redis", "ES": "ES", "MQ": "MQ", "配置/缓存": "配置"}
    for row in carrier_actual:
        key = table_cell(carrier_headers, row, "数据/状态")
        if key.startswith("不涉及："):
            continue
        for flag in ["MySQL", "Redis", "ES", "MQ", "配置/缓存"]:
            if table_cell(carrier_headers, row, flag) not in {"是", "否"}:
                errors.append(f"02-design.md 的数据承载行“{key}”字段 {flag} 必须明确为是或否")
        for flag, carrier_type in carrier_type_map.items():
            if table_cell(carrier_headers, row, flag) == "是":
                selected_non_mysql.add(carrier_type)
        if table_cell(carrier_headers, row, "MySQL") == "是":
            selected_mysql = True
        refs = claim_refs(table_cell(carrier_headers, row, "来源Cxx"))
        if not refs:
            errors.append(f"02-design.md 数据承载行“{key}”缺少 Cxx 来源")
        assert_claim_refs_exist(f"02-design.md 数据承载行“{key}”", refs, eligible_claim_ids, errors)
    if (
        design_schema_version(text) >= 5
        and extract_line_value(text, "- MySQL 结构变更：") == "有"
        and not selected_mysql
    ):
        errors.append("02-design.md 声明有 MySQL 结构变更时，数据承载设计必须至少有一行 MySQL=是")

    detail_required = [
        "类型", "标识（Key / Index / Topic / 配置项）", "数据结构/消息体", "生命周期",
        "一致性/过期策略", "幂等/失败处理", "来源Cxx", "来源Dxx",
    ]
    detail_headers, detail_rows = find_table(carrier, detail_required)
    if not detail_headers and not selected_non_mysql:
        return
    detail_actual = assert_required_row_values(
        "非 MySQL 承载明细",
        detail_headers,
        detail_rows,
        "类型",
        detail_required[1:],
        errors,
        allow_not_applicable=True,
    )
    detailed_types: set[str] = set()
    for row in detail_actual:
        carrier_type = table_cell(detail_headers, row, "类型")
        if carrier_type.startswith("不涉及："):
            if selected_non_mysql:
                errors.append("02-design.md 已选择非 MySQL 承载，不能将承载明细写为不涉及")
            continue
        detailed_types.add("配置" if carrier_type in {"配置", "本地缓存"} else carrier_type)
        refs = claim_refs(table_cell(detail_headers, row, "来源Cxx"))
        if not refs:
            errors.append(f"02-design.md {carrier_type} 承载明细缺少 Cxx 来源")
        assert_claim_refs_exist(f"02-design.md {carrier_type} 承载明细", refs, eligible_claim_ids, errors)
        if not design_refs(table_cell(detail_headers, row, "来源Dxx")):
            errors.append(f"02-design.md {carrier_type} 承载明细缺少来源 Dxx")
    for missing in sorted(selected_non_mysql - detailed_types):
        errors.append(f"02-design.md 数据承载选择了 {missing}，但缺少对应非 MySQL 承载明细")


def assert_minimal_design_gate(text: str, errors: list[str], eligible_claim_ids: set[str] | None) -> None:
    section = extract_section(text, "## 四、数据承载设计")
    required = [
        "设计点", "当前能力/可复用落点", "最小可行方案", "更复杂备选", "不采用复杂方案原因",
        "触发升级条件", "来源Cxx", "对应Dxx",
    ]
    headers, rows = find_table(section, required)
    actual = assert_required_row_values(
        "最小方案与复杂度准入", headers, rows, "设计点", required[1:], errors
    )
    for row in actual:
        key = table_cell(headers, row, "设计点")
        for header in ["当前能力/可复用落点", "最小可行方案", "不采用复杂方案原因", "触发升级条件"]:
            value = table_cell(headers, row, header)
            if vague_design_value(value):
                errors.append(f"02-design.md 的最小方案行“{key}”字段 {header} 过于空泛: {value}")
        refs = claim_refs(table_cell(headers, row, "来源Cxx"))
        if not refs:
            errors.append(f"02-design.md 的最小方案行“{key}”缺少 Cxx 来源引用")
        else:
            assert_claim_refs_exist(f"02-design.md 最小方案行“{key}”", refs, eligible_claim_ids, errors)
        if not design_refs(table_cell(headers, row, "对应Dxx")):
            errors.append(f"02-design.md 的最小方案行“{key}”缺少对应 Dxx")


def assert_sql_minimality_design(text: str, errors: list[str], eligible_claim_ids: set[str] | None) -> None:
    if extract_line_value(text, "- MySQL 结构变更：") != "有":
        return
    section = extract_section(text, "## 五、SQL 表设计")
    tables = [
        (
            "SQL 表准入", "表",
            ["表", "变更类型", "承载业务事实", "现有承载评估", "写入事件", "核心查询", "生命周期",
             "最小方案", "不采用更小方案原因", "来源Cxx", "设计ID"],
            ["现有承载评估", "最小方案", "不采用更小方案原因"], False,
        ),
        (
            "SQL 字段准入", "字段",
            ["表", "字段", "字段性质", "来源/生成规则", "写入时机", "读取/约束场景", "是否可推导",
             "冗余一致性风险", "不落库后果", "来源Cxx", "设计ID"],
            ["来源/生成规则", "读取/约束场景", "冗余一致性风险", "不落库后果"], False,
        ),
        (
            "SQL 索引与约束准入", "表",
            ["表", "索引/约束", "对应查询或约束", "字段顺序依据", "现有索引复用/重复检查", "预期收益",
             "写入/空间成本", "验证方式", "来源Cxx", "设计ID"],
            ["对应查询或约束", "现有索引复用/重复检查", "预期收益", "写入/空间成本", "验证方式"], True,
        ),
    ]
    for label, key_header, required, quality_headers, allow_not_applicable in tables:
        headers, rows = find_table(section, required)
        actual = assert_required_row_values(
            label, headers, rows, key_header, required[1:], errors, allow_not_applicable=allow_not_applicable
        )
        for row in actual:
            key = table_cell(headers, row, key_header)
            if allow_not_applicable and key.startswith("不涉及："):
                continue
            for header in quality_headers:
                value = table_cell(headers, row, header)
                if vague_design_value(value):
                    errors.append(f"02-design.md 的{label}行“{key}”字段 {header} 过于空泛: {value}")
            refs = claim_refs(table_cell(headers, row, "来源Cxx"))
            assert_claim_refs_exist(f"02-design.md {label}行“{key}”", refs, eligible_claim_ids, errors)
            if not design_refs(table_cell(headers, row, "设计ID")):
                errors.append(f"02-design.md 的{label}行“{key}”缺少 Dxx 设计ID")

    compatibility_required = [
        "变更对象", "现有数据/规模", "DDL/锁风险", "历史数据处理", "读写兼容顺序", "回滚边界", "验证方式"
    ]
    compatibility_headers, compatibility_rows = find_table(section, compatibility_required)
    compatibility_actual = assert_required_row_values(
        "SQL 线上变更与兼容", compatibility_headers, compatibility_rows, "变更对象",
        compatibility_required[1:], errors,
    )
    for row in compatibility_actual:
        key = table_cell(compatibility_headers, row, "变更对象")
        for header in compatibility_required[1:]:
            value = table_cell(compatibility_headers, row, header)
            if vague_design_value(value):
                errors.append(f"02-design.md 的 SQL 兼容行“{key}”字段 {header} 过于空泛: {value}")


def assert_sql_design_v4(
    text: str,
    errors: list[str],
    eligible_claim_ids: set[str] | None,
) -> None:
    section = extract_section(text, "## 五、SQL 变更说明")
    mysql_change = extract_line_value(text, "- MySQL 结构变更：")
    if mysql_change == "无":
        reason = extract_line_value(section, "- 无 MySQL 结构变更：")
        if not meaningful_design_value(reason):
            errors.append("02-design.md 无 MySQL 结构变更时必须写明具体原因")
            return
        refs = claim_refs(reason)
        if not refs:
            errors.append("02-design.md 无 MySQL 结构变更原因必须引用至少一个 Cxx")
        assert_claim_refs_exist("02-design.md SQL 无变更说明", refs, eligible_claim_ids, errors)
        return

    if mysql_change != "有":
        return
    if "04-schema.sql" not in section:
        errors.append("02-design.md 有 MySQL 结构变更时必须声明精确结构以 04-schema.sql 为准")

    if design_schema_version(text) >= 5:
        required = [
            "设计ID", "变更对象", "操作", "DDL对象覆盖", "风险等级", "风险依据/执行条件",
            "承载事实/变更理由", "现有结构复用结论", "核心写入/查询",
            "索引/约束依据", "兼容/回滚/验证", "来源Cxx",
        ]
    else:
        required = [
            "设计ID", "变更对象", "承载事实/变更理由", "现有结构复用结论", "核心写入/查询",
            "索引/约束依据", "兼容/回滚/验证", "来源Cxx",
        ]
    headers, rows = find_table(section, required)
    actual = assert_required_row_values(
        "SQL 变更说明",
        headers,
        rows,
        "变更对象",
        required[:1] + required[2:],
        errors,
    )
    for row in actual:
        key = table_cell(headers, row, "变更对象")
        d_ids = design_refs(table_cell(headers, row, "设计ID"))
        if not d_ids:
            errors.append(f"02-design.md SQL 变更“{key}”缺少 Dxx 设计ID")
        refs = claim_refs(table_cell(headers, row, "来源Cxx"))
        if not refs:
            errors.append(f"02-design.md SQL 变更“{key}”缺少 Cxx 来源")
        assert_claim_refs_exist(f"02-design.md SQL 变更“{key}”", refs, eligible_claim_ids, errors)
        for header in required[2:-1]:
            value = table_cell(headers, row, header)
            if vague_design_value(value):
                errors.append(f"02-design.md SQL 变更“{key}”字段 {header} 过于空泛: {value}")
        if design_schema_version(text) >= 5:
            operation = table_cell(headers, row, "操作").strip().lower()
            if operation not in DDL_OPERATIONS:
                errors.append(f"02-design.md SQL 变更“{key}”操作非法: {operation}")
            parse_ddl_members_manifest(
                table_cell(headers, row, "DDL对象覆盖"),
                f"02-design.md SQL 变更“{key}”的 DDL对象覆盖",
                errors,
            )
            risk = table_cell(headers, row, "风险等级")
            if risk not in DDL_RISK_LEVELS:
                errors.append(f"02-design.md SQL 变更“{key}”风险等级必须为普通或高风险")
            risk_reason = table_cell(headers, row, "风险依据/执行条件")
            if not meaningful_design_value(risk_reason) or vague_design_value(risk_reason):
                errors.append(f"02-design.md SQL 变更“{key}”缺少具体风险依据/执行条件")


def parse_ddl_members_manifest(value: str, label: str, errors: list[str]) -> set[str]:
    items = split_manifest_items(value)
    members: set[str] = set()
    for item in items:
        member = normalize_ddl_member(item)
        if member.upper() == "PRIMARY KEY":
            member = "PRIMARY KEY"
        if member != "*" and member != "PRIMARY KEY" and not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_$]*",
            member,
        ):
            errors.append(f"{label} 包含非法字段、索引或约束名: {item}")
            continue
        members.add(member)
    if not items:
        errors.append(f"{label} 必须列出字段、索引和约束名")
    elif len(members) != len(items):
        errors.append(f"{label} 包含空值、非法值或重复值")
    return members


def parse_risk_reason_manifest(value: str, label: str, errors: list[str]) -> set[str]:
    reasons = {
        re.sub(r"\s+", " ", item).strip().rstrip("。")
        for item in re.split(r"[;；]", value)
        if item.strip()
    }
    if not reasons:
        errors.append(f"{label} 必须填写具体风险依据/执行条件")
    for reason in reasons:
        if not meaningful_design_value(reason) or vague_design_value(reason):
            errors.append(f"{label} 包含空泛风险依据: {reason}")
    return reasons


def extract_design_v5_sql_entries(
    text: str,
    errors: list[str],
) -> dict[tuple[str, str], dict[str, object]]:
    section = extract_section(text, "## 五、SQL 变更说明")
    required = [
        "设计ID", "变更对象", "操作", "DDL对象覆盖", "风险等级", "风险依据/执行条件",
        "承载事实/变更理由", "现有结构复用结论", "核心写入/查询",
        "索引/约束依据", "兼容/回滚/验证", "来源Cxx",
    ]
    headers, rows = find_table(section, required)
    result: dict[tuple[str, str], dict[str, object]] = {}
    for row in actual_table_rows(headers, rows, "变更对象"):
        raw_object = table_cell(headers, row, "变更对象")
        ddl_object = normalize_sql_object(raw_object)
        operation = table_cell(headers, row, "操作").strip().lower()
        if not ddl_object or operation not in DDL_OPERATIONS:
            continue
        key = (ddl_object, operation)
        if key in result:
            errors.append(
                f"02-design.md SQL 变更对象 {ddl_object}/{operation} 重复登记，必须合并为一行"
            )
            continue
        result[key] = {
            "object": ddl_object,
            "operation": operation,
            "members": parse_ddl_members_manifest(
                table_cell(headers, row, "DDL对象覆盖"),
                f"02-design.md SQL 变更“{ddl_object}”的 DDL对象覆盖",
                errors,
            ),
            "risk": table_cell(headers, row, "风险等级"),
            "risk_reasons": parse_risk_reason_manifest(
                table_cell(headers, row, "风险依据/执行条件"),
                f"02-design.md SQL 变更“{ddl_object}”的风险依据/执行条件",
                errors,
            ),
            "claims": claim_refs(table_cell(headers, row, "来源Cxx")),
            "designs": design_refs(table_cell(headers, row, "设计ID")),
        }
    return result


def aggregate_sql_v3_entries(
    entries: list[dict[str, object]],
) -> dict[tuple[str, str], dict[str, object]]:
    result: dict[tuple[str, str], dict[str, object]] = {}
    for entry in entries:
        key = (str(entry["object"]), str(entry["operation"]))
        aggregate = result.setdefault(
            key,
            {
                "object": entry["object"],
                "operation": entry["operation"],
                "members": set(),
                "risk": "普通",
                "risk_reasons": set(),
                "claims": set(),
                "designs": set(),
            },
        )
        aggregate["members"].update(entry["members"])  # type: ignore[union-attr]
        risk_reason = re.sub(r"\s+", " ", str(entry["risk_reason"])).strip().rstrip("。")
        aggregate["risk_reasons"].add(risk_reason)  # type: ignore[union-attr]
        aggregate["claims"].update(entry["claims"])  # type: ignore[union-attr]
        aggregate["designs"].update(entry["designs"])  # type: ignore[union-attr]
        if entry["risk"] == "高风险":
            aggregate["risk"] = "高风险"
    return result


def assert_sql_object_closure_v5(
    design_text: str,
    schema_text: str,
    errors: list[str],
) -> list[dict[str, object]]:
    if sql_schema_version(schema_text) < 3:
        errors.append("Design v5 有 MySQL 结构变更时，04-schema.sql 必须升级为 SQL v3")
        return []
    design_entries = extract_design_v5_sql_entries(design_text, errors)
    sql_entries = extract_sql_v3_ddl_entries(schema_text, errors)
    actual_entries = aggregate_sql_v3_entries(sql_entries)

    for key in sorted(set(design_entries) - set(actual_entries)):
        errors.append(f"02-design.md SQL 对象未在 04-schema.sql 闭环: {key[0]}/{key[1]}")
    for key in sorted(set(actual_entries) - set(design_entries)):
        errors.append(f"04-schema.sql DDL 对象未在 02-design.md 闭环: {key[0]}/{key[1]}")
    for key in sorted(set(design_entries) & set(actual_entries)):
        expected = design_entries[key]
        actual = actual_entries[key]
        for field, label in [
            ("members", "DDL对象覆盖"),
            ("risk", "风险等级"),
            ("risk_reasons", "风险依据/执行条件"),
            ("claims", "来源Cxx"),
            ("designs", "设计ID"),
        ]:
            if expected[field] != actual[field]:
                errors.append(
                    f"SQL 对象 {key[0]}/{key[1]} 的{label}在 02-design.md 与 04-schema.sql 不一致:"
                    f" 设计={expected[field]}，SQL={actual[field]}"
                )
    return sql_entries


def assert_design_sequence_choice_v4(text: str, errors: list[str]) -> None:
    section = extract_section(text, "## 七、主链路与依赖")
    choice = extract_line_value(section, "- 时序图：")
    if choice not in {"需要", "不需要"}:
        errors.append("02-design.md 必须明确时序图为“需要”或“不需要”")
        return
    if choice == "需要":
        if "@startuml" not in section:
            errors.append("02-design.md 选择需要时序图，但主链路章节缺少 PlantUML")
        return
    reason = extract_line_value(section, "- 不需要原因：")
    if not meaningful_design_value(reason):
        errors.append("02-design.md 选择不需要时序图时必须写明具体原因")


def assert_design_traceability_v4(
    text: str,
    core_changes: str,
    decisions: str,
    errors: list[str],
    valid_claim_ids: set[str] | None,
) -> None:
    all_claim_refs: set[str] = set()
    if extract_line_value(text, "- MySQL 结构变更：") == "有":
        sql_design = extract_section(text, "## 五、SQL 变更说明")
        _sql_design_refs, sql_claim_refs = assert_traceable_design_rows(
            sql_design,
            "## 五、SQL 变更说明",
            ["设计ID", "来源Cxx"],
            errors,
        )
        all_claim_refs.update(sql_claim_refs)
    _core_design_refs, core_claim_refs = assert_traceable_design_rows(
        core_changes,
        "## 六、核心改动",
        ["设计ID", "来源Cxx"],
        errors,
    )
    _decision_design_refs, decision_claim_refs = assert_traceable_design_rows(
        decisions,
        "## 十三、设计决策记录",
        ["设计ID", "来源Cxx"],
        errors,
    )
    all_claim_refs.update(core_claim_refs)
    all_claim_refs.update(decision_claim_refs)
    assert_claim_refs_exist("02-design.md", all_claim_refs, valid_claim_ids, errors)


def extract_decision_ledger_ids(decisions: str, errors: list[str]) -> set[str]:
    headers, rows = find_table(
        decisions,
        ["设计ID", "决策点", "当前事实/约束", "最小可行选择", "更复杂备选", "不采用复杂方案原因",
         "来源Cxx", "影响/代价", "触发升级条件", "验证方式"],
    )
    if not headers:
        headers, rows = find_table(decisions, ["设计ID", "决策点", "选择", "不选方案", "来源Cxx", "原因", "影响"])
    if not headers:
        return set()
    ids: list[str] = []
    for row in rows:
        value = table_cell(headers, row, "设计ID")
        if re.fullmatch(r"D\d+", value or ""):
            ids.append(value)
    for duplicate in sorted({item for item in ids if ids.count(item) > 1}):
        errors.append(f"02-design.md 设计决策记录编号重复: {duplicate}")
    return set(ids)


def assert_design_decision_quality(text: str, decisions: str, errors: list[str], eligible_claim_ids: set[str] | None) -> None:
    if design_schema_version(text) < 3:
        return
    required = [
        "设计ID", "决策点", "当前事实/约束", "最小可行选择", "更复杂备选", "不采用复杂方案原因",
        "来源Cxx", "影响/代价", "触发升级条件", "验证方式",
    ]
    headers, rows = find_table(decisions, required)
    actual = assert_required_row_values(
        "设计决策记录", headers, rows, "设计ID", required[1:], errors
    )
    for row in actual:
        design_id = table_cell(headers, row, "设计ID")
        if not re.fullmatch(r"D\d+", design_id or ""):
            errors.append(f"02-design.md 的设计决策记录包含非法设计ID: {design_id}")
        for header in ["当前事实/约束", "最小可行选择", "不采用复杂方案原因", "影响/代价", "触发升级条件", "验证方式"]:
            value = table_cell(headers, row, header)
            if vague_design_value(value):
                errors.append(f"02-design.md 的设计决策“{design_id}”字段 {header} 过于空泛: {value}")
        refs = claim_refs(table_cell(headers, row, "来源Cxx"))
        assert_claim_refs_exist(f"02-design.md 设计决策“{design_id}”", refs, eligible_claim_ids, errors)


def assert_design_decision_closure(text: str, decisions: str, errors: list[str]) -> set[str]:
    decision_ids = extract_decision_ledger_ids(decisions, errors)
    all_refs: set[str] = set()
    for headers, rows in iter_markdown_tables(text):
        for header in ["设计ID", "来源Dxx", "对应Dxx/章节", "对应Dxx/章节或原因"]:
            if header not in headers:
                continue
            for row in rows:
                all_refs.update(design_refs(table_cell(headers, row, header)))
    for missing in sorted(all_refs - decision_ids):
        errors.append(f"02-design.md 引用了未在设计决策记录中定义的设计ID: {missing}")
    return decision_ids


def assert_design_quality_v4(
    text: str,
    errors: list[str],
    valid_claim_ids: set[str] | None,
    eligible_claim_ids: set[str] | None,
    transferred_question_ids: set[str] | None,
) -> None:
    input_coverage = extract_section(text, "## 〇、设计输入去向")
    instance_identity = extract_section(text, "## 二、实例身份与可信边界")
    contract_flow = extract_section(text, "## 三、调用方与接口契约")
    data_carrier = extract_section(text, "## 四、数据承载设计")
    sql_design = extract_section(text, "## 五、SQL 变更说明")
    core_changes = extract_section(text, "## 六、核心改动")
    call_chain = extract_section(text, "## 七、主链路与依赖")
    decisions = extract_section(text, "## 十三、设计决策记录")
    test_risk = extract_section(text, "## 十六、测试链路与风险")

    if extract_line_value(text, "- 设计状态：") != "已完成":
        errors.append("02-design.md 完整方案校验要求设计状态为“已完成”")
    if extract_line_value(text, "- MySQL 结构变更：") not in {"有", "无"}:
        errors.append("02-design.md 必须明确 MySQL 结构变更为“有”或“无”")

    for section, heading, min_lines in [
        (input_coverage, "## 〇、设计输入去向", 2),
        (instance_identity, "## 二、实例身份与可信边界", 2),
        (contract_flow, "## 三、调用方与接口契约", 2),
        (data_carrier, "## 四、数据承载设计", 2),
        (sql_design, "## 五、SQL 变更说明", 1),
        (core_changes, "## 六、核心改动", 2),
        (call_chain, "## 七、主链路与依赖", 2),
        (decisions, "## 十三、设计决策记录", 1),
        (test_risk, "## 十六、测试链路与风险", 2),
    ]:
        assert_section_has_substance(section, heading, "02-design.md", errors, min_lines=min_lines)

    assert_design_input_coverage(text, errors, eligible_claim_ids, transferred_question_ids)
    assert_design_precheck_tables_v4(text, errors, eligible_claim_ids)
    assert_sql_design_v4(text, errors, eligible_claim_ids)
    assert_design_sequence_choice_v4(text, errors)
    assert_design_traceability_v4(text, core_changes, decisions, errors, valid_claim_ids)
    assert_design_decision_closure(text, decisions, errors)
    assert_design_decision_quality(text, decisions, errors, eligible_claim_ids)


def assert_design_sql_reference_v6(
    text: str,
    errors: list[str],
    eligible_claim_ids: set[str] | None,
) -> None:
    impact_display = extract_line_value(text, "- SQL 影响类型：").strip()
    impact_type = SQL_IMPACT_TYPES.get(impact_display, "")
    if not impact_type:
        errors.append("02-design.md SQL 影响类型必须为“不涉及 / 查询或DML / DDL”之一")
    source = extract_line_value(text, "- SQL 确认来源：").strip()
    fingerprint = extract_line_value(text, "- SQL 语义指纹：").strip()
    if not meaningful_design_value(source):
        errors.append("02-design.md 缺少已确认 SQL 的用户确认来源")
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        errors.append("02-design.md 缺少合法的 64 位 SQL 语义指纹")

    section = extract_section(text, "## 五、已确认 SQL 引用")
    gate_value = extract_line_value(section, "- SQL Gate：").strip()
    required = [
        "设计ID",
        "SQL ID/对象",
        "SQL 类型",
        "业务理由",
        "代码落点",
        "事务/并发边界",
        "兼容/回滚/验证",
        "来源Cxx",
    ]
    headers, rows = find_table(section, required)
    if not headers:
        errors.append("02-design.md 已确认 SQL 引用表缺少固定表头")
        return
    actual = actual_table_rows(headers, rows, "SQL ID/对象")
    if impact_type == "none":
        if not gate_value.startswith("不涉及：") or len(gate_value) <= len("不涉及："):
            errors.append("02-design.md SQL 不涉及时必须写“SQL Gate：不涉及：具体原因（Cxx）”")
        refs = claim_refs(gate_value)
        if not refs:
            errors.append("02-design.md SQL 不涉及原因必须引用 Cxx")
        assert_claim_refs_exist("02-design.md SQL Gate", refs, eligible_claim_ids, errors)
        if any(
            not table_cell(headers, row, "SQL ID/对象").startswith("不涉及：")
            for row in actual
        ):
            errors.append("02-design.md SQL 不涉及时不能登记真实 SQL 引用")
        return

    if gate_value != "已确认 `sql-draft.sql`" and gate_value != "已确认 sql-draft.sql":
        errors.append("02-design.md 涉及 SQL 时必须声明“SQL Gate：已确认 `sql-draft.sql`”")
    real_rows = [
        row
        for row in actual
        if not table_cell(headers, row, "SQL ID/对象").startswith("不涉及：")
    ]
    if not real_rows:
        errors.append("02-design.md 涉及 SQL 时必须登记至少一条已确认 SQL 引用")
    seen_sql_ids: set[str] = set()
    for row in real_rows:
        key = table_cell(headers, row, "SQL ID/对象")
        sql_ids = set(re.findall(r"\bSQL\d+\b", key))
        if not sql_ids:
            errors.append(f"02-design.md SQL 引用“{key}”缺少 SQL ID")
        for sql_id in sql_ids:
            if sql_id in seen_sql_ids:
                errors.append(f"02-design.md SQL ID 重复引用: {sql_id}")
            seen_sql_ids.add(sql_id)
        d_ids = design_refs(table_cell(headers, row, "设计ID"))
        if len(d_ids) != 1:
            errors.append(f"02-design.md SQL 引用“{key}”必须且只能绑定一个 Dxx")
        refs = claim_refs(table_cell(headers, row, "来源Cxx"))
        if not refs:
            errors.append(f"02-design.md SQL 引用“{key}”缺少 Cxx 来源")
        assert_claim_refs_exist(f"02-design.md SQL 引用“{key}”", refs, eligible_claim_ids, errors)
        sql_type = table_cell(headers, row, "SQL 类型").upper()
        if sql_type not in SQL_DRAFT_TYPES:
            errors.append(f"02-design.md SQL 引用“{key}”类型非法: {sql_type or '空'}")
        for header in required[3:-1]:
            if not meaningful_design_value(table_cell(headers, row, header)):
                errors.append(f"02-design.md SQL 引用“{key}”缺少实质字段: {header}")
    if impact_type == "query_dml" and any(
        table_cell(headers, row, "SQL 类型").upper() == "DDL" for row in real_rows
    ):
        errors.append("02-design.md 查询或DML Gate 不能引用 DDL")
    if impact_type == "ddl" and not any(
        table_cell(headers, row, "SQL 类型").upper() == "DDL" for row in real_rows
    ):
        errors.append("02-design.md DDL Gate 至少需要引用一条 DDL")


def assert_design_interface_index_v6(text: str, errors: list[str]) -> None:
    section = extract_section(text, "## 八、接口设计")
    required = [
        "接口名称",
        "新增/修改",
        "请求方式",
        "路径/方法",
        "所属项目",
        "接口文档地址",
        "备注",
    ]
    headers, rows = find_table(section, required)
    if not headers:
        errors.append("02-design.md 接口设计缺少固定七列表头")
        return
    actual = actual_table_rows(headers, rows, "接口名称")
    no_interface_rows = [
        row
        for row in actual
        if table_cell(headers, row, "接口名称").startswith("不涉及：")
    ]
    real_rows = [row for row in actual if row not in no_interface_rows]
    if no_interface_rows and real_rows:
        errors.append("02-design.md 接口设计不能同时声明不涉及和登记真实接口")
    if len(no_interface_rows) > 1:
        errors.append("02-design.md 接口设计声明不涉及只能保留一行")

    index_identifiers: set[str] = set()
    detail_refs: set[str] = set()
    for row in real_rows:
        name = table_cell(headers, row, "接口名称")
        change = table_cell(headers, row, "新增/修改")
        method = table_cell(headers, row, "请求方式")
        path_or_method = table_cell(headers, row, "路径/方法")
        if change not in {"新增", "修改"}:
            errors.append(f"02-design.md 接口“{name}”新增/修改必须为新增或修改")
        for header in ["请求方式", "路径/方法", "所属项目", "接口文档地址", "备注"]:
            if not meaningful_design_value(table_cell(headers, row, header)):
                errors.append(f"02-design.md 接口“{name}”缺少实质字段: {header}")
        identifier = normalize_contract_identifier(
            f"{method} {path_or_method}"
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
            else path_or_method
        )
        if identifier in index_identifiers:
            errors.append(f"02-design.md 接口设计重复登记路径/方法: {identifier}")
        index_identifiers.add(identifier)
        detail = table_cell(headers, row, "接口文档地址").strip().strip("`").replace("\\", "/")
        if detail.startswith("无需：") and len(detail) > len("无需："):
            continue
        if not re.fullmatch(r"interface-details/02-interface-\d{2}-.+\.md", detail):
            errors.append(f"02-design.md 接口“{name}”的接口文档地址非法: {detail}")
        else:
            detail_refs.add(detail.split("/")[-1])

    contract_section = extract_section(text, "## 三、调用方与接口契约")
    contract_headers, contract_rows = find_table(
        contract_section,
        [
            "设计ID",
            "调用方/触发事件",
            "契约类型",
            "契约标识",
            "输入关键字段",
            "后端推导字段/来源",
            "禁止外部传字段",
            "输出字段",
            "副作用",
            "独立明细",
            "来源Cxx",
            "说明",
        ],
    )
    contract_identifiers = {
        normalize_contract_identifier(table_cell(contract_headers, row, "契约标识"))
        for row in actual_table_rows(contract_headers, contract_rows, "调用方/触发事件")
        if not table_cell(contract_headers, row, "调用方/触发事件").startswith("不涉及：")
    }
    if no_interface_rows and contract_identifiers:
        errors.append("02-design.md 接口设计声明不涉及，但调用方与接口契约仍有真实契约")
    for missing in sorted(contract_identifiers - index_identifiers):
        errors.append(f"02-design.md 接口设计遗漏契约: {missing}")
    for extra in sorted(index_identifiers - contract_identifiers):
        errors.append(f"02-design.md 接口设计包含未在契约主表登记的接口: {extra}")

    # 文件存在性和孤立文档由统一接口闭环校验负责；此处只核对两个主表的地址一致性。
    contract_detail_refs = {
        table_cell(contract_headers, row, "独立明细").strip().strip("`").replace("\\", "/").split("/")[-1]
        for row in actual_table_rows(contract_headers, contract_rows, "调用方/触发事件")
        if re.fullmatch(
            r"interface-details/02-interface-\d{2}-.+\.md",
            table_cell(contract_headers, row, "独立明细").strip().strip("`").replace("\\", "/"),
        )
    }
    if detail_refs != contract_detail_refs:
        errors.append(
            "02-design.md 接口设计的接口文档地址与调用方契约表不一致:"
            f" 接口设计={sorted(detail_refs)}，契约主表={sorted(contract_detail_refs)}"
        )


def assert_design_quality_v6(
    text: str,
    errors: list[str],
    valid_claim_ids: set[str] | None,
    eligible_claim_ids: set[str] | None,
    transferred_question_ids: set[str] | None,
) -> None:
    input_coverage = extract_section(text, "## 〇、设计输入去向")
    instance_identity = extract_section(text, "## 二、实例身份与可信边界")
    contract_flow = extract_section(text, "## 三、调用方与接口契约")
    data_carrier = extract_section(text, "## 四、数据承载设计")
    sql_reference = extract_section(text, "## 五、已确认 SQL 引用")
    core_changes = extract_section(text, "## 六、核心改动")
    call_chain = extract_section(text, "## 七、主链路与依赖")
    interface_index = extract_section(text, "## 八、接口设计")
    decisions = extract_section(text, "## 十三、设计决策记录")
    test_risk = extract_section(text, "## 十六、测试链路与风险")
    if extract_line_value(text, "- 设计状态：") != "已完成":
        errors.append("02-design.md 完整方案校验要求设计状态为“已完成”")
    for section, heading, min_lines in [
        (input_coverage, "## 〇、设计输入去向", 2),
        (instance_identity, "## 二、实例身份与可信边界", 2),
        (contract_flow, "## 三、调用方与接口契约", 2),
        (data_carrier, "## 四、数据承载设计", 2),
        (sql_reference, "## 五、已确认 SQL 引用", 2),
        (core_changes, "## 六、核心改动", 2),
        (call_chain, "## 七、主链路与依赖", 2),
        (interface_index, "## 八、接口设计", 2),
        (decisions, "## 十三、设计决策记录", 1),
        (test_risk, "## 十六、测试链路与风险", 2),
    ]:
        assert_section_has_substance(section, heading, "02-design.md", errors, min_lines=min_lines)
    assert_design_input_coverage(text, errors, eligible_claim_ids, transferred_question_ids)
    assert_design_precheck_tables_v4(text, errors, eligible_claim_ids)
    assert_design_sequence_choice_v4(text, errors)
    for prefix in [
        "- 异常与失败边界：",
        "- 业务日志：",
        "- Trace 链路：",
    ]:
        value = extract_line_value(call_chain, prefix).strip()
        if (
            not meaningful_design_value(value)
            or value == "不涉及"
            or re.fullmatch(r"不涉及[：:]具体原因(?:\s*/.*)?", value)
        ):
            errors.append(
                f"02-design.md 主链路缺少实质设计: {prefix.rstrip('：')}"
            )
    assert_design_sql_reference_v6(text, errors, eligible_claim_ids)
    assert_design_interface_index_v6(text, errors)
    assert_design_traceability_v4(
        text,
        core_changes,
        decisions,
        errors,
        valid_claim_ids,
    )
    assert_design_decision_closure(text, decisions, errors)
    assert_design_decision_quality(text, decisions, errors, eligible_claim_ids)


def assert_design_quality(
    text: str,
    errors: list[str],
    valid_claim_ids: set[str] | None = None,
    eligible_claim_ids: set[str] | None = None,
    transferred_question_ids: set[str] | None = None,
) -> None:
    if design_schema_version(text) >= 6:
        assert_design_quality_v6(
            text,
            errors,
            valid_claim_ids,
            eligible_claim_ids,
            transferred_question_ids,
        )
        return
    if design_schema_version(text) >= 4:
        assert_design_quality_v4(
            text,
            errors,
            valid_claim_ids,
            eligible_claim_ids,
            transferred_question_ids,
        )
        return

    strict = design_schema_version(text) >= 2
    input_coverage = extract_section(text, "## 〇、设计输入覆盖清单")
    instance_identity = extract_section(text, "## 二、实例身份与状态隔离")
    contract_flow = extract_section(text, "## 三、前后端接口协作流")
    data_carrier = extract_section(text, "## 四、数据承载设计")
    sql_design = extract_section(text, "## 五、SQL 表设计")
    core_changes = extract_section(text, "## 六、核心改动")
    call_chain = extract_section(text, "## 七、主链路与依赖")
    interface_design = extract_section(text, "## 八、接口设计")
    decisions = extract_section(text, "## 十三、设计决策记录")
    test_risk = extract_section(text, "## 十六、测试链路与风险")

    if strict:
        if extract_line_value(text, "- 设计状态：") != "已完成":
            errors.append("02-design.md 完整方案校验要求设计状态为“已完成”")
        if extract_line_value(text, "- MySQL 结构变更：") not in {"有", "无"}:
            errors.append("02-design.md 必须明确 MySQL 结构变更为“有”或“无”")
        assert_section_has_substance(input_coverage, "## 〇、设计输入覆盖清单", "02-design.md", errors, min_lines=2)
        assert_design_input_coverage(text, errors, eligible_claim_ids, transferred_question_ids)
        assert_design_precheck_tables(text, errors, eligible_claim_ids)
        if design_schema_version(text) == 3:
            assert_minimal_design_gate(text, errors, eligible_claim_ids)
            assert_sql_minimality_design(text, errors, eligible_claim_ids)

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
    if strict:
        assert_design_decision_closure(text, decisions, errors)
        assert_design_decision_quality(text, decisions, errors, eligible_claim_ids)


def interface_basic_info(text: str) -> dict[str, str]:
    section = extract_section(text, "## 1. 基本信息")
    headers, rows = find_table(section, ["项", "内容"])
    return {
        table_cell(headers, row, "项"): table_cell(headers, row, "内容")
        for row in rows
        if table_cell(headers, row, "项")
    }


def normalized_interface_info(text: str) -> dict[str, str]:
    """将 Interface v4 的统一接口索引字段映射为既有契约闭包字段。"""
    info = interface_basic_info(text)
    if interface_schema_version(text) < 4:
        return info
    method = info.get("请求方式", "").strip()
    path_or_method = info.get("路径/方法", "").strip()
    identifier = (
        f"{method} {path_or_method}"
        if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
        else path_or_method
    )
    normalized = dict(info)
    normalized["契约名称"] = info.get("接口名称", "")
    normalized["新增 / 修改"] = info.get("新增/修改", "")
    normalized["契约标识"] = normalize_contract_identifier(identifier)
    return normalized


def assert_json_example(
    section: str,
    label: str,
    errors: list[str],
    allow_null: bool = False,
    allow_empty: bool = False,
) -> object | None:
    matches = re.findall(r"```json\s*(.*?)```", section, re.DOTALL)
    if not matches:
        errors.append(f"{label} 缺少 JSON 示例")
        return None
    raw = matches[0].strip()
    if any(token in raw for token in ['"fieldA"', '"fieldB"', '"value"']):
        errors.append(f"{label} 仍是模板 JSON 示例")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        errors.append(f"{label} JSON 示例无法解析: {exc.msg}")
        return None
    if value is None and allow_null:
        return value
    if allow_empty and isinstance(value, (dict, list)) and not value:
        return value
    if not isinstance(value, dict) or not value:
        errors.append(f"{label} JSON 示例必须是非空对象")
    return value


def json_field_paths(value: object, prefix: str = "") -> set[str]:
    if not isinstance(value, dict):
        return set()
    paths: set[str] = set()
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        paths.add(path)
        paths.update(json_field_paths(child, path))
    return paths


def assert_parameter_table(section: str, label: str, required_headers: list[str], errors: list[str]) -> None:
    headers, rows = find_table(section, required_headers)
    if not headers:
        errors.append(f"{label} 缺少参数表或关键表头")
        return
    actual = actual_table_rows(headers, rows, required_headers[0])
    if not actual:
        errors.append(f"{label} 缺少真实参数行或明确的不涉及原因")
        return
    for row in actual:
        key = table_cell(headers, row, required_headers[0])
        if key.startswith("不涉及：") and len(key) > len("不涉及："):
            continue
        for header in required_headers[1:]:
            if not meaningful_design_value(table_cell(headers, row, header)):
                errors.append(f"{label} 参数“{key}”缺少实质字段: {header}")


def assert_interface_detail_quality(path: Path, text: str, errors: list[str]) -> None:
    label = path.name
    if not INTERFACE_DETAIL_FILENAME.fullmatch(path.name):
        errors.append(f"{label} 命名不规范，推荐使用 02-interface-01-主题.md")
    version = interface_schema_version(text)
    required_tokens = (
        INTERFACE_DETAIL_V4_REQUIRED_TOKENS
        if version >= 4
        else INTERFACE_DETAIL_V3_REQUIRED_TOKENS
        if version >= 3
        else INTERFACE_DETAIL_REQUIRED_TOKENS
    )
    assert_contains(text, required_tokens, label, errors)
    assert_no_unresolved_placeholders(text, label, errors)
    assert_no_design_residuals(text, label, errors)
    if interface_schema_version(text) < 2:
        return
    if interface_schema_version(text) >= 3:
        assert_interface_detail_quality_v3(path, text, errors)
        return

    info = interface_basic_info(text)
    for key in ["设计ID", "来源Cxx", "接口名称", "新增 / 修改", "所属项目", "接口类型", "请求方式", "接口路径 / 方法", "调用方", "处理入口"]:
        if not meaningful_design_value(info.get(key, "")):
            errors.append(f"{label} 基本信息缺少实质内容: {key}")
    if not re.fullmatch(r"D\d+", info.get("设计ID", "")):
        errors.append(f"{label} 基本信息的设计ID必须是单个 Dxx")
    if not claim_refs(info.get("来源Cxx", "")):
        errors.append(f"{label} 基本信息缺少 Cxx 来源")

    contract = extract_section(text, "## 2. 契约与参数")
    request = extract_section(contract, "### 2.1 请求参数表")
    response = extract_section(contract, "### 2.2 响应参数表")
    assert_parameter_table(
        request,
        f"{label} 请求参数",
        ["字段", "位置", "类型", "必填", "示例值", "来源", "是否后端推导", "前端是否允许传", "说明"],
        errors,
    )
    assert_parameter_table(response, f"{label} 响应参数", ["字段", "类型", "说明"], errors)
    request_json = assert_json_example(
        extract_section(contract, "### 2.3 请求 JSON 示例"), f"{label} 请求", errors, allow_null=True
    )
    response_json = assert_json_example(
        extract_section(contract, "### 2.4 响应 JSON 示例"), f"{label} 响应", errors
    )
    request_headers, request_rows = find_table(
        request,
        ["字段", "位置", "类型", "必填", "示例值", "来源", "是否后端推导", "前端是否允许传", "说明"],
    )
    expected_request_fields = {
        table_cell(request_headers, row, "字段")
        for row in request_rows
        if table_cell(request_headers, row, "位置") == "Body"
        and table_cell(request_headers, row, "是否后端推导") == "否"
        and table_cell(request_headers, row, "前端是否允许传") == "是"
    }
    request_paths = json_field_paths(request_json)
    for field in sorted(expected_request_fields - request_paths):
        errors.append(f"{label} 请求 JSON 缺少请求参数表字段: {field}")
    for field in sorted(request_paths - expected_request_fields):
        errors.append(f"{label} 请求 JSON 字段未在请求参数表中闭环: {field}")

    response_headers, response_rows = find_table(response, ["字段", "类型", "说明"])
    expected_response_fields = {
        table_cell(response_headers, row, "字段")
        for row in response_rows
        if meaningful_design_value(table_cell(response_headers, row, "字段"))
        and not table_cell(response_headers, row, "字段").startswith("不涉及：")
    }
    response_paths = json_field_paths(response_json)
    for field in sorted(expected_response_fields - response_paths):
        errors.append(f"{label} 响应 JSON 缺少响应参数表字段: {field}")
    for field in sorted(response_paths - expected_response_fields):
        errors.append(f"{label} 响应 JSON 字段未在响应参数表中闭环: {field}")
    for prefix in ["- 参数校验：", "- 后端自动推导字段：", "- 前端禁止传字段：", "- 关键业务规则：", "- 兼容旧参数 / 旧返回结构："]:
        if not meaningful_design_value(extract_line_value(contract, prefix)):
            errors.append(f"{label} 缺少契约闭环说明: {prefix.rstrip('：')}")


def interface_v3_contract_snapshot(
    text: str,
    label: str,
    errors: list[str],
) -> dict[str, object]:
    version = interface_schema_version(text)
    info = normalized_interface_info(text)
    contract = extract_section(text, "## 2. 契约与参数")
    request = extract_section(contract, "### 2.1 请求参数表")
    response = extract_section(contract, "### 2.2 响应参数表")
    request_required_headers = (
        [
            "字段", "位置", "Java 类型", "JSON 类型", "必填", "可空/空值语义",
            "示例值", "来源", "是否后端推导", "外部是否允许传", "说明",
        ]
        if version >= 4
        else [
            "字段", "位置", "类型", "必填", "示例值", "来源",
            "是否后端推导", "外部是否允许传", "说明",
        ]
    )
    request_headers, request_rows = find_table(
        request,
        request_required_headers,
    )
    actual_request = actual_table_rows(request_headers, request_rows, "字段")
    trusted: dict[str, str] = {}
    forbidden: set[str] = set()
    input_fields: set[str] = set()
    request_json_fields: set[str] = set()
    no_request = False
    for row in actual_request:
        field = table_cell(request_headers, row, "字段")
        if field.startswith("不涉及：") and len(field) > len("不涉及："):
            no_request = True
            continue
        input_fields.add(field)
        derived = table_cell(request_headers, row, "是否后端推导")
        external = table_cell(request_headers, row, "外部是否允许传")
        source = table_cell(request_headers, row, "来源")
        if version >= 4:
            required = table_cell(request_headers, row, "必填")
            if required not in {"是", "否"}:
                errors.append(f"{label} 请求字段 {field} 的必填必须为是或否")
            null_semantics = table_cell(request_headers, row, "可空/空值语义")
            if null_semantics in {"可空", "不适用", "按需", "视情况"}:
                errors.append(f"{label} 请求字段 {field} 的可空/空值语义必须写明具体含义")
        if derived not in {"是", "否"}:
            errors.append(f"{label} 请求字段 {field} 的是否后端推导必须为是或否")
        if external not in {"是", "否"}:
            errors.append(f"{label} 请求字段 {field} 的外部是否允许传必须为是或否")
        if derived == "是":
            if external != "否":
                errors.append(f"{label} 后端推导字段 {field} 必须禁止外部传入")
            if not meaningful_design_value(source):
                errors.append(f"{label} 后端推导字段 {field} 缺少可信来源")
            else:
                trusted[field] = source
        if external == "否":
            forbidden.add(field)
        if (
            table_cell(request_headers, row, "位置") in {"Body", "Message"}
            and derived == "否"
            and external == "是"
        ):
            request_json_fields.add(field)
    if no_request and len(actual_request) > 1:
        errors.append(f"{label} 请求参数声明不涉及时不能同时登记真实字段")

    response_required_headers = (
        ["字段", "Java 类型", "JSON 类型", "必返", "可空/空值语义", "说明"]
        if version >= 4
        else ["字段", "类型", "说明"]
    )
    response_headers, response_rows = find_table(response, response_required_headers)
    actual_response = actual_table_rows(response_headers, response_rows, "字段")
    no_response = any(
        table_cell(response_headers, row, "字段").startswith("不涉及：")
        and len(table_cell(response_headers, row, "字段")) > len("不涉及：")
        for row in actual_response
    )
    if no_response and len(actual_response) > 1:
        errors.append(f"{label} 响应参数声明不涉及时不能同时登记真实字段")
    if version >= 4:
        for row in actual_response:
            field = table_cell(response_headers, row, "字段")
            if field.startswith("不涉及："):
                continue
            if table_cell(response_headers, row, "必返") not in {"是", "否"}:
                errors.append(f"{label} 响应字段 {field} 的必返必须为是或否")
            null_semantics = table_cell(response_headers, row, "可空/空值语义")
            if null_semantics in {"可空", "不适用", "按需", "视情况"}:
                errors.append(f"{label} 响应字段 {field} 的可空/空值语义必须写明具体含义")
    output = {
        table_cell(response_headers, row, "字段")
        for row in actual_response
        if not table_cell(response_headers, row, "字段").startswith("不涉及：")
    }
    side_effects = parse_side_effect_manifest(
        extract_line_value(contract, "- 输出副作用："),
        f"{label} 输出副作用",
        errors,
    )
    return {
        "info": info,
        "trusted": trusted,
        "forbidden": forbidden,
        "input": input_fields,
        "request_json_fields": request_json_fields,
        "no_request": no_request,
        "output": output,
        "no_response": no_response,
        "side_effects": side_effects,
    }


def assert_interface_detail_quality_v3(path: Path, text: str, errors: list[str]) -> None:
    label = path.name
    info = normalized_interface_info(text)
    required_info = (
        [
            "设计ID", "来源Cxx", "接口名称", "新增/修改", "请求方式",
            "路径/方法", "所属项目", "接口文档地址", "备注",
            "契约类型", "调用方 / 触发事件", "处理入口",
        ]
        if interface_schema_version(text) >= 4
        else [
            "设计ID", "来源Cxx", "契约名称", "新增 / 修改", "所属项目",
            "契约类型", "契约标识", "调用方 / 触发事件", "处理入口",
        ]
    )
    for key in required_info:
        if not meaningful_design_value(info.get(key, "")):
            errors.append(f"{label} 基本信息缺少实质内容: {key}")
    if not re.fullmatch(r"D\d+", info.get("设计ID", "")):
        errors.append(f"{label} 基本信息的设计ID必须是单个 Dxx")
    if not claim_refs(info.get("来源Cxx", "")):
        errors.append(f"{label} 基本信息缺少 Cxx 来源")
    if interface_schema_version(text) >= 4:
        if info.get("新增/修改") not in {"新增", "修改"}:
            errors.append(f"{label} 基本信息的新增/修改必须为新增或修改")
        if info.get("接口文档地址", "").strip().strip("`") != (
            f"interface-details/{path.name}"
        ):
            errors.append(f"{label} 基本信息的接口文档地址必须指向当前文档")
    contract_type = info.get("契约类型", "")
    identifier = normalize_contract_identifier(info.get("契约标识", ""))
    if contract_type not in CONTRACT_TYPES:
        errors.append(f"{label} 基本信息的契约类型非法: {contract_type}")
    if contract_type == "HTTP" and identifier and not re.fullmatch(
        r"(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+/\S+",
        identifier,
    ):
        errors.append(f"{label} HTTP 契约标识必须使用“METHOD /path”")

    contract = extract_section(text, "## 2. 契约与参数")
    request = extract_section(contract, "### 2.1 请求参数表")
    response = extract_section(contract, "### 2.2 响应参数表")
    request_headers = (
        [
            "字段", "位置", "Java 类型", "JSON 类型", "必填", "可空/空值语义",
            "示例值", "来源", "是否后端推导", "外部是否允许传", "说明",
        ]
        if interface_schema_version(text) >= 4
        else [
            "字段", "位置", "类型", "必填", "示例值", "来源",
            "是否后端推导", "外部是否允许传", "说明",
        ]
    )
    response_headers = (
        ["字段", "Java 类型", "JSON 类型", "必返", "可空/空值语义", "说明"]
        if interface_schema_version(text) >= 4
        else ["字段", "类型", "说明"]
    )
    assert_parameter_table(request, f"{label} 请求参数", request_headers, errors)
    assert_parameter_table(response, f"{label} 响应参数", response_headers, errors)
    snapshot = interface_v3_contract_snapshot(text, label, errors)

    request_json = assert_json_example(
        extract_section(contract, "### 2.3 请求 JSON 示例"),
        f"{label} 请求",
        errors,
        allow_null=True,
        allow_empty=True,
    )
    expected_request = snapshot["request_json_fields"]
    request_paths = json_field_paths(request_json)
    if expected_request and not request_paths:
        errors.append(f"{label} 存在外部请求体字段时，请求 JSON 不能为 null 或空集合")
    for field in sorted(expected_request - request_paths):  # type: ignore[operator]
        errors.append(f"{label} 请求 JSON 缺少请求参数表字段: {field}")
    for field in sorted(request_paths - expected_request):  # type: ignore[operator]
        errors.append(f"{label} 请求 JSON 字段未在请求参数表中闭环: {field}")

    response_json = assert_json_example(
        extract_section(contract, "### 2.4 响应 JSON 示例"),
        f"{label} 响应",
        errors,
        allow_null=bool(snapshot["no_response"]),
        allow_empty=bool(snapshot["no_response"]),
    )
    response_paths = json_field_paths(response_json)
    expected_response = snapshot["output"]
    if snapshot["no_response"]:
        if response_paths:
            errors.append(f"{label} 已声明无同步响应，响应 JSON 必须为 null 或空集合")
    else:
        if not expected_response:
            errors.append(f"{label} 响应参数表必须登记字段或写“不涉及：具体原因”")
        for field in sorted(expected_response - response_paths):  # type: ignore[operator]
            errors.append(f"{label} 响应 JSON 缺少响应参数表字段: {field}")
        for field in sorted(response_paths - expected_response):  # type: ignore[operator]
            errors.append(f"{label} 响应 JSON 字段未在响应参数表中闭环: {field}")

    closure_prefixes = ["- 参数校验："]
    if interface_schema_version(text) >= 4:
        closure_prefixes.append("- 数值精度与序列化：")
    closure_prefixes.extend(
        ["- 关键业务规则：", "- 兼容旧契约：", "- 输出副作用："]
    )
    for prefix in closure_prefixes:
        if not meaningful_design_value(extract_line_value(contract, prefix)):
            errors.append(f"{label} 缺少契约闭环说明: {prefix.rstrip('：')}")


def assert_interface_closure(
    interface_design: str,
    interface_details: Path,
    errors: list[str],
    valid_design_ids: set[str],
    eligible_claim_ids: set[str] | None,
) -> None:
    required = ["设计ID", "接口名称", "新增/修改", "请求方式", "路径/方法", "所属项目", "首屏/点击后/提交后", "后端自动推导", "前端禁止传", "接口文档地址", "来源Cxx", "备注"]
    headers, rows = find_table(interface_design, required)
    if not headers:
        errors.append("02-design.md 接口总表缺少闭环表头")
        return
    actual = actual_table_rows(headers, rows, "接口名称")
    if not actual:
        errors.append("02-design.md 接口总表缺少真实接口行；不涉及接口时必须写明具体原因")
        return

    expected_files: dict[str, tuple[str, set[str], str, str]] = {}
    no_interface = False
    for row in actual:
        name = table_cell(headers, row, "接口名称")
        if name.startswith("不涉及：") and len(name) > len("不涉及："):
            no_interface = True
            continue
        for header in required:
            if header in {"备注"}:
                continue
            if not meaningful_design_value(table_cell(headers, row, header)):
                errors.append(f"02-design.md 接口“{name}”缺少实质字段: {header}")
        d_ids = design_refs(table_cell(headers, row, "设计ID"))
        c_ids = claim_refs(table_cell(headers, row, "来源Cxx"))
        if len(d_ids) != 1:
            errors.append(f"02-design.md 接口“{name}”必须且只能绑定一个 Dxx")
        assert_design_refs_exist(f"02-design.md 接口“{name}”", d_ids, valid_design_ids, errors)
        assert_claim_refs_exist(f"02-design.md 接口“{name}”", c_ids, eligible_claim_ids, errors)
        raw_path = table_cell(headers, row, "接口文档地址").strip().strip("`").replace("\\", "/")
        if not re.fullmatch(r"interface-details/02-interface-\d{2}-.+\.md", raw_path):
            errors.append(f"02-design.md 接口“{name}”的接口文档地址非法: {raw_path}")
            continue
        filename = raw_path.split("/")[-1]
        if filename in expected_files:
            errors.append(f"02-design.md 多个接口重复引用同一明细文档: {filename}")
        expected_files[filename] = (
            next(iter(d_ids), ""),
            c_ids,
            table_cell(headers, row, "后端自动推导"),
            table_cell(headers, row, "前端禁止传"),
        )

    actual_files = set()
    if interface_details.exists() and interface_details.is_dir():
        actual_files = {path.name for path in interface_details.glob("*.md")}
    if no_interface and (expected_files or actual_files):
        errors.append("02-design.md 接口总表声明不涉及接口，但仍存在接口行或接口明细")
    for missing in sorted(set(expected_files) - actual_files):
        errors.append(f"02-design.md 接口总表引用的明细文档不存在: {missing}")
    for orphan in sorted(actual_files - set(expected_files)):
        errors.append(f"interface-details/ 存在未被接口总表引用的孤立文档: {orphan}")

    for filename in sorted(set(expected_files) & actual_files):
        detail_path = interface_details / filename
        detail_text = read_text(detail_path)
        info = interface_basic_info(detail_text)
        expected_d, expected_c, expected_derived, expected_forbidden = expected_files[filename]
        if info.get("设计ID") != expected_d:
            errors.append(f"{filename} 的设计ID与接口总表不一致")
        if claim_refs(info.get("来源Cxx", "")) != expected_c:
            errors.append(f"{filename} 的来源Cxx与接口总表不一致")
        contract = extract_section(detail_text, "## 2. 契约与参数")
        detail_derived = extract_line_value(contract, "- 后端自动推导字段：")
        detail_forbidden = extract_line_value(contract, "- 前端禁止传字段：")
        if expected_derived not in {"无", "不涉及", "-"} and expected_derived not in detail_derived:
            errors.append(f"{filename} 未闭环接口总表中的后端自动推导字段: {expected_derived}")
        if expected_forbidden not in {"无", "不涉及", "-"} and expected_forbidden not in detail_forbidden:
            errors.append(f"{filename} 未闭环接口总表中的前端禁止传字段: {expected_forbidden}")


def assert_interface_closure_v4(
    contract: str,
    interface_details: Path,
    errors: list[str],
    valid_design_ids: set[str],
    eligible_claim_ids: set[str] | None,
) -> None:
    required = [
        "设计ID", "调用方/触发事件", "接口/消息/任务", "类型", "输入关键字段",
        "后端推导/可信边界", "输出结果", "独立明细", "来源Cxx", "说明",
    ]
    headers, rows = find_table(contract, required)
    if not headers:
        errors.append("02-design.md 调用方与接口契约表缺少闭环表头")
        return
    actual = actual_table_rows(headers, rows, "调用方/触发事件")
    if not actual:
        errors.append("02-design.md 调用方与接口契约表缺少真实行或明确的不涉及原因")
        return

    expected_files: dict[str, tuple[str, set[str]]] = {}
    no_contract = False
    for row in actual:
        caller = table_cell(headers, row, "调用方/触发事件")
        if caller.startswith("不涉及：") and len(caller) > len("不涉及："):
            no_contract = True
            continue
        d_ids = design_refs(table_cell(headers, row, "设计ID"))
        c_ids = claim_refs(table_cell(headers, row, "来源Cxx"))
        assert_design_refs_exist(f"02-design.md 契约“{caller}”", d_ids, valid_design_ids, errors)
        assert_claim_refs_exist(f"02-design.md 契约“{caller}”", c_ids, eligible_claim_ids, errors)
        detail = table_cell(headers, row, "独立明细").strip().strip("`").replace("\\", "/")
        if detail.startswith("无需：") and len(detail) > len("无需："):
            continue
        if not re.fullmatch(r"interface-details/02-interface-\d{2}-.+\.md", detail):
            errors.append(f"02-design.md 契约“{caller}”的接口明细地址非法: {detail}")
            continue
        filename = detail.split("/")[-1]
        if filename in expected_files:
            errors.append(f"02-design.md 多个契约重复引用同一明细文档: {filename}")
        expected_files[filename] = (next(iter(d_ids), ""), c_ids)

    actual_files: set[str] = set()
    if interface_details.exists() and interface_details.is_dir():
        actual_files = {path.name for path in interface_details.glob("*.md")}
    if no_contract and (expected_files or actual_files):
        errors.append("02-design.md 声明不涉及接口/消息/任务，但仍存在契约行或接口明细")
    for missing in sorted(set(expected_files) - actual_files):
        errors.append(f"02-design.md 契约表引用的明细文档不存在: {missing}")
    for orphan in sorted(actual_files - set(expected_files)):
        errors.append(f"interface-details/ 存在未被契约表引用的孤立文档: {orphan}")

    for filename in sorted(set(expected_files) & actual_files):
        info = interface_basic_info(read_text(interface_details / filename))
        expected_d, expected_c = expected_files[filename]
        if info.get("设计ID") != expected_d:
            errors.append(f"{filename} 的设计ID与契约表不一致")
        if claim_refs(info.get("来源Cxx", "")) != expected_c:
            errors.append(f"{filename} 的来源Cxx与契约表不一致")


def assert_interface_closure_v5(
    contract: str,
    interface_details: Path,
    errors: list[str],
    valid_design_ids: set[str],
    eligible_claim_ids: set[str] | None,
) -> None:
    required = [
        "设计ID", "调用方/触发事件", "契约类型", "契约标识", "输入关键字段",
        "后端推导字段/来源", "禁止外部传字段", "输出字段", "副作用",
        "独立明细", "来源Cxx", "说明",
    ]
    headers, rows = find_table(contract, required)
    if not headers:
        errors.append("02-design.md 调用方与接口契约表缺少 Design v5 闭环表头")
        return
    actual = actual_table_rows(headers, rows, "调用方/触发事件")
    if not actual:
        errors.append("02-design.md 调用方与接口契约表缺少真实行或明确的不涉及原因")
        return

    expected_files: dict[str, dict[str, object]] = {}
    no_contract = False
    has_real_contract = False
    for row in actual:
        caller = table_cell(headers, row, "调用方/触发事件")
        if caller.startswith("不涉及：") and len(caller) > len("不涉及："):
            no_contract = True
            continue
        has_real_contract = True
        d_ids = design_refs(table_cell(headers, row, "设计ID"))
        c_ids = claim_refs(table_cell(headers, row, "来源Cxx"))
        assert_design_refs_exist(f"02-design.md 契约“{caller}”", d_ids, valid_design_ids, errors)
        assert_claim_refs_exist(f"02-design.md 契约“{caller}”", c_ids, eligible_claim_ids, errors)
        detail = table_cell(headers, row, "独立明细").strip().strip("`").replace("\\", "/")
        if detail.startswith("无需：") and len(detail) > len("无需："):
            continue
        if not re.fullmatch(r"interface-details/02-interface-\d{2}-.+\.md", detail):
            errors.append(f"02-design.md 契约“{caller}”的接口明细地址非法: {detail}")
            continue
        filename = detail.split("/")[-1]
        if filename in expected_files:
            errors.append(f"02-design.md 多个契约重复引用同一明细文档: {filename}")
            continue
        expected_files[filename] = {
            "design": next(iter(d_ids), ""),
            "claims": c_ids,
            "caller": normalize_contract_identifier(caller),
            "type": table_cell(headers, row, "契约类型"),
            "identifier": normalize_contract_identifier(table_cell(headers, row, "契约标识")),
            "input": parse_field_manifest(
                table_cell(headers, row, "输入关键字段"),
                f"02-design.md 契约“{caller}”的输入关键字段",
                errors,
            ),
            "trusted": parse_trusted_field_manifest(
                table_cell(headers, row, "后端推导字段/来源"),
                f"02-design.md 契约“{caller}”的后端推导字段/来源",
                errors,
            ),
            "forbidden": parse_field_manifest(
                table_cell(headers, row, "禁止外部传字段"),
                f"02-design.md 契约“{caller}”的禁止外部传字段",
                errors,
            ),
            "output": parse_field_manifest(
                table_cell(headers, row, "输出字段"),
                f"02-design.md 契约“{caller}”的输出字段",
                errors,
            ),
            "side_effects": parse_side_effect_manifest(
                table_cell(headers, row, "副作用"),
                f"02-design.md 契约“{caller}”的副作用",
                errors,
            ),
        }

    actual_files: set[str] = set()
    if interface_details.exists() and interface_details.is_dir():
        actual_files = {path.name for path in interface_details.glob("*.md")}
    if no_contract and (has_real_contract or actual_files):
        errors.append("02-design.md 声明不涉及契约，但仍存在契约行或接口明细")
    for missing in sorted(set(expected_files) - actual_files):
        errors.append(f"02-design.md 契约表引用的明细文档不存在: {missing}")
    for orphan in sorted(actual_files - set(expected_files)):
        errors.append(f"interface-details/ 存在未被契约表引用的孤立文档: {orphan}")

    for filename in sorted(set(expected_files) & actual_files):
        detail_text = read_text(interface_details / filename)
        if interface_schema_version(detail_text) < 3:
            errors.append(f"{filename} 被 Design v5 引用时必须升级为 Interface v3")
            continue
        snapshot = interface_v3_contract_snapshot(detail_text, filename, errors)
        info = snapshot["info"]
        expected = expected_files[filename]
        comparisons = [
            ("设计ID", expected["design"], info.get("设计ID", "")),
            ("来源Cxx", expected["claims"], claim_refs(info.get("来源Cxx", ""))),
            (
                "调用方/触发事件",
                expected["caller"],
                normalize_contract_identifier(info.get("调用方 / 触发事件", "")),
            ),
            ("契约类型", expected["type"], info.get("契约类型", "")),
            (
                "契约标识",
                expected["identifier"],
                normalize_contract_identifier(info.get("契约标识", "")),
            ),
            ("输入关键字段", expected["input"], snapshot["input"]),
            ("后端推导字段/来源", expected["trusted"], snapshot["trusted"]),
            ("禁止外部传字段", expected["forbidden"], snapshot["forbidden"]),
            ("输出字段", expected["output"], snapshot["output"]),
            ("副作用", expected["side_effects"], snapshot["side_effects"]),
        ]
        for field, main_value, detail_value in comparisons:
            if main_value != detail_value:
                errors.append(
                    f"{filename} 的{field}与 02-design.md 契约主表不一致:"
                    f" 主表={main_value}，明细={detail_value}"
                )


def source_refs(value: str) -> tuple[set[str], set[str], bool, bool, bool]:
    return (
        design_refs(value),
        claim_refs(value),
        "interface-details/" in value or "interface-details\\" in value,
        "04-schema.sql" in value,
        "sql-draft.sql" in value,
    )


def assert_source_value_traceability(
    label: str,
    source: str,
    errors: list[str],
    valid_design_ids: set[str] | None = None,
    valid_claim_ids: set[str] | None = None,
    schema_exists: bool = False,
    sql_draft_exists: bool = False,
) -> None:
    source = source.strip()
    d_refs, c_refs, has_interface_ref, has_schema_ref, has_sql_draft_ref = source_refs(
        source
    )
    if not source or source in {"-", "无", "不涉及"}:
        errors.append(f"{label} 缺少来源依据")
        return
    if not d_refs:
        errors.append(
            f"{label} 来源依据必须引用至少一个核心改动 Dxx；"
            "Cxx、interface-details、sql-draft.sql 和 04-schema.sql 只能作为补充依据"
        )
    assert_design_refs_exist(label, d_refs, valid_design_ids, errors)
    assert_claim_refs_exist(label, c_refs, valid_claim_ids, errors)
    if has_schema_ref and not schema_exists:
        errors.append(f"{label} 引用了 04-schema.sql，但当前需求目录未发现该文件")
    if has_sql_draft_ref and not sql_draft_exists:
        errors.append(f"{label} 引用了 sql-draft.sql，但当前需求目录未发现该文件")


def assert_task_source_traceability(
    overview: str,
    errors: list[str],
    valid_design_ids: set[str] | None = None,
    valid_claim_ids: set[str] | None = None,
    schema_exists: bool = False,
    required_core_design_ids: set[str] | None = None,
    sql_draft_exists: bool = False,
) -> set[str]:
    headers, rows = extract_first_table(overview)
    if "来源依据" not in headers:
        errors.append("03-tasks.md 任务总览缺少来源依据列")
        return set()

    covered_design_ids: set[str] = set()
    for row in rows:
        task_id = table_cell(headers, row, "编号")
        if not re.fullmatch(r"T\d+", task_id or ""):
            continue
        source = table_cell(headers, row, "来源依据")
        task_design_ids = design_refs(source)
        covered_design_ids.update(task_design_ids)
        assert_source_value_traceability(
            f"03-tasks.md {task_id}",
            source,
            errors,
            valid_design_ids,
            valid_claim_ids,
            schema_exists,
            sql_draft_exists,
        )
        if required_core_design_ids and not (task_design_ids & required_core_design_ids):
            errors.append(f"03-tasks.md {task_id} 未关联 02-design.md 核心改动中的 Dxx")
    return covered_design_ids


def task_detail_blocks(detail: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"(?m)^###\s+(T\d+)\b.*$", detail))
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(detail)
        blocks.append((match.group(1), detail[match.start():end].strip()))
    return blocks


def task_dependencies(value: str) -> set[str]:
    return set(re.findall(r"\bT\d+\b", value))


def assert_task_dependency_graph(
    task_ids: list[str],
    dependencies: dict[str, set[str]],
    errors: list[str],
) -> None:
    known = set(task_ids)
    for task_id, refs in dependencies.items():
        if task_id in refs:
            errors.append(f"03-tasks.md {task_id} 不能依赖自身")
        for ref in sorted(refs - known):
            errors.append(f"03-tasks.md {task_id} 依赖不存在的任务: {ref}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str, path: list[str]) -> None:
        if task_id in visiting:
            cycle_start = path.index(task_id) if task_id in path else 0
            cycle = path[cycle_start:] + [task_id]
            errors.append(f"03-tasks.md 任务依赖存在循环: {' -> '.join(cycle)}")
            return
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in sorted(dependencies.get(task_id, set())):
            if dependency in known:
                visit(dependency, path + [task_id])
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in task_ids:
        visit(task_id, [])


def assert_task_name_is_code_work(
    task_id: str,
    name: str,
    errors: list[str],
    require_explicit_test_deliverable: bool = True,
) -> None:
    normalized = re.sub(r"\s+", "", name)
    if normalized in {"开发接口", "实现逻辑", "代码开发", "修改代码", "测试一下", "功能开发"}:
        errors.append(f"03-tasks.md {task_id} 开发任务过于笼统: {name}")

    forbidden_patterns = [
        r"发布|上线|灰度|发布单|联调协调",
        r"回滚(?:准备|方案|检查|演练)",
        r"执行.*(?:DDL|SQL|数据回填)",
        r"(?:Nacos|环境).*(?:配置|准备|操作)",
        r"(?:接口|回归|系统|验收|冒烟)?测试(?:执行|验证|报告)$",
    ]
    if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in forbidden_patterns):
        errors.append(f"03-tasks.md {task_id} 不是仓库编码任务: {name}")
    if require_explicit_test_deliverable and "测试" in normalized and not any(
        token in normalized for token in ["代码", "桩", "用例", "工具", "基座", "Fixture", "数据工厂"]
    ):
        errors.append(f"03-tasks.md {task_id} 测试任务必须明确产生测试代码: {name}")


def assert_task_detail_quality(
    detail: str,
    overview_rows: dict[str, dict[str, str]],
    errors: list[str],
) -> None:
    blocks = task_detail_blocks(detail)
    detail_ids = [task_id for task_id, _ in blocks]
    duplicates = sorted({task_id for task_id in detail_ids if detail_ids.count(task_id) > 1})
    if duplicates:
        errors.append(f"03-tasks.md 任务详情编号重复: {', '.join(duplicates)}")

    overview_ids = set(overview_rows)
    detail_id_set = set(detail_ids)
    missing = sorted(overview_ids - detail_id_set)
    extra = sorted(detail_id_set - overview_ids)
    if missing:
        errors.append(f"03-tasks.md 任务详情缺少任务: {', '.join(missing)}")
    if extra:
        errors.append(f"03-tasks.md 任务详情包含总览中不存在的任务: {', '.join(extra)}")

    required_labels = [
        "来源依据", "所属项目", "依赖任务", "预计修改文件/符号",
        "主要实现内容", "代码边界", "完成标准",
    ]

    def list_field_value(block: str, label: str) -> str:
        match = re.search(
            rf"(?ms)^-\s*{re.escape(label)}[：:]\s*(.*?)(?=^-\s*[^\n：:]+[：:]|\Z)",
            block,
        )
        if not match:
            return ""
        values = [
            re.sub(r"^\s*-\s*", "", line).strip()
            for line in match.group(1).splitlines()
            if re.sub(r"^\s*-\s*", "", line).strip()
        ]
        return "\n".join(values)

    for task_id, block in blocks:
        for label in required_labels:
            if not re.search(rf"(?m)^\s*-\s*{re.escape(label)}[：:]", block):
                errors.append(f"03-tasks.md {task_id} 任务详情缺少字段: {label}")

        source = extract_line_value(block, "- 来源依据：")
        if not source or source in {"-", "无", "不涉及"}:
            errors.append(f"03-tasks.md {task_id} 任务详情 缺少来源依据")

        row = overview_rows.get(task_id)
        if row is None:
            continue
        comparisons = {
            "来源依据": source,
            "所属项目": extract_line_value(block, "- 所属项目："),
            "依赖任务": extract_line_value(block, "- 依赖任务："),
            "预计修改文件/符号": extract_line_value(block, "- 预计修改文件/符号："),
        }
        for field, detail_value in comparisons.items():
            if detail_value != row.get(field, ""):
                errors.append(f"03-tasks.md {task_id} 的{field}在任务总览和详情中不一致")
        for field in ["主要实现内容", "代码边界", "完成标准"]:
            if not list_field_value(block, field):
                errors.append(f"03-tasks.md {task_id} 任务详情的{field}不能为空")


def assert_tasks_quality(
    text: str,
    errors: list[str],
    interface_details: Path | None = None,
    valid_design_ids: set[str] | None = None,
    valid_claim_ids: set[str] | None = None,
    schema_exists: bool = False,
    required_core_design_ids: set[str] | None = None,
) -> None:
    sequence = extract_section(text, "## 2. 拆分方式和执行顺序")
    overview = extract_section(text, "## 3. 编码任务")
    detail = extract_section(text, "## 4. 任务详情")
    done = extract_section(text, "## 5. 完成定义")
    assert_regex_exists(
        text,
        r"\|\s*T\d+\s*\|",
        "03-tasks.md 缺少已填写的任务行",
        errors,
    )
    required_headers = ["编号", "开发任务", "来源依据", "所属项目", "预计修改文件/符号", "依赖任务", "完成标准"]
    headers, rows = extract_first_table(overview)
    for token in required_headers:
        if token not in headers:
            errors.append(f"03-tasks.md 编码任务表缺少列: {token}")
    assert_regex_exists(
        overview,
        r"\|\s*T\d+\s*\|",
        "03-tasks.md 编码任务表缺少结构化任务行",
        errors,
    )

    task_ids: list[str] = []
    overview_rows: dict[str, dict[str, str]] = {}
    dependencies: dict[str, set[str]] = {}
    for row in rows:
        task_id = table_cell(headers, row, "编号")
        if not re.fullmatch(r"T\d+", task_id or ""):
            continue
        task_ids.append(task_id)
        values = {header: table_cell(headers, row, header).strip() for header in required_headers}
        if task_id not in overview_rows:
            overview_rows[task_id] = values

        for field in ["开发任务", "来源依据", "所属项目", "预计修改文件/符号", "完成标准"]:
            if values[field] in {"", "-", "无", "待定", "未知", "TBD"}:
                errors.append(f"03-tasks.md {task_id} 缺少有效的{field}")

        assert_task_name_is_code_work(task_id, values["开发任务"], errors)
        if values["完成标准"] in {"完成", "功能正常", "编译通过", "测试通过", "开发完成"}:
            errors.append(f"03-tasks.md {task_id} 完成标准过于笼统: {values['完成标准']}")

        dependency_value = values["依赖任务"]
        if dependency_value in {"", "无"}:
            errors.append(f"03-tasks.md {task_id} 无依赖时必须填写 -")
        remaining = re.sub(r"\bT\d+\b", "", dependency_value)
        remaining = re.sub(r"[\s,，、/;；-]", "", remaining)
        if remaining:
            errors.append(f"03-tasks.md {task_id} 依赖任务只能填写 Txx 或 -: {dependency_value}")
        dependencies[task_id] = task_dependencies(dependency_value)

    duplicate_ids = sorted({task_id for task_id in task_ids if task_ids.count(task_id) > 1})
    if duplicate_ids:
        errors.append(f"03-tasks.md 编码任务编号重复: {', '.join(duplicate_ids)}")

    covered_design_ids = assert_task_source_traceability(
        overview,
        errors,
        valid_design_ids,
        valid_claim_ids,
        schema_exists,
        required_core_design_ids,
    )
    if required_core_design_ids:
        missing_design_ids = sorted(required_core_design_ids - covered_design_ids)
        if missing_design_ids:
            errors.append(
                f"03-tasks.md 遗漏 02-design.md 核心改动: {', '.join(missing_design_ids)}"
            )
    assert_task_dependency_graph(task_ids, dependencies, errors)
    assert_task_detail_quality(
        detail,
        overview_rows,
        errors,
    )
    assert_section_has_substance(detail, "## 4. 任务详情", "03-tasks.md", errors, min_lines=8)

    recommended_order = extract_line_value(sequence, "- 推荐执行顺序：")
    order_ids = re.findall(r"\bT\d+\b", recommended_order)
    if set(order_ids) != set(task_ids) or len(order_ids) != len(task_ids):
        errors.append("03-tasks.md 推荐执行顺序必须且只能覆盖全部编码任务")

    if interface_details is not None and interface_details.exists() and interface_details.is_dir():
        for detail_file in sorted(interface_details.glob("*.md")):
            if detail_file.name not in text and detail_file.stem not in text:
                errors.append(f"03-tasks.md 缺少接口明细对应编码任务: {detail_file.name}")
    if schema_exists and not any("04-schema.sql" in row.get("来源依据", "") for row in overview_rows.values()):
        errors.append("03-tasks.md 存在 04-schema.sql，但没有编码任务覆盖 SQL 文件及持久化代码")
    assert_section_has_substance(done, "## 5. 完成定义", "03-tasks.md", errors, min_lines=3)


def task_detail_field_value(block: str, label: str) -> str:
    match = re.search(
        rf"(?ms)^-\s*{re.escape(label)}[：:]\s*(.*?)(?=^-\s*[^\n：:]+[：:]|\Z)",
        block,
    )
    if not match:
        return ""
    values = [
        re.sub(r"^\s*-\s*", "", line).strip()
        for line in match.group(1).splitlines()
        if re.sub(r"^\s*-\s*", "", line).strip()
    ]
    return "\n".join(values)


def task_completion_item_values(block: str, label: str) -> list[str]:
    """提取“完成标准”的直接子项；保留重复项，以便调用方拒绝歧义。"""
    lines = block.splitlines()
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if re.match(r"^-\s*完成标准[：:]", line)
        ),
        None,
    )
    if start is None:
        return []

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if re.match(r"^-\s*[^\n：:]+[：:]", lines[index]):
            end = index
            break

    body = lines[start + 1:end]
    bullets: list[tuple[int, int, str]] = []
    for index, line in enumerate(body):
        match = re.match(r"^([ \t]+)-[ \t]*(.*)$", line)
        if match:
            bullets.append((index, len(match.group(1).expandtabs(4)), match.group(2)))
    if not bullets:
        return []

    direct_indent = min(indent for _index, indent, _content in bullets)
    values: list[str] = []
    for bullet_index, (line_index, indent, content) in enumerate(bullets):
        if indent != direct_indent:
            continue
        header = re.fullmatch(
            rf"{re.escape(label)}[：:][ \t]*(.*)",
            content,
        )
        if not header:
            continue

        value_end = len(body)
        for next_line_index, next_indent, _next_content in bullets[bullet_index + 1:]:
            if next_line_index > line_index and next_indent <= direct_indent:
                value_end = next_line_index
                break

        parts = [header.group(1).strip()] if header.group(1).strip() else []
        for raw in body[line_index + 1:value_end]:
            stripped = re.sub(r"^[-*+]\s*", "", raw.strip())
            if stripped:
                parts.append(stripped)
        values.append("\n".join(parts))
    return values


def normalized_task_completion_value(value: str) -> str:
    normalized = re.sub(r"[`*_]", "", value)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized.strip("。；;，,")


def task_necessary_test_has_substance(value: str) -> bool:
    normalized = normalized_task_completion_value(value)
    if normalized in {
        "", "-", "无", "无需", "不需要", "待定", "未知", "同上", "按需",
        "测试", "测试代码", "补充测试", "已覆盖", "不涉及",
    }:
        return False
    if "不涉及：具体原因/" in normalized or "不涉及:具体原因/" in normalized:
        return False
    if normalized.startswith(("不涉及", "无需新增测试", "不新增测试")):
        match = re.match(
            r"^(?:不涉及|无需新增测试(?:代码)?|不新增测试(?:代码)?)[：:](.+)$",
            normalized,
        )
        if not match:
            return False
        reason = match.group(1).strip("。；;，,")
        if len(reason) < 4 or reason == "具体原因":
            return False
        return not re.search(
            r"低风险|改动简单|用户(?:未|没有)要求|时间不足|来不及",
            reason,
        )
    return len(normalized) >= 4


def task_v3_test_code_policy(value: str) -> tuple[str, str]:
    """返回 v3 测试代码策略及错误原因；默认明确不新增测试代码。"""
    normalized = normalized_task_completion_value(value)
    if normalized == "默认不新增":
        return "default_none", ""
    match = re.match(r"^用户明确要求[：:](.+)$", value.strip(), re.DOTALL)
    if not match:
        return "", "必须填写“默认不新增”或“用户明确要求：具体内容＋授权来源”"
    detail = match.group(1).strip()
    normalized_detail = normalized_task_completion_value(detail)
    if (
        len(normalized_detail) < 10
        or "具体测试类、测试桩、数据构造或用例场景＋授权来源" in detail
        or not re.search(r"授权|用户消息|用户要求|用户确认", detail)
    ):
        return "", "用户明确要求测试代码时必须写清具体测试内容和可回查授权来源"
    return "user_authorized", ""


def task_code_result_has_substance(value: str) -> bool:
    normalized = normalized_task_completion_value(value)
    if len(normalized) < 6 or normalized in {
        "", "-", "无", "待定", "未知", "同上", "按需",
        "完成", "代码完成", "开发完成", "功能正常", "实现完成",
    }:
        return False
    if re.fullmatch(
        r"(?:代码|功能|开发|实现|任务|改动|需求|方案)?"
        r"(?:已|已经)?"
        r"(?:完成|完毕|正常|实现|开发|修改完成|开发完成|实现完成|完成开发|完成实现)",
        normalized,
    ):
        return False
    return not re.fullmatch(
        r"(?:完成|实现)(?:对应|相关|上述|本任务|本次)?"
        r"(?:代码|功能|开发|实现|任务|改动|需求)",
        normalized,
    )


def task_minimum_verification_has_substance(value: str) -> bool:
    normalized = normalized_task_completion_value(value)
    if normalized in {
        "", "-", "无", "无需", "不需要", "不涉及", "待定", "未知", "同上", "按需",
        "验证", "验证通过", "测试", "测试通过", "运行测试", "执行测试",
        "人工确认", "代码审查确认", "编译通过", "构建通过", "功能正常", "开发完成",
        "验证功能正常", "具体命令、测试类/用例或静态检查及预期结果",
    }:
        return False
    if re.fullmatch(
        r"(?:运行|执行|调用|请求|检查|校验|验证|编译|构建|启动)"
        r"(?:(?:所有|全部|相关|对应|必要|单元|集成|契约|回归|冒烟|"
        r"端到端|系统|验收|接口|功能|业务|目标|本任务|本次))*"
        r"(?:测试|测试用例|用例|测试类|接口|功能|功能行为)"
        r"(?:的)?(?:(?:并)?(?:检查|确认|验证))?"
        r"(?:响应|返回|返回结果|结果|行为|状态|是否)?"
        r"(?:通过|正常|正确|符合预期|无误|成功)?",
        normalized,
    ):
        return False
    command = re.search(
        r"(?i)(?:^|[\s`./])(?:mvnw?|gradlew?|npm|pnpm|yarn|pytest|python\d*|"
        r"go|cargo|make|bazel|git|ruff|eslint|tsc|mypy|checkstyle)"
        r"(?:\s+|:)[^\s`]+",
        value,
    )
    if command:
        return True

    action = re.search(
        r"(?:运行|执行|调用|请求|检查|校验|验证|编译|构建|启动)",
        normalized,
    )
    concrete_target = re.search(
        r"\b[A-Za-z_][A-Za-z0-9_]*(?:Test|Tests|TestCase|Spec)\b"
        r"|(?:[\w.-]+/)+[\w.-]+"
        r"|[\w.-]+\.(?i:java|kt|groovy|py|ts|tsx|js|jsx|sql|xml|ya?ml|json)\b"
        r"|(?i:POST|GET|PUT|PATCH|DELETE)\s+\S+"
        r"|[\w.$]+#[\w$]+"
        r"|(?:[\u4e00-\u9fffA-Za-z0-9_]{2,})(?:测试类|用例|接口)"
        r"|(?i:spotless(?::check|Check)|checkstyle|ruff|eslint|tsc|mypy|lint)",
        value,
    )
    return bool(action and concrete_target)


def task_artifacts(value: str) -> list[str]:
    return [
        token.strip().strip("`")
        for token in re.split(r"(?:<br\s*/?>|[\n,，;；、]+)", value, flags=re.IGNORECASE)
        if token.strip().strip("`")
    ]


def is_test_artifact(value: str) -> bool:
    normalized = value.replace("\\", "/")
    lowered = normalized.lower()
    filename = normalized.rsplit("/", 1)[-1]
    return bool(
        re.search(
            r"(?:^|/)(?:test|tests|__tests__|testdata|testfixtures|test[-_]?support|"
            r"fixtures?|mocks?|stubs?)(?:/|$)",
            lowered,
        )
        or re.search(r"\.(?:test|spec)\.[^.]+$", filename.lower())
        or re.search(
            r"(?:^|[_-])(?:test|tests|testcase|spec|fixture|mock|stub)(?:[_-]|\.[^.]+$)",
            filename,
            re.IGNORECASE,
        )
        or re.search(
            r"(?:Test|Tests|TestCase|Spec|IT|Fixture|Mock|Stub)"
            r"(?=\.[A-Za-z0-9]+$|[#:.]|$)",
            filename,
        )
    )


def task_name_has_test_deliverable(name: str) -> bool:
    if re.search(
        r"(?:测试(?:代码|用例|桩|工具|基座)|"
        r"(?:单元|集成|契约|回归|冒烟|端到端)测试"
        r"(?:代码|用例|桩|工具|基座)?|回归用例|测试数据工厂)"
        r"(?:能力|资产)?$",
        name,
        re.IGNORECASE,
    ):
        return True
    return bool(
        re.search(
            r"\b[A-Za-z_][A-Za-z0-9_]*(?:Test|Tests|TestCase|Spec)\b|"
            r"\b(?:Fixture|Mock|Stub)\b",
            name,
        )
    )


def task_has_reusable_test_capability(
    task_name: str,
    files: str,
    implementation: str,
    boundary: str,
) -> bool:
    """独立测试任务必须同时说明资产类型与多消费者复用范围。"""
    context = "\n".join([task_name, files, implementation, boundary])
    reuse_context = "\n".join([implementation, boundary])
    asset_pattern = re.compile(
        r"测试基座|契约测试工具|共享\s*Fixture|通用(?:测试)?数据工厂|"
        r"共享测试桩|可复用测试工具|test[-_ ]support",
        re.IGNORECASE,
    )
    negated_asset = re.search(
        r"(?:不|未|不能|无法|不是|并非).{0,12}"
        r"(?:测试基座|契约测试工具|共享\s*Fixture|通用(?:测试)?数据工厂|"
        r"共享测试桩|可复用测试工具)",
        context,
        re.IGNORECASE,
    )
    if not asset_pattern.search(context) or negated_asset:
        return False

    multi_consumer = re.search(
        r"(?:多个|至少(?:两|二|2)个|两个|跨(?:模块|项目|服务|仓库))"
        r"[^。；;\n]{0,40}(?:复用|共享|共用|使用)"
        r"|(?:供|由)[^。；;\n]{1,24}(?:、|，|,|和|及|与)"
        r"[^。；;\n]{1,24}(?:复用|共享|共用|使用)",
        reuse_context,
        re.IGNORECASE,
    )
    negated_reuse = re.search(
        r"(?:不|未|不能|无法|不是|并非|仅供当前|只供当前|仅供单一|只供单一)"
        r".{0,16}(?:多个|两个|跨模块|跨项目|复用|共享|共用|使用)",
        reuse_context,
        re.IGNORECASE,
    )
    return bool(multi_consumer and not negated_reuse)


def assert_tasks_quality_v2(
    text: str,
    errors: list[str],
    interface_details: Path | None = None,
    valid_design_ids: set[str] | None = None,
    valid_claim_ids: set[str] | None = None,
    schema_exists: bool = False,
    required_core_design_ids: set[str] | None = None,
    sql_draft_exists: bool = False,
) -> None:
    version = task_schema_version(text)
    overview = extract_section(text, "## 3. 任务总览")
    detail = extract_section(text, "## 4. 任务详情")
    done = extract_section(text, "## 5. 完成定义")
    if "推荐执行顺序" in text:
        errors.append("03-tasks.md v2 不再维护推荐执行顺序；执行顺序由依赖关系决定")
    if version >= 3:
        strategy = extract_line_value(text, "- 测试代码策略：").strip()
        if strategy == "默认不新增":
            pass
        elif re.match(r"^用户明确要求[：:（(].+", strategy):
            if (
                "记录用户消息定位" in strategy
                or not re.search(r"用户消息|用户要求|用户确认|授权", strategy)
            ):
                errors.append("03-tasks.md v3 测试代码策略缺少可回查的用户授权来源")
        else:
            errors.append(
                "03-tasks.md v3 测试代码策略必须为“默认不新增”"
                "或记录用户明确要求及授权来源"
            )

    required_headers = ["编号", "开发任务", "所属项目", "依赖任务"]
    headers, rows = extract_first_table(overview)
    for header in required_headers:
        if header not in headers:
            errors.append(f"03-tasks.md 任务总览缺少列: {header}")
    for duplicate_header in ["来源依据", "预计修改文件/符号", "完成标准"]:
        if duplicate_header in headers:
            errors.append(f"03-tasks.md v2 的任务总览不应重复维护字段: {duplicate_header}")
    assert_regex_exists(
        overview,
        r"\|\s*T\d+\s*\|",
        "03-tasks.md 任务总览缺少结构化任务行",
        errors,
    )

    task_ids: list[str] = []
    overview_rows: dict[str, dict[str, str]] = {}
    dependencies: dict[str, set[str]] = {}
    for row in rows:
        task_id = table_cell(headers, row, "编号")
        if not re.fullmatch(r"T\d+", task_id or ""):
            continue
        task_ids.append(task_id)
        values = {header: table_cell(headers, row, header).strip() for header in required_headers}
        if task_id not in overview_rows:
            overview_rows[task_id] = values
        for field in ["开发任务", "所属项目"]:
            if values[field] in {"", "-", "无", "待定", "未知", "TBD"}:
                errors.append(f"03-tasks.md {task_id} 缺少有效的{field}")
        assert_task_name_is_code_work(
            task_id,
            values["开发任务"],
            errors,
            require_explicit_test_deliverable=False,
        )
        dependency_value = values["依赖任务"]
        if dependency_value in {"", "无"}:
            errors.append(f"03-tasks.md {task_id} 无依赖时必须填写 -")
        remaining = re.sub(r"\bT\d+\b", "", dependency_value)
        remaining = re.sub(r"[\s,，、/;；-]", "", remaining)
        if remaining:
            errors.append(f"03-tasks.md {task_id} 依赖任务只能填写 Txx 或 -: {dependency_value}")
        dependencies[task_id] = task_dependencies(dependency_value)

    duplicates = sorted({task_id for task_id in task_ids if task_ids.count(task_id) > 1})
    if duplicates:
        errors.append(f"03-tasks.md 编码任务编号重复: {', '.join(duplicates)}")
    assert_task_dependency_graph(task_ids, dependencies, errors)

    blocks = task_detail_blocks(detail)
    detail_ids = [task_id for task_id, _block in blocks]
    detail_duplicates = sorted({task_id for task_id in detail_ids if detail_ids.count(task_id) > 1})
    if detail_duplicates:
        errors.append(f"03-tasks.md 任务详情编号重复: {', '.join(detail_duplicates)}")
    missing_details = sorted(set(task_ids) - set(detail_ids))
    extra_details = sorted(set(detail_ids) - set(task_ids))
    if missing_details:
        errors.append(f"03-tasks.md 任务详情缺少任务: {', '.join(missing_details)}")
    if extra_details:
        errors.append(f"03-tasks.md 任务详情包含总览中不存在的任务: {', '.join(extra_details)}")

    required_labels = ["来源依据", "预计修改文件/符号", "主要实现内容", "代码边界", "完成标准"]
    covered_design_ids: set[str] = set()
    for task_id, block in blocks:
        for repeated in ["所属项目", "依赖任务"]:
            if re.search(rf"(?m)^\s*-\s*{re.escape(repeated)}[：:]", block):
                errors.append(f"03-tasks.md v2 的 {task_id} 详情不应重复维护{repeated}")
        for label in required_labels:
            if not re.search(rf"(?m)^\s*-\s*{re.escape(label)}[：:]", block):
                errors.append(f"03-tasks.md {task_id} 任务详情缺少字段: {label}")

        source = extract_line_value(block, "- 来源依据：")
        assert_source_value_traceability(
            f"03-tasks.md {task_id}",
            source,
            errors,
            valid_design_ids,
            valid_claim_ids,
            schema_exists,
            sql_draft_exists,
        )
        task_design_ids = design_refs(source)
        covered_design_ids.update(task_design_ids)
        if required_core_design_ids and not (task_design_ids & required_core_design_ids):
            errors.append(f"03-tasks.md {task_id} 未关联 02-design.md 核心改动中的 Dxx")

        files = task_detail_field_value(block, "预计修改文件/符号")
        implementation = task_detail_field_value(block, "主要实现内容")
        boundary = task_detail_field_value(block, "代码边界")
        completion = task_detail_field_value(block, "完成标准")
        for label, value in [
            ("预计修改文件/符号", files),
            ("主要实现内容", implementation),
            ("代码边界", boundary),
            ("完成标准", completion),
        ]:
            if not meaningful_design_value(value):
                errors.append(f"03-tasks.md {task_id} 任务详情的{label}不能为空")
        if completion.strip() in {"完成", "功能正常", "编译通过", "测试通过", "开发完成"}:
            errors.append(f"03-tasks.md {task_id} 完成标准过于笼统: {completion}")

        task_name = overview_rows.get(task_id, {}).get("开发任务", "")
        code_result_items = task_completion_item_values(block, "代码结果与关键行为")
        test_code_label = "测试代码" if version >= 3 else "必要测试代码"
        necessary_items = task_completion_item_values(block, test_code_label)
        minimum_verification_items = task_completion_item_values(block, "最小验证")
        code_result = code_result_items[0] if len(code_result_items) == 1 else ""
        necessary_test = necessary_items[0] if len(necessary_items) == 1 else ""
        minimum_verification = (
            minimum_verification_items[0]
            if len(minimum_verification_items) == 1
            else ""
        )
        if not code_result_items:
            errors.append(f"03-tasks.md {task_id} 完成标准缺少直接子项: 代码结果与关键行为")
        elif len(code_result_items) > 1:
            errors.append(f"03-tasks.md {task_id} 完成标准的代码结果与关键行为子项重复")
        elif not task_code_result_has_substance(code_result):
            errors.append(f"03-tasks.md {task_id} 完成标准缺少实质的代码结果与关键行为")

        if not necessary_items:
            errors.append(
                f"03-tasks.md {task_id} 完成标准缺少直接子项: {test_code_label}"
            )
        elif len(necessary_items) > 1:
            errors.append(
                f"03-tasks.md {task_id} 完成标准的{test_code_label}子项重复"
            )
        elif version >= 3:
            _policy, policy_error = task_v3_test_code_policy(necessary_test)
            if policy_error:
                errors.append(
                    f"03-tasks.md {task_id} 测试代码策略非法: {policy_error}"
                )
        elif not task_necessary_test_has_substance(necessary_test):
            if normalized_task_completion_value(necessary_test).startswith("不涉及"):
                errors.append(
                    f"03-tasks.md {task_id} 必要测试代码写“不涉及”时必须附具体原因"
                )
            else:
                errors.append(f"03-tasks.md {task_id} 完成标准缺少实质的必要测试代码")

        if not minimum_verification_items:
            errors.append(f"03-tasks.md {task_id} 完成标准缺少直接子项: 最小验证")
        elif len(minimum_verification_items) > 1:
            errors.append(f"03-tasks.md {task_id} 完成标准的最小验证子项重复")
        elif not task_minimum_verification_has_substance(minimum_verification):
            errors.append(f"03-tasks.md {task_id} 完成标准缺少可执行的最小验证")

        risk_text = "\n".join([task_name, source, files, implementation, boundary])
        risk_pattern = re.compile(
            r"状态机|状态流转|事务|权限|鉴权|公共契约|interface-details/|"
            r"04-schema\.sql|\bSQL\b|\bMQ\b|异步|幂等|重试|补偿|Bug|修复",
            re.IGNORECASE,
        )
        if (
            version < 3
            and risk_pattern.search(risk_text)
            and normalized_task_completion_value(necessary_test).startswith("不涉及")
        ):
            errors.append(
                f"03-tasks.md {task_id} 涉及高风险行为，必要测试代码不能写不涉及"
            )

        artifacts = task_artifacts(files)
        if version >= 3 and len(necessary_items) == 1:
            test_policy, _policy_error = task_v3_test_code_policy(necessary_test)
            has_test_artifact = any(is_test_artifact(artifact) for artifact in artifacts)
            if test_policy == "default_none" and has_test_artifact:
                errors.append(
                    f"03-tasks.md {task_id} 声明默认不新增测试代码，但预计修改文件包含测试资产"
                )
            if test_policy == "user_authorized" and not has_test_artifact:
                errors.append(
                    f"03-tasks.md {task_id} 声明用户明确要求测试代码，但预计修改文件未包含测试资产"
                )
        production_artifacts = [
            artifact for artifact in artifacts if not is_test_artifact(artifact)
        ]
        standalone_test = bool(
            (artifacts and not production_artifacts)
            or task_name_has_test_deliverable(task_name)
        )
        if standalone_test and not task_has_reusable_test_capability(
            task_name,
            files,
            implementation,
            boundary,
        ):
            errors.append(
                f"03-tasks.md {task_id} 默认不应单拆测试任务；"
                "独立测试能力必须同时写明测试资产类型和至少两个复用方或跨模块复用范围"
            )

    if required_core_design_ids:
        missing_design_ids = sorted(required_core_design_ids - covered_design_ids)
        if missing_design_ids:
            errors.append(f"03-tasks.md 遗漏 02-design.md 核心改动: {', '.join(missing_design_ids)}")

    if interface_details is not None and interface_details.exists() and interface_details.is_dir():
        for detail_file in sorted(interface_details.glob("*.md")):
            if detail_file.name not in detail and detail_file.stem not in detail:
                errors.append(f"03-tasks.md 缺少接口明细对应编码任务: {detail_file.name}")
    sql_artifact_name = (
        "sql-draft.sql"
        if sql_draft_exists
        else "04-schema.sql"
        if schema_exists
        else ""
    )
    if sql_artifact_name:
        schema_blocks = [
            (task_id, block)
            for task_id, block in blocks
            if sql_artifact_name in block
        ]
        if not schema_blocks:
            errors.append(
                f"03-tasks.md 存在 {sql_artifact_name}，但没有任务覆盖 SQL 文件及持久化代码"
            )
        else:
            persistence_pattern = re.compile(
                r"(?:Mapper|Repository|DAO|Entity|JdbcTemplate|DSLContext|MyBatis|JPA|"
                r"(?:^|[/_.-])(?:DO|PO)(?:$|[/_.-])|持久化|数据访问|仓储)",
                re.IGNORECASE,
            )
            if not any(
                persistence_pattern.search(task_detail_field_value(block, "预计修改文件/符号"))
                for _task_id, block in schema_blocks
            ):
                errors.append(
                    f"03-tasks.md 已引用 {sql_artifact_name}，但对应任务缺少 "
                    "Mapper/Repository/Entity 等持久化代码落点"
                )

    assert_section_has_substance(detail, "## 4. 任务详情", "03-tasks.md", errors, min_lines=6)
    assert_section_has_substance(done, "## 5. 完成定义", "03-tasks.md", errors, min_lines=3)


def schema_comment_value(text: str, label: str) -> str:
    match = re.search(rf"(?mi)^\s*--\s*{re.escape(label)}\s*[：:]\s*(.*?)\s*$", text)
    return match.group(1).strip() if match else ""


def assert_schema_quality(
    text: str,
    errors: list[str],
    valid_claim_ids: set[str] | None = None,
    valid_design_ids: set[str] | None = None,
) -> None:
    version = sql_schema_version(text)
    required_labels = ["变更目标", "来源Cxx", "来源Dxx", "SQL参考表", "执行前备份", "回滚方式", "验证SQL"]
    if version >= 2:
        required_labels.extend([
            "SQL参考证据", "最小变更结论", "现有结构复用评估", "核心写入", "核心查询",
            "索引/约束依据", "数据规模与DDL风险",
        ])
    for label in required_labels:
        value = schema_comment_value(text, label)
        if not meaningful_design_value(value):
            errors.append(f"04-schema.sql 缺少实质元数据: {label}")
        elif vague_design_value(value):
            errors.append(f"04-schema.sql 元数据过于空泛: {label}={value}")
    claim_source = schema_comment_value(text, "来源Cxx")
    design_source = schema_comment_value(text, "来源Dxx")
    if not claim_refs(claim_source):
        errors.append("04-schema.sql 来源Cxx 必须引用至少一个 Cxx")
    if not design_refs(design_source):
        errors.append("04-schema.sql 来源Dxx 必须引用至少一个 Dxx")
    assert_claim_refs_exist("04-schema.sql", claim_refs(claim_source), valid_claim_ids, errors)
    assert_design_refs_exist("04-schema.sql", design_refs(design_source), valid_design_ids, errors)

    ddl_entries: list[dict[str, object]] = []
    if version >= 3:
        ddl_entries = extract_sql_v3_ddl_entries(text, errors)
        if not ddl_entries:
            errors.append("04-schema.sql SQL v3 未解析到任何逐对象结构 DDL")

    if version >= 3:
        assert_regex_exists(
            text,
            r"(?i)\b(CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE|TRUNCATE\s+TABLE|RENAME\s+TABLE)\b",
            "04-schema.sql 缺少实际结构 DDL 语句",
            errors,
        )
    else:
        assert_regex_exists(
            text,
            r"(?i)\b(CREATE\s+TABLE|ALTER\s+TABLE)\b",
            "04-schema.sql 缺少实际 CREATE TABLE 或 ALTER TABLE 语句",
            errors,
        )
    create_statements = (
        [
            str(entry["statement"])
            for entry in ddl_entries
            if entry["operation"] == "create"
        ]
        if version >= 3
        else re.findall(r"(?is)\bCREATE\s+TABLE\b.*?;", text)
    )
    for index, statement in enumerate(create_statements, start=1):
        for pattern, item in [
            (r"(?i)\bPRIMARY\s+KEY\b", "主键"),
            (r"(?i)\bENGINE\s*=", "ENGINE"),
            (r"(?i)\bDEFAULT\s+CHARSET\s*=", "DEFAULT CHARSET"),
            (r"(?i)\bCOMMENT\s*=\s*['\"]", "表注释"),
            (r"(?i)\b\w+\s+[A-Z]+(?:\([^)]*\))?[^,\n]*\bCOMMENT\s+['\"]", "字段注释"),
        ]:
            if not re.search(pattern, statement):
                errors.append(f"04-schema.sql 第 {index} 个 CREATE TABLE 缺少{item}")

    if version >= 2:
        index_definitions = re.findall(
            r"(?mi)^\s*(UNIQUE\s+)?KEY\s+`?([A-Za-z0-9_]+)`?\s*\(([^)]+)\)", text
        )
        seen_names: set[str] = set()
        seen_columns: dict[tuple[str, ...], str] = {}
        for _unique, name, columns_text in index_definitions:
            normalized_name = name.lower()
            if normalized_name in {"idx_xxx", "uk_xxx", "index_name"}:
                errors.append(f"04-schema.sql 索引名仍是模板占位符: {name}")
            if normalized_name in seen_names:
                errors.append(f"04-schema.sql 索引名重复: {name}")
            seen_names.add(normalized_name)
            columns: list[str] = []
            for part in columns_text.split(","):
                normalized_column = re.sub(r"\s+(ASC|DESC)\s*$", "", part.strip(), flags=re.I)
                normalized_column = re.sub(r"\(\d+\)$", "", normalized_column).strip().strip("`").lower()
                columns.append(normalized_column)
            columns_key = tuple(columns)
            if columns_key in seen_columns:
                errors.append(
                    f"04-schema.sql 存在重复索引列组合: {seen_columns[columns_key]} 与 {name}"
                )
            else:
                seen_columns[columns_key] = name

    if version >= 3:
        for entry in ddl_entries:
            ddl_label = f"04-schema.sql DDL 对象 {entry['object']}/{entry['operation']}"
            assert_claim_refs_exist(ddl_label, entry["claims"], valid_claim_ids, errors)  # type: ignore[arg-type]
            assert_design_refs_exist(ddl_label, entry["designs"], valid_design_ids, errors)  # type: ignore[arg-type]


def validate_baseline_doc(path: Path, clarification_gate_required: bool | None = None) -> list[str]:
    errors: list[str] = []
    text = read_text(path)
    if not text:
        return [f"缺少 {path.name}"]
    required_tokens = (
        BASELINE_V5_REQUIRED_TOKENS
        if document_schema_version(text) >= 5
        else BASELINE_REQUIRED_TOKENS
    )
    assert_contains(text, required_tokens, path.name, errors)
    assert_baseline_quality(text, errors, clarification_gate_required)
    return errors


def validate_research_doc(
    path: Path,
    repo_root: Path | None = None,
    baseline_text: str | None = None,
) -> list[str]:
    errors: list[str] = []
    text = read_text(path)
    if not text:
        return [f"缺少 {path.name}"]
    if repo_root is None:
        repo_root = infer_repo_root_from_doc(path)
    version = research_schema_version(text)
    required_tokens = (
        RESEARCH_V3_REQUIRED_TOKENS
        if version >= 3
        else RESEARCH_V2_REQUIRED_TOKENS
        if version >= 2
        else (
            RESEARCH_REQUIRED_TOKENS
            if "## 8. 结论账本（Claim Ledger）" in text
            else LEGACY_RESEARCH_REQUIRED_TOKENS
        )
    )
    assert_contains(text, required_tokens, path.name, errors)
    assert_no_unresolved_placeholders(text, path.name, errors)
    strict = bool(baseline_text) and document_schema_version(baseline_text or "") >= 4
    expected_baseline_ids = set(extract_baseline_verification_ids(baseline_text or "")) if strict else None
    assert_research_quality(text, errors, repo_root, expected_baseline_ids, strict)
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
    eligible_claim_ids: set[str] | None = None,
    transferred_question_ids: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    text = read_text(path)
    if not text:
        return [f"缺少 {path.name}"]
    version = design_schema_version(text)
    if version >= 6:
        required_tokens = DESIGN_V6_REQUIRED_TOKENS
    elif version >= 5:
        required_tokens = DESIGN_V5_REQUIRED_TOKENS
    elif version >= 4:
        required_tokens = DESIGN_V4_REQUIRED_TOKENS
    elif version >= 2:
        required_tokens = DESIGN_REQUIRED_TOKENS
    else:
        required_tokens = [
            token for token in DESIGN_REQUIRED_TOKENS if token != "## 〇、设计输入覆盖清单"
        ]
    assert_contains(text, required_tokens, path.name, errors)
    assert_no_unresolved_placeholders(text, path.name, errors)
    assert_no_design_residuals(text, path.name, errors, allow_risk_confirmation=True)
    assert_design_quality(text, errors, valid_claim_ids, eligible_claim_ids, transferred_question_ids)
    if eligible_claim_ids is not None:
        assert_design_claim_eligibility(text, eligible_claim_ids, errors)
    if version == 5 and extract_line_value(text, "- MySQL 结构变更：") == "有":
        schema_path = path.parent / "04-schema.sql"
        schema_text = read_text(schema_path)
        if not schema_text:
            errors.append("Design v5 有 MySQL 结构变更时缺少 04-schema.sql")
        else:
            assert_sql_object_closure_v5(text, schema_text, errors)

    detail_dir = interface_details or (path.parent / "interface-details")
    if interface_details is not None or version >= 5:
        errors.extend(validate_interface_details_dir(detail_dir))
        if version >= 2:
            decisions = extract_section(text, "## 十三、设计决策记录")
            decision_ids = extract_decision_ledger_ids(decisions, errors)
            if version >= 6:
                for detail_file in (
                    sorted(detail_dir.glob("*.md")) if detail_dir.exists() else []
                ):
                    if interface_schema_version(read_text(detail_file)) < 4:
                        errors.append(
                            f"{detail_file.name} 被 Design v6 引用时必须使用 Interface v4"
                        )
                assert_interface_closure_v5(
                    extract_section(text, "## 三、调用方与接口契约"),
                    detail_dir,
                    errors,
                    decision_ids,
                    eligible_claim_ids,
                )
            elif version >= 5:
                assert_interface_closure_v5(
                    extract_section(text, "## 三、调用方与接口契约"),
                    detail_dir,
                    errors,
                    decision_ids,
                    eligible_claim_ids,
                )
            elif version >= 4:
                assert_interface_closure_v4(
                    extract_section(text, "## 三、调用方与接口契约"),
                    detail_dir,
                    errors,
                    decision_ids,
                    eligible_claim_ids,
                )
            else:
                assert_interface_closure(
                    extract_section(text, "## 八、接口设计"),
                    detail_dir,
                    errors,
                    decision_ids,
                    eligible_claim_ids,
                )
    return errors


def validate_design_precheck(
    path: Path,
    eligible_claim_ids: set[str] | None = None,
    transferred_question_ids: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    text = read_text(path)
    if not text:
        return [f"缺少 {path.name}"]
    version = design_schema_version(text)
    if version < 2:
        return ["02-design.md 不是支持设计预检门禁的新版模板"]
    if version >= 4:
        precheck_headings = [
            "## 〇、设计输入去向",
            "## 二、实例身份与可信边界",
            "## 三、调用方与接口契约",
            "## 四、数据承载设计",
        ]
    else:
        precheck_headings = [
            "## 〇、设计输入覆盖清单",
            "## 二、实例身份与状态隔离",
            "## 三、前后端接口协作流",
            "## 四、数据承载设计",
        ]
    assert_contains(text, precheck_headings, path.name, errors)
    if extract_line_value(text, "- 设计状态：") != "SQL待确认":
        errors.append("02-design.md 在确认 SQL 前，设计状态必须为“SQL待确认”")
    if extract_line_value(text, "- MySQL 结构变更：") != "有":
        errors.append("02-design.md 进入 SQL 确认门禁时，MySQL 结构变更必须为“有”")
    assert_design_input_coverage(text, errors, eligible_claim_ids, transferred_question_ids)
    assert_design_precheck_tables(text, errors, eligible_claim_ids)
    if version == 3:
        assert_minimal_design_gate(text, errors, eligible_claim_ids)

    if version >= 5:
        precheck_scope = "\n".join(
            [
                extract_line_value(text, "- 设计状态："),
                extract_line_value(text, "- MySQL 结构变更："),
                extract_section(text, "## 〇、设计输入去向"),
                extract_section(text, "## 一、背景与目标"),
                extract_section(text, "## 二、实例身份与可信边界"),
                extract_section(text, "## 三、调用方与接口契约"),
                extract_section(text, "## 四、数据承载设计"),
            ]
        )
        assert_no_unresolved_placeholders(precheck_scope, path.name, errors)
        schema_text = read_text(path.parent / "04-schema.sql")
        if not schema_text:
            return errors

        assert_contains(text, ["## 五、SQL 变更说明"], path.name, errors)
        sql_section = extract_section(text, "## 五、SQL 变更说明")
        assert_no_unresolved_placeholders(f"{precheck_scope}\n{sql_section}", path.name, errors)
        assert_sql_design_v4(text, errors, eligible_claim_ids)
        assert_schema_quality(
            schema_text,
            errors,
            valid_claim_ids=eligible_claim_ids,
            valid_design_ids=None,
        )
        ddl_entries = assert_sql_object_closure_v5(text, schema_text, errors)
        if any(entry["risk"] == "高风险" for entry in ddl_entries):
            locked_headings_v5 = [
                "## 六、核心改动",
                "## 七、主链路与依赖",
                "## 八、接口补充（按需）",
                "## 九、枚举、状态与常量（按需）",
                "## 十、缓存设计（按需）",
                "## 十一、消息队列设计（按需）",
                "## 十二、配置变更（按需）",
                "## 十三、设计决策记录",
                "## 十四、影响范围",
                "## 十五、发布与灰度策略（按需）",
                "## 十六、测试链路与风险",
            ]
            for heading in locked_headings_v5:
                if re.search(r"\b[CD]\d+\b", extract_section(text, heading)):
                    errors.append(f"02-design.md 高风险 DDL 确认前不得填写依赖章节: {heading}")
            detail_dir = path.parent / "interface-details"
            if detail_dir.exists() and any(detail_dir.glob("*.md")):
                errors.append("高风险 DDL 确认前不得创建 interface-details/ 接口明细")
        return errors

    assert_no_unresolved_placeholders(text, path.name, errors)
    if version >= 4:
        return errors

    locked_headings = [
        "## 五、SQL 表设计",
        "## 六、核心改动",
        "## 七、主链路与依赖",
        "## 八、接口设计",
        "## 九、枚举、状态与常量",
        "## 十、缓存设计（按需）",
        "## 十一、消息队列设计（按需）",
        "## 十二、配置变更",
        "## 十三、设计决策记录",
        "## 十四、影响范围",
        "## 十五、发布与灰度策略",
        "## 十六、测试链路与风险",
    ]
    for heading in locked_headings:
        section = extract_section(text, heading)
        if re.search(r"\b[CD]\d+\b", section):
            errors.append(f"02-design.md 在 SQL 确认前不得填写锁定章节: {heading}")
    detail_dir = path.parent / "interface-details"
    if detail_dir.exists() and any(detail_dir.glob("*.md")):
        errors.append("SQL 确认前不得创建 interface-details/ 接口明细")
    return errors


def validate_tasks_doc(
    path: Path,
    interface_details: Path | None = None,
    valid_design_ids: set[str] | None = None,
    valid_claim_ids: set[str] | None = None,
    schema_exists: bool = False,
    required_core_design_ids: set[str] | None = None,
    sql_draft_exists: bool = False,
) -> list[str]:
    errors: list[str] = []
    text = read_text(path)
    if not text:
        return [f"缺少 {path.name}"]
    if not sql_draft_exists:
        sql_draft_exists = (path.parent / "sql-draft.sql").exists()
    marker_mentions = text.count("GGG_TASK_SCHEMA_VERSION")
    marker_matches = re.findall(
        r"<!--\s*GGG_TASK_SCHEMA_VERSION:\s*(\d+)\s*-->",
        text,
    )
    if marker_mentions and len(marker_matches) != 1:
        errors.append("03-tasks.md 的 GGG_TASK_SCHEMA_VERSION 标记畸形或重复，不能降级为 legacy")
    elif marker_matches and marker_matches[0] not in {"2", "3", "4"}:
        errors.append(f"03-tasks.md 使用不支持的 task schema 版本: {marker_matches[0]}")

    version = task_schema_version(text)
    required_tokens = (
        TASK_V3_REQUIRED_TOKENS
        if version >= 3
        else TASK_V2_REQUIRED_TOKENS
        if version >= 2
        else TASK_REQUIRED_TOKENS
    )
    assert_contains(text, required_tokens, path.name, errors)
    assert_no_unresolved_placeholders(text, path.name, errors)
    if required_core_design_ids is None:
        design_text = read_text(path.parent / "02-design.md")
        required_core_design_ids = extract_core_change_design_ids_from_design(design_text) if design_text else set()
    if task_schema_version(text) >= 2:
        assert_tasks_quality_v2(
            text,
            errors,
            interface_details,
            valid_design_ids,
            valid_claim_ids,
            schema_exists,
            required_core_design_ids,
            sql_draft_exists,
        )
    else:
        assert_tasks_quality(
            text,
            errors,
            interface_details,
            valid_design_ids,
            valid_claim_ids,
            schema_exists,
            required_core_design_ids,
        )
    return errors


def validate_schema_doc(
    path: Path,
    meta: dict,
    valid_claim_ids: set[str] | None = None,
    valid_design_ids: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    text = read_text(path)
    if not text:
        return [f"缺少 {path.name}"]
    assert_no_design_residuals(text, path.name, errors)
    assert_schema_quality(text, errors, valid_claim_ids, valid_design_ids)
    return errors


def validate_implementation_log(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return errors
    text = read_text(path)
    legacy = "## 4. 逐文件代码质量门禁" in text
    required_tokens = (
        [
            "## 1. 实现记录索引",
            "## 2. 偏差与回写记录",
            "## 3. 验证记录",
            "## 4. 逐文件代码质量门禁",
            "## 5. 高频漏项复核",
            "## 6. 实现会话状态",
        ]
        if legacy
        else IMPLEMENTATION_LOG_REQUIRED_TOKENS
    )
    assert_contains(text, required_tokens, path.name, errors)
    assert_table_has_headers(
        text,
        ["轮次", "任务", "实际修改文件", "验证结果"]
        if legacy
        else ["轮次", "任务", "完成标准证据", "实际修改文件", "验证结果"],
        "05-implementation-log.md 实现记录索引缺少关键表头",
        errors,
    )
    assert_table_has_headers(
        text,
        ["偏差", "影响文档", "处理结果"],
        "05-implementation-log.md 偏差与回写记录缺少关键表头: 偏差、影响文档、处理结果",
        errors,
    )
    return errors


IMPLEMENTATION_PRECHECK_ITEMS = [
    "范围与主链路",
    "代码落点与职责",
    "数据一致性与失败边界",
    "性能与外部调用",
    "抽象选择与方案偏差",
]
IMPLEMENTATION_PRECHECK_PROFILES = {
    "legacy": IMPLEMENTATION_PRECHECK_ITEMS,
    "tiny": [
        "范围与主链路",
        "验证策略",
    ],
    "normal": [
        "范围与主链路",
        "代码落点与职责",
        "数据、契约与失败边界",
        "验证策略",
    ],
    "high": [
        "范围与主链路",
        "代码落点与职责",
        "数据、契约与失败边界",
        "性能、外部调用与恢复",
        "抽象选择与方案偏差",
        "验证策略",
    ],
}


def implementation_precheck_section(path: Path) -> str:
    heading = "### 3.1 编码前实现预检" if path.name == "quick.md" else "## 0. 编码前实现预检"
    return extract_section(read_text(path), heading)


def implementation_precheck_fingerprint(path: Path) -> str:
    section = implementation_precheck_section(path)
    return hashlib.sha256(section.encode("utf-8")).hexdigest()


def validate_implementation_precheck(
    path: Path,
    expected_round: str,
    risk_profile: str | None = None,
    expected_task_ids: set[str] | None = None,
) -> list[str]:
    """按风险档位校验实现草图，不让小改动承担高风险流程成本。"""
    if not path.exists():
        return [f"缺少实现记录: {path}"]
    label = "quick.md" if path.name == "quick.md" else "05-implementation-log.md"
    section = implementation_precheck_section(path)
    if not section:
        return [f"{label} 缺少编码前实现预检"]

    errors: list[str] = []
    headers, rows = extract_first_table(section)
    required_headers = ["轮次", "检查面", "预检结论", "事实依据", "状态"]
    if not all(header in headers for header in required_headers):
        return [f"{label} 编码前实现预检缺少关键表头: {', '.join(required_headers)}"]

    current_rows = [
        row for row in rows
        if table_cell(headers, row, "轮次") == expected_round
    ]
    rows_by_item: dict[str, list[list[str]]] = {}
    for row in current_rows:
        rows_by_item.setdefault(table_cell(headers, row, "检查面"), []).append(row)

    unresolved_tokens = ["TODO", "TBD", "FIXME", "待补充", "待确认", "未确认"]
    required_items = (
        IMPLEMENTATION_PRECHECK_PROFILES.get(risk_profile, [])
        if risk_profile
        else IMPLEMENTATION_PRECHECK_ITEMS
    )
    if not required_items:
        errors.append(f"{label} 使用了未知风险档位: {risk_profile}")
        return errors
    for item in required_items:
        matches = rows_by_item.get(item, [])
        if len(matches) != 1:
            errors.append(
                f"{label} {expected_round} 编码前实现预检必须且只能有一条“{item}”"
            )
            continue
        row = matches[0]
        conclusion = table_cell(headers, row, "预检结论")
        evidence = table_cell(headers, row, "事实依据")
        status = table_cell(headers, row, "状态")
        if len(conclusion) < 6 or conclusion in EMPTY_VALUES:
            errors.append(f"{label} {expected_round} 的“{item}”预检结论过于空泛")
        if len(evidence) < 4 or evidence in EMPTY_VALUES:
            errors.append(f"{label} {expected_round} 的“{item}”缺少代码或设计事实依据")
        if any(token in f"{conclusion} {evidence}" for token in unresolved_tokens):
            errors.append(f"{label} {expected_round} 的“{item}”仍有未确认内容")
        if status != "通过":
            errors.append(f"{label} {expected_round} 的“{item}”状态必须为通过")

    if path.name != "quick.md":
        range_rows = rows_by_item.get("范围与主链路", [])
        if len(range_rows) == 1:
            range_text = " ".join(
                [
                    table_cell(headers, range_rows[0], "预检结论"),
                    table_cell(headers, range_rows[0], "事实依据"),
                ]
            )
            referenced_tasks = set(re.findall(r"\bT\d+\b", range_text))
            planned_tasks = (
                set(expected_task_ids)
                if expected_task_ids is not None
                else implementation_task_ids(path.parent / "03-tasks.md")
            )
            if not referenced_tasks:
                errors.append(f"{label} {expected_round} 的范围与主链路必须引用本轮 Txx")
            unknown_tasks = referenced_tasks - planned_tasks
            if unknown_tasks:
                errors.append(
                    f"{label} {expected_round} 的预检引用了不存在的任务: "
                    + ", ".join(sorted(unknown_tasks))
                )
            missing_tasks = planned_tasks - referenced_tasks
            if missing_tasks:
                errors.append(
                    f"{label} {expected_round} 的范围与主链路未覆盖本轮任务: "
                    + ", ".join(sorted(missing_tasks))
                )
    return errors


HIGH_FREQUENCY_QUALITY_ITEMS = [
    "Controller Javadoc",
    "Javadoc 格式完整性",
    "DTO/VO 字段注释",
    "Service/Facade Javadoc",
    "关键业务逻辑注释",
    "链路日志/Trace",
    "对外 ID 类型",
    "Controller 职责与转换",
    "重复业务常量",
    "SQL/DDL 公共字段与方言",
    "代码格式与项目静态检查",
]

JAVA_PATH_PATTERN = re.compile(r"[^\s、，,；;`|]+\.java")
SQL_PATH_PATTERN = re.compile(r"[^\s、，,；;`|]+\.sql", re.IGNORECASE)
DOCUMENT_SUFFIXES = {".md", ".rst", ".adoc"}
FAILED_EVIDENCE_PREFIXES = ("未通过", "有问题", "失败", "阻塞", "待补充", "待修复")


def extract_round_java_and_ddl_evidence(
    text: str,
    expected_round: str,
) -> tuple[str, str, list[str]]:
    """读取 full 指定 Ixx 的独立规范证据。"""
    errors: list[str] = []
    matches: list[tuple[str, str]] = []
    for headers, rows in iter_markdown_tables(text):
        required = {"轮次", "关键逻辑注释证据", "SQL/DDL 规范证据"}
        if not required.issubset(headers):
            continue
        for row in rows:
            if table_cell(headers, row, "轮次") == expected_round:
                matches.append(
                    (
                        table_cell(headers, row, "关键逻辑注释证据"),
                        table_cell(headers, row, "SQL/DDL 规范证据"),
                    )
                )
    if len(matches) > 1:
        errors.append(f"05-implementation-log.md {expected_round} 存在重复关键规范证据")
    if matches:
        return matches[-1][0], matches[-1][1], errors
    return "", "", errors


def evidence_paths(
    evidence: str,
    pattern: re.Pattern[str],
) -> set[str]:
    unquoted = re.sub(r"`[^`\n]+`", " ", evidence)
    paths = {normalize_quality_path(match) for match in pattern.findall(unquoted)}
    for quoted in re.findall(r"`([^`\n]+)`", evidence):
        match = re.match(r"^(.+\.(?:java|sql))(?::\d+|#.*)?$", quoted, flags=re.IGNORECASE)
        if match and pattern.search(match.group(1)):
            paths.add(normalize_quality_path(match.group(1)))
    return paths


def validate_evidence_path_binding(
    evidence: str,
    actual_paths: set[str],
    pattern: re.Pattern[str],
    kind: str,
    label: str,
    require_all: bool = False,
) -> list[str]:
    """保证证据只引用本轮登记文件，DDL 还必须覆盖全部 SQL 文件。"""
    expected = {
        normalize_quality_path(path)
        for path in actual_paths
        if pattern.search(normalize_quality_path(path))
    }
    referenced = evidence_paths(evidence, pattern)
    if not referenced:
        return [f"{label} 的{kind}证据必须引用本轮修改文件"]
    unrelated = sorted(referenced - expected)
    errors = []
    if unrelated:
        errors.append(f"{label} 的{kind}证据引用了非本轮文件: " + ", ".join(unrelated))
    if require_all:
        missing = sorted(expected - referenced)
        if missing:
            errors.append(f"{label} 的{kind}证据未覆盖本轮文件: " + ", ".join(missing))
    return errors


def validate_java_and_ddl_evidence(
    text: str,
    actual_paths: set[str],
    label: str,
    review: bool = False,
    expected_round: str | None = None,
    require_round_evidence: bool = False,
) -> list[str]:
    """按真实文件类型校验关键逻辑注释和 DDL 规范证据。"""
    errors: list[str] = []
    prefix = "Review " if review else ""
    java_label = f"- {prefix}关键逻辑注释证据："
    ddl_label = f"- {prefix}SQL/DDL 规范证据："
    has_java = any(path.lower().endswith(".java") for path in actual_paths)
    has_ddl = any(path.lower().endswith(".sql") for path in actual_paths)
    java_evidence = ""
    ddl_evidence = ""

    if expected_round:
        java_evidence, ddl_evidence, round_errors = extract_round_java_and_ddl_evidence(
            text,
            expected_round,
        )
        errors.extend(round_errors)
        if require_round_evidence and not java_evidence and not ddl_evidence:
            errors.append(f"{label} {expected_round} 缺少按轮次记录的关键规范证据")
    if not expected_round or (not java_evidence and not ddl_evidence and not require_round_evidence):
        java_evidence = extract_line_value(text, java_label)
        ddl_evidence = extract_line_value(text, ddl_label)

    if has_java:
        evidence = java_evidence
        placeholder = "写明本轮没有复杂逻辑的原因"
        if not evidence or placeholder in evidence:
            errors.append(f"{label} 的 Java 改动缺少独立关键逻辑注释证据")
        elif evidence.startswith(FAILED_EVIDENCE_PREFIXES):
            errors.append(f"{label} 的关键逻辑注释证据仍明确为未通过")
        elif evidence.startswith(("不涉及", "不适用")):
            if len(evidence) < 12 or "原因" in evidence:
                errors.append(f"{label} 的关键逻辑注释不适用原因不具体")
        elif not re.search(r"\.java`?(?::\d+|#)", evidence):
            errors.append(f"{label} 的关键逻辑注释证据必须包含 Java 文件行号或符号")
        else:
            errors.extend(
                validate_evidence_path_binding(
                    evidence,
                    actual_paths,
                    JAVA_PATH_PATTERN,
                    "关键逻辑注释",
                    label,
                )
            )

    if has_ddl:
        evidence = ddl_evidence
        if not evidence or evidence.startswith(("不涉及", "不适用")):
            errors.append(f"{label} 的 DDL 改动缺少 SQL/DDL 规范证据")
        elif evidence.startswith(FAILED_EVIDENCE_PREFIXES):
            errors.append(f"{label} 的 SQL/DDL 规范证据仍明确为未通过")
        else:
            if not any(token in evidence for token in ["参考表", "项目现有", "统一兜底", "共享兜底"]):
                errors.append(f"{label} 的 SQL/DDL 规范证据缺少参考表或统一兜底依据")
            if "公共字段" not in evidence:
                errors.append(f"{label} 的 SQL/DDL 规范证据缺少公共字段或例外说明")
            if not any(token in evidence for token in ["MySQL", "方言", "测试 schema", "测试脚本"]):
                errors.append(f"{label} 的 SQL/DDL 规范证据缺少生产方言与测试脚本区分")
            errors.extend(
                validate_evidence_path_binding(
                    evidence,
                    actual_paths,
                    SQL_PATH_PATTERN,
                    "SQL/DDL ",
                    label,
                    require_all=True,
                )
            )
    return errors


def validate_legacy_quick_review_evidence(text: str, actual_paths: set[str]) -> list[str]:
    errors = validate_java_and_ddl_evidence(
        text,
        actual_paths,
        "quick Review",
        review=True,
    )
    expected_paths = {normalize_quality_path(value) for value in actual_paths}
    covered_paths = extract_quality_paths(extract_line_value(text, "- Review 覆盖文件："))
    if expected_paths - covered_paths:
        errors.append("quick Review 覆盖文件未包含本轮实际文件: " + ", ".join(sorted(expected_paths - covered_paths)))
    if covered_paths - expected_paths:
        errors.append("quick Review 覆盖文件包含非本轮文件: " + ", ".join(sorted(covered_paths - expected_paths)))
    section = extract_section(text, "### 5.1 Quick Review 独立复核")
    headers, rows = extract_first_table(section)
    rows_by_item = {table_cell(headers, row, "检查面"): row for row in rows}
    for item in ["需求与边界一致性", "代码质量与风险", "幻觉审计", "验证证据充分性"]:
        row = rows_by_item.get(item)
        if row is None:
            errors.append(f"quick Review 独立复核缺少检查面: {item}")
        elif (
            table_cell(headers, row, "结论") != "通过"
            or table_cell(headers, row, "独立证据或问题") in EMPTY_VALUES
        ):
            errors.append(f"quick Review 的“{item}”未通过或缺少独立证据")
    return errors


def validate_quick_review_evidence(
    path: Path,
    actual_paths: set[str],
    expected_reviewer_mode: str | None = None,
    expected_self_review_reason: str | None = None,
) -> list[str]:
    """Review 通过前校验 quick 两门复核和完整 Diff 覆盖。"""
    if not path.exists():
        return [f"缺少 quick 记录: {path}"]
    text = read_text(path)
    if quick_schema_version(text) >= 4:
        return validate_optional_review(
            path,
            "passed",
            extract_line_value(text, "- Review 对应实现轮次："),
            extract_line_value(text, "- Review 对应差异指纹："),
        )
    if quick_schema_version(text) >= 3:
        errors: list[str] = []
        disposition = extract_line_value(text, "- Review 处置：").strip()
        result = extract_line_value(text, "- Review 结论：").strip()
        gate_satisfied = extract_line_value(
            text,
            "- Review Gate 是否满足：",
        ).strip()
        issue_value = extract_line_value(
            text,
            "- Review 未关闭阻塞/必须修问题：",
        ).strip()
        if disposition not in {"light", "formal", "skipped"}:
            return ["quick.md v3 Review 处置必须为 light、formal 或 skipped"]
        if gate_satisfied != "是":
            errors.append("quick.md v3 Review Gate 是否满足必须为“是”")
        if disposition == "skipped":
            if result != "已跳过":
                errors.append("quick.md v3 skipped Review 的结论必须为“已跳过”")
            skip_source = extract_line_value(text, "- Review 跳过来源：").strip()
            if (
                not meaningful_design_value(skip_source)
                or skip_source in {"用户消息", "已确认 quick 规则", "其他具体来源"}
            ):
                errors.append("quick.md v3 skipped Review 必须记录可回查的跳过来源")
            return errors
        if result != "通过":
            errors.append("quick.md v3 Review 通过登记时结论必须为“通过”")
        if issue_value not in {"无", "不涉及"}:
            errors.append("quick Review 通过前必须明确没有未关闭阻塞/必须修问题")
        if not any(
            line.strip().startswith("- Review 剩余风险：")
            for line in text.splitlines()
        ):
            errors.append("quick Review 缺少剩余风险记录")
        if disposition == "light":
            summary = extract_line_value(
                text,
                "- Light Review 简要结论：",
            ).strip()
            if (
                not meaningful_design_value(summary)
                or summary.startswith("不涉及")
                or "逻辑、代码和文档的简洁复核结论" in summary
            ):
                errors.append("quick.md v3 light Review 缺少逻辑、代码或文档的简洁复核结论")
            return errors

        section = extract_section(
            text,
            "### 5.1 Formal Review 两门复核（仅 formal）",
        )
        tables = iter_markdown_tables(section)
        if len(tables) < 2:
            return errors + ["quick formal Review 缺少两门复核表或完整 Diff 覆盖表"]
        return errors + validate_quick_formal_review_tables(tables, actual_paths)

    provenance_errors = validate_review_provenance(
        text,
        "quick.md",
        expected_reviewer_mode,
        expected_self_review_reason,
    )
    if "### 5.1 Quick Review 两门复核" not in text:
        return provenance_errors + validate_legacy_quick_review_evidence(
            text,
            actual_paths,
        )
    errors = provenance_errors
    if extract_line_value(text, "- Review Gate A：") != "通过":
        errors.append("quick Review Gate A 必须先通过")
    if extract_line_value(text, "- Review Gate B：") != "通过":
        errors.append("quick Review Gate B 必须通过")
    issue_value = extract_line_value(text, "- Review 未关闭阻塞/必须修问题：")
    if issue_value not in {"无", "不涉及"}:
        errors.append("quick Review 通过前必须明确没有未关闭阻塞/必须修问题")
    if not any(line.strip().startswith("- Review 剩余风险：") for line in text.splitlines()):
        errors.append("quick Review 缺少剩余风险记录")

    section = extract_section(text, "### 5.1 Quick Review 两门复核")
    tables = iter_markdown_tables(section)
    if len(tables) < 2:
        return errors + ["quick Review 缺少两门复核表或完整 Diff 覆盖表"]
    headers, rows = tables[0]
    required_headers = ["Gate", "检查面", "结论", "独立证据或 CRxx"]
    if not all(header in headers for header in required_headers):
        errors.append("quick Review 两门复核缺少关键表头")
        return errors
    rows_by_item = {table_cell(headers, row, "检查面"): row for row in rows}
    for item in [
        "目标、禁止项与行为",
        "契约、数据、权限、兼容与越界",
        "正确性、安全、失败边界与副作用",
        "可维护性、触发风险与验证充分性",
    ]:
        row = rows_by_item.get(item)
        if row is None:
            errors.append(f"quick Review 两门复核缺少检查面: {item}")
            continue
        if table_cell(headers, row, "结论") != "通过":
            errors.append(f"quick Review 的“{item}”必须明确为通过")
        evidence = table_cell(headers, row, "独立证据或 CRxx")
        if evidence in EMPTY_VALUES:
            errors.append(f"quick Review 的“{item}”缺少独立证据")

    coverage_headers, coverage_rows = tables[1]
    required_coverage = ["Diff 路径", "Gate A", "Gate B", "独立证据或 CRxx"]
    if not all(header in coverage_headers for header in required_coverage):
        return errors + ["quick Review 完整 Diff 覆盖表缺少关键表头"]
    covered: set[str] = set()
    for row in coverage_rows:
        paths = extract_quality_paths(table_cell(coverage_headers, row, "Diff 路径"))
        if not paths:
            continue
        if len(paths) != 1:
            errors.append("quick Review 每个覆盖行必须且只能记录一个 Diff 路径")
            continue
        diff_path = next(iter(paths))
        if diff_path in covered:
            errors.append(f"quick Review Diff 路径重复: {diff_path}")
        covered.add(diff_path)
        if table_cell(coverage_headers, row, "Gate A") != "通过":
            errors.append(f"quick Review {diff_path} Gate A 未通过")
        if table_cell(coverage_headers, row, "Gate B") != "通过":
            errors.append(f"quick Review {diff_path} Gate B 未通过")
        if table_cell(coverage_headers, row, "独立证据或 CRxx") in EMPTY_VALUES:
            errors.append(f"quick Review {diff_path} 缺少独立证据")
    expected = {normalize_quality_path(value) for value in actual_paths}
    missing = sorted(expected - covered)
    extra = sorted(covered - expected)
    if missing:
        errors.append("quick Review 未覆盖本轮实际文件: " + ", ".join(missing))
    if extra:
        errors.append("quick Review 覆盖了非本轮文件: " + ", ".join(extra))
    return errors


def validate_quick_formal_review_tables(
    tables: list[tuple[list[str], list[list[str]]]],
    actual_paths: set[str],
) -> list[str]:
    """校验 quick v3 仅在 formal 处置下要求的两门复核与完整 Diff 覆盖。"""
    errors: list[str] = []
    headers, rows = tables[0]
    required_headers = ["Gate", "检查面", "结论", "独立证据或 CRxx"]
    if not all(header in headers for header in required_headers):
        return ["quick formal Review 两门复核缺少关键表头"]
    rows_by_item = {table_cell(headers, row, "检查面"): row for row in rows}
    for item in [
        "目标、禁止项与行为",
        "契约、数据、权限、兼容与越界",
        "正确性、安全、失败边界与副作用",
        "可维护性、触发风险与验证充分性",
    ]:
        row = rows_by_item.get(item)
        if row is None:
            errors.append(f"quick formal Review 两门复核缺少检查面: {item}")
            continue
        if table_cell(headers, row, "结论") != "通过":
            errors.append(f"quick formal Review 的“{item}”必须明确为通过")
        if table_cell(headers, row, "独立证据或 CRxx") in EMPTY_VALUES:
            errors.append(f"quick formal Review 的“{item}”缺少独立证据")

    coverage_headers, coverage_rows = tables[1]
    required_coverage = ["Diff 路径", "Gate A", "Gate B", "独立证据或 CRxx"]
    if not all(header in coverage_headers for header in required_coverage):
        return errors + ["quick formal Review 完整 Diff 覆盖表缺少关键表头"]
    covered: set[str] = set()
    for row in coverage_rows:
        paths = extract_quality_paths(table_cell(coverage_headers, row, "Diff 路径"))
        if not paths:
            continue
        if len(paths) != 1:
            errors.append("quick formal Review 每个覆盖行必须且只能记录一个 Diff 路径")
            continue
        diff_path = next(iter(paths))
        if diff_path in covered:
            errors.append(f"quick formal Review Diff 路径重复: {diff_path}")
        covered.add(diff_path)
        if table_cell(coverage_headers, row, "Gate A") != "通过":
            errors.append(f"quick formal Review {diff_path} Gate A 未通过")
        if table_cell(coverage_headers, row, "Gate B") != "通过":
            errors.append(f"quick formal Review {diff_path} Gate B 未通过")
        if table_cell(coverage_headers, row, "独立证据或 CRxx") in EMPTY_VALUES:
            errors.append(f"quick formal Review {diff_path} 缺少独立证据")
    expected = {normalize_quality_path(value) for value in actual_paths}
    missing = sorted(expected - covered)
    extra = sorted(covered - expected)
    if missing:
        errors.append("quick formal Review 未覆盖本轮实际文件: " + ", ".join(missing))
    if extra:
        errors.append("quick formal Review 覆盖了非本轮文件: " + ", ".join(extra))
    return errors


def normalize_quality_path(value: str) -> str:
    path = value.strip().strip("`\"'").rstrip("。.:：")
    while path.startswith("./"):
        path = path[2:]
    return path.replace("\\", "/")


def looks_like_quality_path(value: str) -> bool:
    if not value or "://" in value or value.startswith("-"):
        return False
    candidate = Path(value)
    if candidate.name == "implementation-state.json" or candidate.suffix.lower() in DOCUMENT_SUFFIXES:
        return False
    return "/" in value or candidate.suffix != "" or candidate.name.startswith(".") or candidate.name in {
        "Dockerfile",
        "Makefile",
        "Jenkinsfile",
        "gradlew",
        "mvnw",
        "BUILD",
        "WORKSPACE",
        "Procfile",
        "Rakefile",
        "Gemfile",
    }


def extract_java_paths(value: str) -> set[str]:
    return {normalize_quality_path(match) for match in JAVA_PATH_PATTERN.findall(value)}


def extract_quality_paths(value: str) -> set[str]:
    """提取需要纳入实现差异、记录和指纹的代码、SQL、脚本、配置与构建文件。"""
    quoted = re.findall(r"`([^`\n]+)`", value)
    remainder = re.sub(r"`[^`\n]+`", "\n", value)
    chunks = quoted + re.split(r"<br\s*/?>|[\n、，,；;]+", remainder, flags=re.IGNORECASE)
    paths: set[str] = set()
    for chunk in chunks:
        normalized = normalize_quality_path(chunk)
        if looks_like_quality_path(normalized):
            paths.add(normalized)
    return paths


def validate_legacy_loaded_norms(text: str, actual_paths: set[str], label: str) -> list[str]:
    """兼容已生成的旧实现记录；新记录只允许统一规范。"""
    errors: list[str] = []
    evidence = extract_line_value(text, "- 已加载规范及证据：")
    if not evidence:
        return [f"{label} 缺少已实际加载规范的证据"]
    if "ggg-implementation" not in evidence:
        errors.append(f"{label} 必须记录 ggg-implementation/SKILL.md 的加载证据")
    if any(path.endswith(".java") for path in actual_paths):
        unified = "ggg-java-coding-standard" in evidence
        legacy_pair = "java-backend-code-standard" in evidence and "jzx-personal-java-style" in evidence
        if not unified and not legacy_pair:
            errors.append(f"{label} 的 Java 改动缺少统一规范或旧版成对规范加载证据")
    return errors


def validate_code_quality_self_check(
    section_text: str,
    label: str,
    expected_round: str | None = None,
) -> list[str]:
    """校验一轮综合代码质量自检，避免重复维护逐文件表和固定十项表。"""
    errors: list[str] = []
    tables = iter_markdown_tables(section_text)
    headers, rows = tables[0] if tables else ([], [])
    required_headers = ["任务/范围", "自检重点", "证据（文件行号/命令）", "结论", "未通过处理"]
    if not all(header in headers for header in required_headers):
        return [f"{label} 缺少关键表头: {', '.join(required_headers)}"]

    if expected_round is not None:
        if "轮次" not in headers:
            return [f"{label} 缺少轮次表头"]
        rows = [row for row in rows if table_cell(headers, row, "轮次") == expected_round]

    substantive_rows = [row for row in rows if table_cell(headers, row, "任务/范围")]
    if not substantive_rows:
        return [f"{label} 缺少已填写的代码质量自检记录"]

    for row in substantive_rows:
        scope = table_cell(headers, row, "任务/范围")
        focus = table_cell(headers, row, "自检重点")
        evidence = table_cell(headers, row, "证据（文件行号/命令）")
        result = table_cell(headers, row, "结论")
        if not focus:
            errors.append(f"{label} 的 {scope} 缺少自检重点")
        if not evidence:
            errors.append(f"{label} 的 {scope} 缺少文件、符号或命令证据")
        if result != "通过":
            errors.append(f"{label} 的 {scope} 结论必须明确为“通过”")
    return errors


def implementation_task_ids(path: Path) -> set[str]:
    """从 03-tasks.md 的结构化任务表提取 Txx。"""
    if not path.exists():
        return set()
    text = read_text(path)
    heading = "## 3. 任务总览" if task_schema_version(text) >= 2 else "## 3. 编码任务"
    headers, rows = extract_first_table(extract_section(text, heading))
    if "编号" not in headers:
        return set()
    return {
        task_id
        for row in rows
        if re.fullmatch(r"T\d+", task_id := table_cell(headers, row, "编号"))
    }


def validate_high_frequency_quality_table(
    section_text: str,
    label: str,
    evidence_header: str,
    allowed_results: set[str],
    expected_round: str | None = None,
) -> list[str]:
    errors: list[str] = []
    headers, rows = extract_first_table(section_text)
    required_headers = ["检查项", "适用文件", "结论", evidence_header]
    if not all(header in headers for header in required_headers):
        return [f"{label} 缺少关键表头: {', '.join(required_headers)}"]

    if expected_round is not None:
        if "轮次" not in headers:
            return [f"{label} 缺少轮次表头"]
        rows = [row for row in rows if table_cell(headers, row, "轮次") == expected_round]
    rows_by_item = {table_cell(headers, row, "检查项"): row for row in rows}
    for item in HIGH_FREQUENCY_QUALITY_ITEMS:
        row = rows_by_item.get(item)
        if row is None:
            errors.append(f"{label} 缺少固定复核项: {item}")
            continue

        result = table_cell(headers, row, "结论")
        evidence = table_cell(headers, row, evidence_header)
        if result not in allowed_results:
            errors.append(f"{label} 的 {item} 结论必须为: {', '.join(sorted(allowed_results))}")
        if not evidence:
            errors.append(f"{label} 的 {item} 缺少文件行号证据或不适用原因")
        if result == "不适用" and len(evidence) < 4:
            errors.append(f"{label} 的 {item} 不适用原因不具体")
    return errors


IMPLEMENTATION_V2_EVIDENCE_ITEMS = [
    "ID / 大整数精度",
    "Request / Response / DTO 字段注释",
    "异常 / 错误码",
    "业务日志",
    "Trace 链路",
    "测试代码是否修改及用户授权",
]


def has_concrete_implementation_evidence(value: str) -> bool:
    normalized = value.strip().strip("`")
    return (
        len(normalized) >= 4
        and normalized not in EMPTY_VALUES
        and normalized
        not in {
            "文件:行号/命令",
            "用户消息定位",
            "具体原因",
        }
    )


def validate_implementation_v2_independent_evidence(
    text: str,
    latest_round: str,
    section_heading: str = "### 4.2 独立契约与可观测性证据",
    record_label: str = "05-implementation-log.md",
    actual_paths: set[str] | None = None,
) -> list[str]:
    """校验 v2 每轮独立契约、可观测性和测试代码授权证据。"""
    label = f"{record_label} 独立契约与可观测性证据"
    section = extract_section(text, section_heading)
    headers, rows = extract_first_table(section)
    required_headers = [
        "轮次",
        "检查项",
        "结论",
        "独立证据（文件:行号/命令）",
        "不涉及原因或用户授权",
    ]
    if not all(header in headers for header in required_headers):
        return [f"{label} 缺少关键表头: {', '.join(required_headers)}"]

    current_rows = [
        row
        for row in rows
        if table_cell(headers, row, "轮次") == latest_round
    ]
    rows_by_item: dict[str, list[list[str]]] = {}
    for row in current_rows:
        rows_by_item.setdefault(
            table_cell(headers, row, "检查项"),
            [],
        ).append(row)

    errors: list[str] = []
    for item in IMPLEMENTATION_V2_EVIDENCE_ITEMS:
        item_rows = rows_by_item.get(item, [])
        if not item_rows:
            errors.append(f"{label} {latest_round} 缺少检查项: {item}")
            continue
        if len(item_rows) > 1:
            errors.append(f"{label} {latest_round} 检查项重复: {item}")
            continue
        row = item_rows[0]
        result = table_cell(headers, row, "结论")
        evidence = table_cell(
            headers,
            row,
            "独立证据（文件:行号/命令）",
        )
        reason = table_cell(headers, row, "不涉及原因或用户授权")

        if item == "测试代码是否修改及用户授权":
            test_paths = sorted(
                path for path in (actual_paths or set()) if is_test_artifact(path)
            )
            if result not in {"未修改", "已授权并修改", "有问题"}:
                errors.append(
                    f"{label} 的“{item}”结论必须为未修改、已授权并修改或有问题"
                )
                continue
            if result == "有问题":
                errors.append(f"{label} 的“{item}”仍有问题，不能完成当前实现轮次")
            if not has_concrete_implementation_evidence(evidence):
                errors.append(f"{label} 的“{item}”缺少独立差异或命令证据")
            if result == "未修改":
                if test_paths:
                    errors.append(
                        f"{label} 声明未修改测试代码，但当前差异包含测试资产: "
                        + ", ".join(test_paths)
                    )
                normalized_reason = reason.strip()
                if not (
                    normalized_reason.startswith("不涉及：")
                    and len(normalized_reason.removeprefix("不涉及：").strip()) >= 4
                ):
                    errors.append(f"{label} 的“{item}”未修改时必须写明不涉及原因")
            elif result == "已授权并修改" and not has_concrete_implementation_evidence(
                reason
            ):
                errors.append(f"{label} 的“{item}”缺少可回查的用户授权来源")
            elif result == "已授权并修改" and not test_paths:
                errors.append(
                    f"{label} 声明已授权并修改测试代码，但当前差异未发现测试资产"
                )
            continue

        if result not in {"通过", "有问题", "不涉及"}:
            errors.append(
                f"{label} 的“{item}”结论必须为通过、有问题或不涉及"
            )
            continue
        if result == "有问题":
            errors.append(f"{label} 的“{item}”仍有问题，不能完成当前实现轮次")
            if not has_concrete_implementation_evidence(evidence):
                errors.append(f"{label} 的“{item}”缺少问题定位证据")
        elif result == "不涉及":
            normalized_reason = reason.strip()
            if not (
                normalized_reason.startswith("不涉及：")
                and len(normalized_reason.removeprefix("不涉及：").strip()) >= 4
            ):
                errors.append(f"{label} 的“{item}”必须写明具体不涉及原因")
        elif not has_concrete_implementation_evidence(evidence):
            errors.append(f"{label} 的“{item}”缺少独立文件行号或命令证据")
    return errors


def validate_legacy_implementation_completion(path: Path, errors: list[str]) -> list[str]:
    """兼容旧版 full 实现记录，不要求用户立即迁移历史需求目录。"""
    text = read_text(path)
    index_headers, index_rows = extract_first_table(extract_section(text, "## 1. 实现记录索引"))
    latest_round = ""
    latest_index_row: list[str] = []
    for row in index_rows:
        round_value = table_cell(index_headers, row, "轮次")
        if re.fullmatch(r"I\d+", round_value):
            latest_round = round_value
            latest_index_row = row
    actual_paths = (
        extract_quality_paths(table_cell(index_headers, latest_index_row, "实际修改文件"))
        if latest_index_row
        else set()
    )
    if not latest_round:
        errors.append("05-implementation-log.md 缺少有效实现轮次")
        return errors
    errors.extend(validate_legacy_loaded_norms(text, actual_paths, "05-implementation-log.md"))

    quality_section = extract_section(text, "## 4. 逐文件代码质量门禁")
    headers, rows = extract_first_table(quality_section)
    required = ["轮次", "文件", "文件角色", "适用检查项", "证据（文件行号/命令）", "结论", "未通过处理"]
    if not all(header in headers for header in required):
        errors.append("05-implementation-log.md 旧版逐文件代码质量门禁缺少关键表头")
    else:
        current_rows = [row for row in rows if table_cell(headers, row, "轮次") == latest_round]
        covered: set[str] = set()
        substantive = 0
        for row in current_rows:
            file_value = table_cell(headers, row, "文件")
            if not file_value:
                continue
            substantive += 1
            covered.update(extract_quality_paths(file_value))
            if not table_cell(headers, row, "适用检查项"):
                errors.append(f"旧版逐文件门禁的 {file_value} 缺少适用检查项")
            if not table_cell(headers, row, "证据（文件行号/命令）"):
                errors.append(f"旧版逐文件门禁的 {file_value} 缺少证据")
            if table_cell(headers, row, "结论") not in {"通过", "不适用"}:
                errors.append(f"旧版逐文件门禁的 {file_value} 未通过或结论未收口")
        if not substantive:
            errors.append("05-implementation-log.md 缺少已填写的旧版逐文件代码质量门禁记录")
        missing = sorted(actual_paths - covered)
        if missing:
            errors.append("旧版逐文件门禁未覆盖实际修改文件: " + ", ".join(missing))

    errors.extend(
        validate_high_frequency_quality_table(
            extract_section(text, "## 5. 高频漏项复核"),
            "05-implementation-log.md 旧版高频漏项复核",
            "证据或不适用原因",
            {"通过", "不适用"},
            latest_round,
        )
    )
    return errors


def validate_implementation_completion(
    path: Path,
    expected_task_ids: set[str] | None = None,
) -> list[str]:
    """验证实现完成证据；编码过程中允许模板存在，推进代码检查前才调用。"""
    errors = validate_implementation_log(path)
    if not path.exists():
        return errors or ["缺少 05-implementation-log.md"]

    text = read_text(path)
    if "## 4. 逐文件代码质量门禁" in text:
        return validate_legacy_implementation_completion(path, errors)
    quality_heading = "## 4. 代码质量自检"
    assert_contains(text, [quality_heading], path.name, errors)

    index_headers, index_rows = extract_first_table(extract_section(text, "## 1. 实现记录索引"))
    valid_index_rows: list[list[str]] = []
    for row in index_rows:
        round_value = table_cell(index_headers, row, "轮次")
        if re.fullmatch(r"I\d+", round_value):
            valid_index_rows.append(row)
    if not valid_index_rows:
        errors.append("05-implementation-log.md 缺少有效实现轮次")
        return errors

    latest_round = max(
        (table_cell(index_headers, row, "轮次") for row in valid_index_rows),
        key=lambda value: int(value[1:]),
    )
    latest_rows = [row for row in valid_index_rows if table_cell(index_headers, row, "轮次") == latest_round]
    latest_paths: set[str] = set()
    completed_tasks: set[str] = set()
    latest_tasks: set[str] = set()
    for row in valid_index_rows:
        task_value = table_cell(index_headers, row, "任务")
        task_ids = set(re.findall(r"\bT\d+\b", task_value))
        completed_tasks.update(task_ids)
        if not task_ids:
            errors.append(f"05-implementation-log.md {table_cell(index_headers, row, '轮次')} 缺少有效 Txx 任务")
        if not table_cell(index_headers, row, "完成标准证据"):
            errors.append(f"05-implementation-log.md {task_value or '任务'} 缺少完成标准证据")
        if not table_cell(index_headers, row, "实际修改文件"):
            errors.append(f"05-implementation-log.md {task_value or '任务'} 缺少实际修改文件")
        if not table_cell(index_headers, row, "验证结果"):
            errors.append(f"05-implementation-log.md {task_value or '任务'} 缺少验证结果")
    for row in latest_rows:
        latest_paths.update(extract_quality_paths(table_cell(index_headers, row, "实际修改文件")))
        latest_tasks.update(
            re.findall(r"\bT\d+\b", table_cell(index_headers, row, "任务"))
        )

    planned_tasks = (
        set(expected_task_ids)
        if expected_task_ids is not None
        else implementation_task_ids(path.parent / "03-tasks.md")
    )
    covered_tasks = latest_tasks if expected_task_ids is not None else completed_tasks
    missing_tasks = sorted(planned_tasks - covered_tasks, key=lambda value: int(value[1:]))
    if missing_tasks:
        errors.append("05-implementation-log.md 尚未覆盖 03-tasks.md 编码任务: " + ", ".join(missing_tasks))

    errors.extend(
        validate_java_and_ddl_evidence(
            text,
            latest_paths,
            "05-implementation-log.md",
            expected_round=latest_round,
            require_round_evidence=(
                "### 4.1 关键规范证据" in text
                or len({table_cell(index_headers, row, "轮次") for row in valid_index_rows}) > 1
            ),
        )
    )
    errors.extend(
        validate_code_quality_self_check(
            extract_section(text, quality_heading),
            "05-implementation-log.md 代码质量自检",
            latest_round,
        )
    )
    if implementation_schema_version(text) >= 2:
        errors.extend(
            validate_implementation_v2_independent_evidence(
                text,
                latest_round,
                actual_paths=latest_paths,
            )
        )

    validation_headers, validation_rows = extract_first_table(extract_section(text, "## 3. 验证记录"))
    latest_validations = [
        row for row in validation_rows if table_cell(validation_headers, row, "轮次") == latest_round
    ]
    if not latest_validations:
        errors.append(f"05-implementation-log.md {latest_round} 缺少验证记录")
    else:
        for index, row in enumerate(latest_validations):
            method = table_cell(validation_headers, row, "命令/方式") or "未命名验证"
            result = table_cell(validation_headers, row, "结果")
            evidence = table_cell(validation_headers, row, "证据")
            reason = table_cell(validation_headers, row, "未验证原因")
            if result == "失败" and index == len(latest_validations) - 1:
                errors.append(f"05-implementation-log.md {latest_round} 存在失败验证（未恢复）: {method}")
            elif result == "通过" and not evidence:
                errors.append(f"05-implementation-log.md {latest_round} 的通过项缺少证据: {method}")
            elif result == "未验证" and not reason:
                errors.append(f"05-implementation-log.md {latest_round} 的未验证项缺少原因: {method}")
            elif result not in {"通过", "失败", "未验证"}:
                errors.append(
                    f"05-implementation-log.md {latest_round} 的验证结果无效: "
                    f"{method}={result or '空'}"
                )
    return errors


def validate_quick_boundary_ready(path: Path) -> list[str]:
    """Quick 只有在业务边界已确认且新模板关键口径已填写时才能进入或完成实现。"""
    if not path.exists():
        return [f"缺少 quick 记录: {path}"]
    text = read_text(path)
    boundary = extract_section(text, "## 1. 边界确认")
    if not boundary:
        return ["quick.md 缺少边界确认章节"]

    errors: list[str] = []
    unresolved_quick_tokens = ["待确认", "TODO", "TBD", "待补充", "未知", "按需", "视情况"]
    marker_mentions = text.count("GGG_QUICK_SCHEMA_VERSION")
    marker_matches = re.findall(
        r"<!--\s*GGG_QUICK_SCHEMA_VERSION:\s*(\d+)\s*-->",
        text,
    )
    if marker_mentions and len(marker_matches) != 1:
        errors.append("quick.md 的 GGG_QUICK_SCHEMA_VERSION 标记畸形或重复，不能降级为 legacy")
    elif marker_matches and marker_matches[0] not in {"2", "3", "4"}:
        errors.append(f"quick.md 使用不支持的 schema 版本: {marker_matches[0]}")

    if extract_line_value(boundary, "- 澄清状态：") != "已确认":
        errors.append("quick.md 澄清状态必须为“已确认”")
    final_confirmation = extract_line_value(boundary, "- 最终边界确认：")
    if not final_confirmation.startswith("已确认"):
        errors.append("quick.md 缺少已确认的最终边界记录")

    core_prefixes = [
        "- 一句话目标：",
        "- 改什么：",
        "- 不改什么：",
        "- 预计主项目 / 代码范围：",
        "- 最小验收信号：",
    ]
    for prefix in core_prefixes:
        if not extract_line_value(boundary, prefix).strip():
            errors.append(f"quick.md 边界确认缺少实质内容: {prefix.rstrip('：')}")

    version = quick_schema_version(text)
    strict = version >= 2
    if strict:
        mode = extract_line_value(boundary, "- 推进模式：").strip()
        if version >= 3:
            if mode != "quick":
                errors.append(f"quick.md v{version} 推进模式必须为 quick")
            recommended_mode = extract_line_value(boundary, "- 推荐模式：").strip()
            recommendation_reason = extract_line_value(boundary, "- 推荐依据：").strip()
            selected_mode = extract_line_value(boundary, "- 最终模式：").strip()
            selection_source = extract_line_value(boundary, "- 模式选择来源：").strip()
            if recommended_mode not in {"quick", "full"}:
                errors.append(f"quick.md v{version} 推荐模式必须为 quick 或 full")
            if selected_mode != "quick":
                errors.append(f"quick.md v{version} 的最终模式必须由用户选择为 quick")
            for value, label in [
                (recommendation_reason, "推荐依据"),
                (selection_source, "模式选择来源"),
            ]:
                if (
                    not meaningful_design_value(value)
                    or vague_design_value(value)
                    or "{{" in value
                    or value in {"用户消息", "用户选择", "AI决定", "已授权"}
                    or any(
                        token in value
                        for token in ["待确认", "TODO", "TBD", "按需", "视情况"]
                    )
                ):
                    errors.append(f"quick.md v{version} {label}缺少可回查的实质内容")
        else:
            if mode not in {
                "quick（自动路由并已告知）",
                "quick（用户明确指定）",
                "quick(自动路由并已告知)",
                "quick(用户明确指定)",
            }:
                errors.append("quick.md v2 必须明确推进模式及自动路由/用户指定来源")

            route_reason = extract_line_value(boundary, "- 路由依据：").strip()
            if (
                not meaningful_design_value(route_reason)
                or vague_design_value(route_reason)
                or any(token in route_reason for token in ["待确认", "TODO", "TBD", "按需", "视情况"])
            ):
                errors.append("quick.md v2 路由依据缺少实质内容")

        confirmation_evidence = (
            final_confirmation[len("已确认"):]
            .strip()
            .strip("（）()")
            .strip()
        )
        if (
            not confirmation_evidence
            or confirmation_evidence in {"用户消息", "确认时间", "记录用户消息或确认时间"}
            or any(token in confirmation_evidence for token in unresolved_quick_tokens)
        ):
            errors.append(
                f"quick.md v{version} 最终边界确认必须记录用户消息定位或确认时间"
            )

        for prefix in core_prefixes:
            value = extract_line_value(boundary, prefix).strip().strip("`")
            if (
                not meaningful_design_value(value)
                or vague_design_value(value)
                or any(token in value for token in ["待确认", "TODO", "TBD", "待补充", "未知"])
            ):
                errors.append(
                    f"quick.md v{version} 边界字段仍未收口: {prefix.rstrip('：')}"
                )

        for prefix, label in [
            ("- 代表性验收例：", "代表性验收例"),
            ("- 失败 / 重复触发补充：", "失败 / 重复触发补充"),
            ("- 兼容性检查：", "兼容性检查"),
        ]:
            if prefix not in boundary:
                errors.append(f"quick.md v{version} 缺少强制字段：{label}")

    if "- 代表性验收例：" in boundary:
        example = extract_line_value(boundary, "- 代表性验收例：").strip().strip("`")
        parts = [
            part.strip()
            for part in re.split(r"\s*(?:->|→)\s*", example)
        ]
        if (
            not example
            or "前置/输入" in example
            or "用户操作或触发" in example
            or (
                strict
                and (
                    len(parts) != 4
                    or any(
                        not meaningful_design_value(part)
                        or any(token in part for token in ["待确认", "TODO", "TBD", "未知"])
                        for part in parts
                    )
                )
            )
        ):
            errors.append("quick.md 代表性验收例仍为空或为模板占位")

    if strict and "- 失败 / 重复触发补充：" in boundary:
        retry = extract_line_value(boundary, "- 失败 / 重复触发补充：").strip().strip("`")
        if (
            not meaningful_design_value(retry)
            or "失败、重试或再次操作时的预期" in retry
            or retry == "不涉及"
            or (retry.startswith("不涉及") and not re.match(r"^不涉及[：:].+", retry))
        ):
            errors.append(
                f"quick.md v{version} 失败 / 重复触发补充必须写明具体口径或“不涉及：原因”"
            )

    if "- 兼容性检查：" in boundary:
        compatibility = extract_line_value(boundary, "- 兼容性检查：").strip().strip("`")
        if (
            not compatibility
            or "无影响/有影响/未知" in compatibility
            or "未知" in compatibility
        ):
            errors.append("quick.md 兼容性检查尚未收口现有调用方、历史数据或重复请求/重试")
        elif strict:
            items = [
                item.strip()
                for item in re.split(r"[；;]", compatibility)
                if item.strip()
            ]
            parsed: dict[str, list[str]] = {}
            for item in items:
                if "=" not in item:
                    continue
                label, value = [part.strip() for part in item.split("=", 1)]
                parsed.setdefault(label, []).append(value)
            expected_labels = {"现有调用方", "历史数据", "重复请求或重试"}
            if set(parsed) != expected_labels:
                errors.append(
                    f"quick.md v{version} 兼容性检查必须且只能覆盖现有调用方、历史数据、重复请求或重试"
                )
            for label in expected_labels:
                values = parsed.get(label, [])
                if (
                    len(values) != 1
                    or not meaningful_design_value(values[0])
                    or any(token in values[0] for token in unresolved_quick_tokens)
                ):
                    errors.append(
                        f"quick.md v{version} 兼容性检查缺少已收口项：{label}"
                    )

    question_tables = [
        (headers, rows)
        for headers, rows in iter_markdown_tables(boundary)
        if "疑问" in headers or "状态" in headers
    ]
    if strict and len(question_tables) != 1:
        errors.append(f"quick.md v{version} 必须且只能有一个疑问账本")

    for headers, rows in question_tables:
        required_headers = (
            ["编号", "疑问", "影响级别", "准确来源", "为什么不确定", "用户结论", "状态"]
            if strict
            else ["编号", "疑问", "准确来源", "为什么不确定", "用户结论", "状态"]
        )
        missing_headers = [header for header in required_headers if header not in headers]
        if missing_headers:
            errors.append(
                f"quick.md {f'v{version} ' if strict else ''}疑问账本缺少列: "
                + ", ".join(missing_headers)
            )
            continue
        question_ids: list[str] = []
        for row in rows:
            question_id = table_cell(headers, row, "编号")
            if not any(cell.strip() for cell in row):
                continue
            if not re.fullmatch(r"Q\d+", question_id or ""):
                errors.append(f"quick.md 疑问账本包含非法编号: {question_id or '空'}")
                continue
            question_ids.append(question_id)
            if table_cell(headers, row, "状态") != "已确认":
                errors.append(f"quick.md 仍有未确认问题: {question_id}")
            if strict:
                level = table_cell(headers, row, "影响级别")
                if level not in {"高影响阻塞", "低风险"}:
                    errors.append(f"quick.md {question_id} 影响级别非法或缺失: {level or '空'}")
                for header in ["疑问", "准确来源", "为什么不确定", "用户结论"]:
                    value = table_cell(headers, row, header)
                    if (
                        not meaningful_design_value(value)
                        or any(token in value for token in ["待确认", "TODO", "TBD", "待补充", "未知"])
                    ):
                        errors.append(f"quick.md {question_id} 缺少实质内容: {header}")
                source = table_cell(headers, row, "准确来源")
                if source in {"用户消息", "PRD", "PRD 章节", "PRD 章节 / 用户消息"}:
                    errors.append(f"quick.md {question_id} 准确来源必须包含可回查定位")
        for duplicate in sorted({item for item in question_ids if question_ids.count(item) > 1}):
            errors.append(f"quick.md 疑问编号重复: {duplicate}")
    return errors


def validate_quick_implementation_completion(path: Path) -> list[str]:
    """验证 quick.md 的实现质量证据。"""
    if not path.exists():
        return [f"缺少 quick 记录: {path}"]

    errors: list[str] = []
    text = read_text(path)
    if "### 4.1 逐文件代码质量门禁" in text:
        actual_paths = extract_quality_paths(extract_line_value(text, "- 修改文件："))
        errors.extend(validate_legacy_loaded_norms(text, actual_paths, "quick.md"))
        quality_section = extract_section(text, "### 4.1 逐文件代码质量门禁")
        headers, rows = extract_first_table(quality_section)
        required = [
            "文件", "文件角色", "适用检查项", "证据（文件行号/命令）", "结论", "未通过处理"
        ]
        if not all(header in headers for header in required):
            errors.append("quick.md 旧版逐文件代码质量门禁缺少关键表头")
        else:
            covered: set[str] = set()
            substantive = 0
            for row in rows:
                file_value = table_cell(headers, row, "文件")
                if not file_value:
                    continue
                substantive += 1
                covered.update(extract_quality_paths(file_value))
                if not table_cell(headers, row, "适用检查项"):
                    errors.append(f"quick 旧版逐文件门禁的 {file_value} 缺少适用检查项")
                if not table_cell(headers, row, "证据（文件行号/命令）"):
                    errors.append(f"quick 旧版逐文件门禁的 {file_value} 缺少证据")
                if table_cell(headers, row, "结论") not in {"通过", "不适用"}:
                    errors.append(f"quick 旧版逐文件门禁的 {file_value} 未通过或结论未收口")
            if not substantive:
                errors.append("quick.md 缺少已填写的旧版逐文件代码质量门禁记录")
            missing = sorted(actual_paths - covered)
            if missing:
                errors.append("quick 旧版逐文件门禁未覆盖实际修改文件: " + ", ".join(missing))
        errors.extend(
            validate_high_frequency_quality_table(
                extract_section(text, "### 4.2 高频漏项复核"),
                "quick.md 旧版高频漏项复核",
                "证据或不适用原因",
                {"通过", "不适用"},
            )
        )
        return errors
    quality_heading = "### 4.1 代码质量自检"
    assert_contains(text, [quality_heading, "### 4.2 运行验证"], path.name, errors)

    actual_quality_paths = extract_quality_paths(extract_line_value(text, "- 修改文件："))
    errors.extend(
        validate_java_and_ddl_evidence(
            text,
            actual_quality_paths,
            "quick.md",
        )
    )
    errors.extend(
        validate_code_quality_self_check(
            extract_section(text, quality_heading),
            "quick.md 代码质量自检",
        )
    )
    if quick_schema_version(text) >= 3:
        latest_round = extract_line_value(text, "- 当前实现轮次：")
        if not re.fullmatch(r"I\d+", latest_round):
            errors.append("quick.md 缺少有效当前实现轮次，无法校验独立契约与可观测性证据")
        else:
            errors.extend(
                validate_implementation_v2_independent_evidence(
                    text,
                    latest_round,
                    section_heading="#### 4.1.1 独立契约与可观测性证据",
                    record_label="quick.md",
                    actual_paths=actual_quality_paths,
                )
            )
    if not extract_line_value(text, "- 完成标准证据："):
        errors.append("quick.md 缺少完成标准证据")
    validation_method = extract_line_value(text, "- 验证命令 / 方式：")
    validation_result = extract_line_value(text, "- 验证结果：")
    unverified = extract_line_value(text, "- 未验证项：")
    if validation_result == "失败":
        errors.append("quick.md 仍存在失败验证")
    elif validation_result == "通过" and not validation_method:
        errors.append("quick.md 验证通过时必须记录验证命令或方式")
    elif validation_result == "未验证" and not unverified:
        errors.append("quick.md 未验证时必须记录未验证项及原因")
    elif validation_result not in {"通过", "失败", "未验证"}:
        errors.append("quick.md 验证结果必须明确为：通过、失败或未验证")
    return errors


OPTIONAL_REVIEW_ITEMS = ["代码与需求是否有偏差", "代码质量与格式"]


def validate_optional_review(
    record: Path,
    result: str,
    expected_implementation_round: str,
    expected_fingerprint: str,
) -> list[str]:
    """校验单一可选 Review，只保留需求偏差、代码质量与格式两项。"""
    expected_label = {
        "passed": "通过",
        "needs_changes": "需修改",
        "blocked": "阻塞",
    }[result]
    if record.name == "quick.md":
        if not record.exists():
            return ["缺少 quick.md"]
        text = read_text(record)
        section = extract_section(text, "### 5.1 可选 Review")
        errors: list[str] = []
        if quick_schema_version(text) < 4:
            return ["quick.md 不是可选 Review v4 工件"]
        if extract_line_value(text, "- Review 状态：") != "已执行":
            errors.append("quick.md Review 状态必须为“已执行”")
        if extract_line_value(text, "- Review 结论：") != expected_label:
            errors.append(f"quick.md Review 结论必须为“{expected_label}”")
        if extract_line_value(text, "- Review 对应实现轮次：") != expected_implementation_round:
            errors.append("quick.md Review 对应实现轮次不一致")
        if extract_line_value(text, "- Review 对应差异指纹：") != expected_fingerprint:
            errors.append("quick.md Review 对应差异指纹不一致")
        unresolved = extract_line_value(text, "- Review 未解决问题：").strip()
        label = "quick.md"
    else:
        path = record.parent / "06-code-review.md"
        if not path.exists():
            return ["缺少 06-code-review.md"]
        text = read_text(path)
        section = extract_section(text, "## 2. 两项检查")
        errors = []
        assert_contains(text, CODE_REVIEW_SIMPLE_REQUIRED_TOKENS, path.name, errors)
        if extract_line_value(text, "- 对应实现轮次：") != expected_implementation_round:
            errors.append("06-code-review.md 对应实现轮次不一致")
        if extract_line_value(text, "- 实现差异指纹：") != expected_fingerprint:
            errors.append("06-code-review.md 实现差异指纹不一致")
        for prefix in ["- 需求依据：", "- 检查范围："]:
            value = extract_line_value(text, prefix).strip()
            if not meaningful_design_value(value) or value in EMPTY_VALUES:
                errors.append(f"06-code-review.md 缺少实质内容: {prefix}")
        if extract_line_value(text, "- 结论：") != expected_label:
            errors.append(f"06-code-review.md 结论必须为“{expected_label}”")
        unresolved = extract_line_value(text, "- 未解决问题：").strip()
        label = "06-code-review.md"

    headers, rows = extract_first_table(section)
    required_headers = ["检查项", "结论", "问题与定位"]
    if not all(header in headers for header in required_headers):
        return errors + [f"{label} 可选 Review 表缺少关键表头"]
    by_item: dict[str, list[list[str]]] = {}
    actual_items: list[str] = []
    for row in rows:
        item = table_cell(headers, row, "检查项")
        if item:
            actual_items.append(item)
            by_item.setdefault(item, []).append(row)
    unknown_items = sorted(set(actual_items) - set(OPTIONAL_REVIEW_ITEMS))
    if unknown_items:
        errors.append(f"{label} 只允许两项检查，不应包含: " + "、".join(unknown_items))
    if len(actual_items) != len(OPTIONAL_REVIEW_ITEMS):
        errors.append(f"{label} 必须恰好包含两条检查")
    conclusions: list[str] = []
    for item in OPTIONAL_REVIEW_ITEMS:
        matches = by_item.get(item, [])
        if len(matches) != 1:
            errors.append(f"{label} 必须且只能有一条“{item}”")
            continue
        row = matches[0]
        conclusion = table_cell(headers, row, "结论")
        problem = table_cell(headers, row, "问题与定位").strip()
        conclusions.append(conclusion)
        if conclusion not in {"通过", "有问题", "阻塞"}:
            errors.append(f"{label} 的“{item}”结论无效")
        if conclusion == "通过":
            if problem not in {"无", "不涉及"}:
                errors.append(f"{label} 的“{item}”通过时问题与定位应为“无”")
        elif (
            problem in EMPTY_VALUES
            or "文件:行号" in problem
            or len(problem) < 8
        ):
            errors.append(f"{label} 的“{item}”有问题或阻塞时必须写明定位和影响")

    if result == "passed" and conclusions != ["通过", "通过"]:
        errors.append(f"{label} 登记通过时两项检查都必须为通过")
    if result == "needs_changes" and "有问题" not in conclusions:
        errors.append(f"{label} 登记需修改时至少一项必须为有问题")
    if result == "blocked" and "阻塞" not in conclusions:
        errors.append(f"{label} 登记阻塞时至少一项必须为阻塞")
    if result == "passed" and unresolved not in {"无", "不涉及"}:
        errors.append(f"{label} 通过时必须明确没有未解决问题")
    if result != "passed" and (
        unresolved in EMPTY_VALUES
        or unresolved in {"无", "不涉及", "具体问题"}
    ):
        errors.append(f"{label} 非通过结论必须记录未解决问题")
    return errors


def validate_code_review_artifacts(index_path: Path, rounds_dir: Path) -> list[str]:
    errors: list[str] = []
    if index_path.exists():
        text = read_text(index_path)
        if review_schema_version(text) >= 2:
            assert_contains(
                text,
                CODE_REVIEW_SIMPLE_REQUIRED_TOKENS,
                index_path.name,
                errors,
            )
            assert_table_has_headers(
                extract_section(text, "## 2. 两项检查"),
                ["检查项", "结论", "问题与定位"],
                "06-code-review.md 可选 Review 表缺少关键表头",
                errors,
            )
            return errors
        assert_contains(
            text,
            CODE_REVIEW_INDEX_REQUIRED_TOKENS[:2],
            index_path.name,
            errors,
        )
        if not review_ledger_section(text):
            errors.append(
                f"{index_path.name} 缺少关键内容: "
                f"{CODE_REVIEW_INDEX_REQUIRED_TOKENS[2]}"
            )
        assert_table_has_headers(
            text,
            ["轮次", "结论", "明细文档", "未关闭问题"],
            "06-code-review.md Review 轮次索引缺少关键表头: 轮次、结论、明细文档、未关闭问题",
            errors,
        )

    if rounds_dir.exists() and rounds_dir.is_dir():
        for round_file in sorted(rounds_dir.glob("review-r*.md")):
            text = read_text(round_file)
            if "## 3. Gate A：Spec Compliance" in text:
                assert_contains(text, CODE_REVIEW_ROUND_REQUIRED_TOKENS, round_file.name, errors)
                assert_table_has_headers(
                    extract_section(text, "## 2. 完整 Diff 覆盖"),
                    ["Diff 路径", "变更类型", "需求/任务来源", "风险标签", "结论/CRxx"],
                    f"{round_file.name} 完整 Diff 覆盖表缺少关键表头",
                    errors,
                )
                assert_table_has_headers(
                    extract_section(text, "## 5. 问题清单"),
                    ["问题编号", "级别", "Gate", "文件行号/全局依据", "问题", "状态"],
                    f"{round_file.name} 问题清单缺少关键表头",
                    errors,
                )
            elif (
                "# Light Code Review 轮次明细" in text
                or extract_line_value(text, "- Review disposition：") == "light"
            ):
                assert_contains(
                    text,
                    [
                        "## 1. 基本信息",
                        "## 2. Light Review 结论",
                        "- 业务逻辑结论：",
                        "- 代码质量结论：",
                        "- 文档一致性结论：",
                        "- 契约 / SQL 结论：",
                        "- 异常 / 日志 / Trace 结论：",
                        "## 3. 评审结论",
                    ],
                    round_file.name,
                    errors,
                )
                assert_table_has_headers(
                    extract_section(text, "## 2. Light Review 结论"),
                    ["定位", "类型", "问题或确认事实", "影响", "处理"],
                    f"{round_file.name} Light Review 结论表缺少关键表头",
                    errors,
                )
            else:
                legacy_tokens = [
                    "## 1. 基本信息",
                    "## 2. 评审结论",
                    "## 3. 问题清单",
                    "## 4. 一致性复核",
                    "## 5. 幻觉审计",
                    "## 6. 修复闭环",
                ]
                assert_contains(text, legacy_tokens, round_file.name, errors)
                assert_table_has_headers(
                    text,
                    ["级别", "文件行号", "问题", "状态"],
                    f"{round_file.name} 问题清单缺少关键表头: 级别、文件行号、问题、状态",
                    errors,
                )
    return errors


def validate_light_code_review_completion(
    index_path: Path,
    rounds_dir: Path,
    expected_implementation_round: str | None = None,
    expected_fingerprint: str | None = None,
) -> list[str]:
    """验证新版 light Review 的最小逻辑、代码、契约和文档证据。"""
    errors = validate_code_review_artifacts(index_path, rounds_dir)
    if not index_path.exists():
        return errors or ["缺少 06-code-review.md"]
    index_text = read_text(index_path)
    if extract_line_value(index_text, "- Review disposition：") != "light":
        errors.append("06-code-review.md Review disposition 必须为 light")
    if extract_line_value(index_text, "- 当前结论：") != "通过":
        errors.append("06-code-review.md light Review 当前结论必须为“通过”")
    if extract_line_value(index_text, "- Review 门禁是否满足：") not in {"是", "通过"}:
        errors.append("06-code-review.md light Review 门禁必须为“是”")

    round_files = (
        sorted(
            rounds_dir.glob("review-r*.md"),
            key=lambda path: (review_round_number(path), path.name),
        )
        if rounds_dir.exists()
        else []
    )
    if not round_files:
        errors.append("light Review 缺少 review-rNN.md 明细")
        return errors
    latest = round_files[-1]
    text = read_text(latest)
    if extract_line_value(text, "- Review disposition：") != "light":
        errors.append(f"{latest.name} Review disposition 必须为 light")
    if extract_line_value(text, "- 结论：") != "通过":
        errors.append(f"{latest.name} light Review 结论必须为“通过”")
    if extract_line_value(text, "- 是否可进入测试验证：") not in {"是", "允许"}:
        errors.append(f"{latest.name} light Review 必须明确允许进入测试验证")
    if extract_line_value(text, "- 需要回到实现阶段的问题：") not in {"无", "不涉及"}:
        errors.append(f"{latest.name} light Review 仍有需要回到实现阶段的问题")

    for prefix in [
        "- 业务逻辑结论：",
        "- 代码质量结论：",
        "- 文档一致性结论：",
    ]:
        if extract_line_value(text, prefix) != "通过":
            errors.append(f"{latest.name} 通过时 {prefix}必须为通过")
    for prefix in ["- 契约 / SQL 结论：", "- 异常 / 日志 / Trace 结论："]:
        value = extract_line_value(text, prefix)
        if value != "通过" and not (
            value.startswith("不涉及：") and len(value) > len("不涉及：")
        ):
            errors.append(
                f"{latest.name} 通过时 {prefix}必须为通过或“不涉及：具体原因”"
            )

    recorded_round = extract_line_value(text, "- 对应实现轮次：")
    recorded_fingerprint = extract_line_value(text, "- 实现差异指纹：")
    if expected_implementation_round and recorded_round != expected_implementation_round:
        errors.append(f"{latest.name} 对应实现轮次与当前完成快照不一致")
    if expected_fingerprint and recorded_fingerprint != expected_fingerprint:
        errors.append(f"{latest.name} 实现差异指纹与当前完成快照不一致")
    return errors


REVIEW_SEVERITIES = {"阻塞", "必须修", "建议修", "提示"}
REVIEW_ISSUE_STATUSES = {"open", "fixed", "accepted", "not-applicable"}
REVIEW_CLOSED_STATUSES = {"fixed", "not-applicable"}
REVIEWER_MODES = {"fresh-review", "self-review"}
SELF_REVIEW_PLACEHOLDERS = {
    "",
    "无",
    "不适用",
    "不可用",
    "工具不可用",
    "无法使用",
    "待填写",
    "原因",
}
HALLUCINATION_AUDIT_ITEMS = [
    "无证据结论",
    "文档有但代码未实现",
    "代码实现但文档/任务未记录",
    "测试声称通过但无执行证据",
    "未覆盖被写成不存在",
]


def validate_review_provenance(
    text: str,
    label: str,
    expected_mode: str | None = None,
    expected_self_review_reason: str | None = None,
) -> list[str]:
    """新 Review 必须显式披露 fresh/self；旧工件没有字段时保持可读兼容。"""
    errors: list[str] = []
    mode = extract_line_value(text, "- Review 方式：")
    reason = extract_line_value(text, "- Self-review 原因：")
    has_mode_field = any(
        line.strip().startswith("- Review 方式：")
        for line in text.splitlines()
    )
    if not has_mode_field and expected_mode is None:
        return errors
    if mode not in REVIEWER_MODES:
        errors.append(f"{label} Review 方式必须为 fresh-review 或 self-review")
        return errors
    if expected_mode is not None and mode != expected_mode:
        errors.append(f"{label} Review 方式与登记命令不一致")
    if mode == "fresh-review":
        if reason != "不适用":
            errors.append(f"{label} fresh-review 的 Self-review 原因必须为“不适用”")
        if expected_self_review_reason not in {None, "", "不适用"}:
            errors.append(f"{label} fresh-review 不得登记 self-review 原因")
        return errors

    normalized_reason = reason.strip()
    if normalized_reason in SELF_REVIEW_PLACEHOLDERS or len(normalized_reason) < 8:
        errors.append(f"{label} self-review 必须记录 fresh reviewer 不可用的具体原因")
    if (
        expected_self_review_reason is not None
        and normalized_reason != expected_self_review_reason.strip()
    ):
        errors.append(f"{label} Self-review 原因与登记命令不一致")
    return errors


def review_round_number(path: Path) -> int:
    match = re.fullmatch(r"review-r(\d+)\.md", path.name)
    return int(match.group(1)) if match else -1


def validate_review_diff_manifest(
    round_text: str,
    actual_paths: set[str] | None,
    label: str,
) -> list[str]:
    errors: list[str] = []
    section = extract_section(round_text, "## 2. 完整 Diff 覆盖")
    headers, rows = extract_first_table(section)
    required = [
        "Diff 路径",
        "变更类型",
        "需求/任务来源",
        "行为与影响面",
        "风险标签",
        "Gate A 证据",
        "Gate B 模块",
        "结论/CRxx",
    ]
    if not all(header in headers for header in required):
        return [f"{label} 完整 Diff 覆盖缺少关键表头: {', '.join(required)}"]

    covered: set[str] = set()
    for row in rows:
        path_value = table_cell(headers, row, "Diff 路径")
        paths = extract_quality_paths(path_value)
        if not paths:
            continue
        if len(paths) != 1:
            errors.append(f"{label} 每个 Diff 覆盖行必须且只能记录一个路径: {path_value}")
            continue
        path = next(iter(paths))
        if path in covered:
            errors.append(f"{label} Diff 路径重复: {path}")
        covered.add(path)
        for header in required[1:]:
            if table_cell(headers, row, header) in EMPTY_VALUES:
                errors.append(f"{label} {path} 缺少{header}")

    expected = (
        {normalize_quality_path(path) for path in actual_paths}
        if actual_paths is not None
        else set(covered)
    )
    if actual_paths is not None:
        missing = sorted(expected - covered)
        extra = sorted(covered - expected)
        if missing:
            errors.append(f"{label} 未覆盖真实 Diff 文件: " + ", ".join(missing))
        if extra:
            errors.append(f"{label} 覆盖了不属于当前实现快照的文件: " + ", ".join(extra))

    actual_count = extract_line_value(section, "- 实际 diff 文件数：")
    covered_count = extract_line_value(section, "- 已覆盖文件数：")
    uncovered = extract_line_value(section, "- 未覆盖文件：")
    if actual_count != str(len(expected)):
        errors.append(f"{label} 实际 diff 文件数与当前快照不一致")
    if covered_count != str(len(covered)):
        errors.append(f"{label} 已覆盖文件数与覆盖表不一致")
    if uncovered not in {"无", "0"}:
        errors.append(f"{label} 仍声明存在未覆盖文件")
    return errors


def validate_review_gate_a(
    round_text: str,
    label: str,
    expected_source_ids: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    section = extract_section(round_text, "## 3. Gate A：Spec Compliance")
    if extract_line_value(section, "- Gate A 结论：") != "通过":
        errors.append(f"{label} Gate A 必须先明确为通过")
    headers, rows = extract_first_table(section)
    required_items = [
        "需求要求但未实现",
        "已实现但行为偏差",
        "超出确认范围",
        "契约、数据、权限和兼容性",
        "结论与验证证据真实性",
    ]
    rows_by_item = {table_cell(headers, row, "检查面"): row for row in rows}
    evidence_parts: list[str] = []
    for item in required_items:
        row = rows_by_item.get(item)
        if row is None:
            errors.append(f"{label} Gate A 缺少检查面: {item}")
            continue
        if table_cell(headers, row, "结论") != "通过":
            errors.append(f"{label} Gate A“{item}”未通过")
        if table_cell(headers, row, "独立证据") in EMPTY_VALUES:
            errors.append(f"{label} Gate A“{item}”缺少独立证据")
        evidence_parts.append(table_cell(headers, row, "独立证据"))
    manifest_headers, manifest_rows = extract_first_table(
        extract_section(round_text, "## 2. 完整 Diff 覆盖")
    )
    evidence_parts.extend(
        table_cell(manifest_headers, row, "需求/任务来源")
        for row in manifest_rows
    )
    evidence_text = "\n".join(evidence_parts)
    missing_sources = sorted(
        source_id
        for source_id in (expected_source_ids or set())
        if not re.search(rf"\b{re.escape(source_id)}\b", evidence_text)
    )
    if missing_sources:
        errors.append(f"{label} Gate A 未覆盖权威来源: " + ", ".join(missing_sources))
    return errors


def validate_review_gate_b(round_text: str, label: str) -> list[str]:
    errors: list[str] = []
    section = extract_section(round_text, "## 4. Gate B：Risk-driven Code Quality")
    if extract_line_value(section, "- Gate B 结论：") != "通过":
        errors.append(f"{label} Gate B 必须明确为通过")
    core = extract_section(round_text, "### 4.1 核心质量面")
    headers, rows = extract_first_table(core)
    required_items = ["正确性", "安全与权限", "数据一致性", "失败边界", "兼容性", "验证充分性"]
    rows_by_item = {table_cell(headers, row, "核心面"): row for row in rows}
    for item in required_items:
        row = rows_by_item.get(item)
        if row is None:
            errors.append(f"{label} Gate B 缺少核心面: {item}")
            continue
        conclusion = table_cell(headers, row, "结论")
        allowed = {"通过", "不涉及"} if item in {"数据一致性", "兼容性"} else {"通过"}
        if conclusion not in allowed:
            errors.append(f"{label} Gate B“{item}”未通过")
        if table_cell(headers, row, "独立证据") in EMPTY_VALUES:
            errors.append(f"{label} Gate B“{item}”缺少独立证据或不适用依据")

    module = extract_section(round_text, "### 4.2 触发的风险模块")
    module_headers, module_rows = extract_first_table(module)
    for row in module_rows:
        name = table_cell(module_headers, row, "模块")
        if name in EMPTY_VALUES:
            continue
        for header in ["Diff 触发证据", "独立证据（文件行号/命令）"]:
            if table_cell(module_headers, row, header) in EMPTY_VALUES:
                errors.append(f"{label} 风险模块“{name}”缺少{header}")
        if table_cell(module_headers, row, "结论") != "通过":
            errors.append(f"{label} 风险模块“{name}”未通过")
    return errors


def review_issue_table(text: str) -> tuple[list[str], list[list[str]]]:
    heading = "## 5. 问题清单" if "## 5. 问题清单" in text else "## 3. 问题清单"
    return extract_first_table(extract_section(text, heading))


def review_ledger_section(text: str) -> str:
    for heading in ["## 3. 问题账本（含历史）", "## 3. 未关闭问题"]:
        section = extract_section(text, heading)
        if section:
            return section
    return ""


def validate_review_issue_history(
    index_text: str,
    round_files: list[Path],
    latest_text: str,
) -> list[str]:
    """确保 CRxx 账本和轮次文件连续，历史问题不会被删除或换号。"""
    errors: list[str] = []
    round_numbers = [review_round_number(path) for path in round_files]
    if round_numbers and round_numbers != list(range(1, max(round_numbers) + 1)):
        errors.append("Review 轮次文件不连续，可能有历史轮次被删除")

    historical: dict[str, tuple[str, str]] = {}
    previous_open: set[str] = set()
    for path in round_files:
        headers, rows = review_issue_table(read_text(path))
        for row in rows:
            issue_id = table_cell(headers, row, "问题编号")
            if not re.fullmatch(r"CR\d+", issue_id):
                continue
            signature = (
                table_cell(headers, row, "级别"),
                table_cell(headers, row, "问题"),
            )
            previous = historical.get(issue_id)
            if previous and previous != signature:
                errors.append(f"{issue_id} 在不同 Review 轮次被复用为不同问题")
            historical[issue_id] = signature
            if path != round_files[-1]:
                if table_cell(headers, row, "状态") == "open":
                    previous_open.add(issue_id)
                else:
                    previous_open.discard(issue_id)

    if historical:
        numbers = sorted(int(issue_id[2:]) for issue_id in historical)
        if numbers != list(range(1, max(numbers) + 1)):
            errors.append("CRxx 编号不连续，可能有历史问题被删除或跳号")

    ledger_headers, ledger_rows = extract_first_table(review_ledger_section(index_text))
    ledger: dict[str, list[str]] = {}
    for row in ledger_rows:
        issue_id = table_cell(ledger_headers, row, "问题编号")
        if not re.fullmatch(r"CR\d+", issue_id):
            continue
        if issue_id in ledger:
            errors.append(f"06-code-review.md CRxx 账本编号重复: {issue_id}")
        ledger[issue_id] = row
    missing_ledger = sorted(set(historical) - set(ledger))
    if missing_ledger:
        errors.append("06-code-review.md CRxx 账本遗漏历史问题: " + ", ".join(missing_ledger))

    closure_headers, closure_rows = extract_first_table(
        extract_section(latest_text, "## 6. 历史问题继承与修复闭环")
    )
    inherited = {
        table_cell(closure_headers, row, "问题编号")
        for row in closure_rows
        if re.fullmatch(r"CR\d+", table_cell(closure_headers, row, "问题编号"))
    }
    missing_inherited = sorted(previous_open - inherited)
    if missing_inherited:
        errors.append(
            "最新 Review 未继承上轮未关闭问题: " + ", ".join(missing_inherited)
        )
    for issue_id, row in ledger.items():
        severity = table_cell(ledger_headers, row, "级别")
        status = table_cell(ledger_headers, row, "当前状态")
        evidence = table_cell(ledger_headers, row, "关闭依据")
        if status not in REVIEW_ISSUE_STATUSES:
            errors.append(f"06-code-review.md {issue_id} 状态不合法: {status or '空'}")
        if status in REVIEW_CLOSED_STATUSES and evidence in EMPTY_VALUES:
            errors.append(f"06-code-review.md {issue_id} 已关闭但缺少关闭依据")
        if severity in {"阻塞", "必须修"} and status not in REVIEW_CLOSED_STATUSES:
            errors.append(f"06-code-review.md {issue_id} 仍是未关闭的{severity}问题")
    return errors


def validate_review_problem_closure(round_text: str, label: str) -> list[str]:
    """Review 通过时禁止问题清单仍保留未关闭的阻塞或必须修问题。"""
    errors: list[str] = []
    new_format = "## 5. 问题清单" in round_text
    issue_heading = "## 5. 问题清单" if new_format else "## 3. 问题清单"
    closure_heading = (
        "## 6. 历史问题继承与修复闭环"
        if new_format
        else "## 6. 修复闭环"
    )
    headers, rows = extract_first_table(extract_section(round_text, issue_heading))
    closure_headers, closure_rows = extract_first_table(extract_section(round_text, closure_heading))
    closures_by_id = {
        table_cell(closure_headers, row, "问题编号"): row
        for row in closure_rows
        if re.fullmatch(r"CR\d+", table_cell(closure_headers, row, "问题编号"))
    }
    rows_by_id: dict[str, list[str]] = {}
    for row in rows:
        issue_id = table_cell(headers, row, "问题编号")
        if not re.fullmatch(r"CR\d+", issue_id):
            continue
        if issue_id in rows_by_id:
            errors.append(f"{label} 问题编号重复: {issue_id}")
        rows_by_id[issue_id] = row
        severity = table_cell(headers, row, "级别")
        status = table_cell(headers, row, "状态")
        if severity not in REVIEW_SEVERITIES:
            errors.append(f"{label} {issue_id} 级别不合法: {severity or '空'}")
        if status not in REVIEW_ISSUE_STATUSES:
            errors.append(f"{label} {issue_id} 状态不合法: {status or '空'}")
        for field in ["问题", "风险", "建议"]:
            if not table_cell(headers, row, field):
                errors.append(f"{label} {issue_id} 缺少{field}")
        if severity in {"阻塞", "必须修"} and status not in REVIEW_CLOSED_STATUSES:
            errors.append(f"{label} {issue_id} 仍是未关闭的{severity}问题")
        elif severity in {"阻塞", "必须修"}:
            closure = closures_by_id.get(issue_id)
            if closure is None:
                errors.append(f"{label} {issue_id} 缺少修复闭环记录")
            else:
                result_header = "本轮结果" if new_format else "复审结果"
                if (
                    table_cell(closure_headers, closure, result_header) != "已关闭"
                    or table_cell(closure_headers, closure, "关闭依据") in EMPTY_VALUES
                ):
                    errors.append(f"{label} {issue_id} 缺少有效复审结果或关闭依据")
    return errors


def validate_review_hallucination_audit(round_text: str, label: str) -> list[str]:
    """Review 通过时要求全部幻觉审计项有独立证据并收口。"""
    errors: list[str] = []
    headers, rows = extract_first_table(extract_section(round_text, "## 5. 幻觉审计"))
    rows_by_item = {table_cell(headers, row, "审计项"): row for row in rows}
    for item in HALLUCINATION_AUDIT_ITEMS:
        row = rows_by_item.get(item)
        if row is None:
            errors.append(f"{label} 幻觉审计缺少审计项: {item}")
            continue
        result = table_cell(headers, row, "结论")
        if result not in {"通过", "不适用"}:
            errors.append(f"{label} 幻觉审计“{item}”仍未通过")
        if table_cell(headers, row, "证据") in EMPTY_VALUES:
            errors.append(f"{label} 幻觉审计“{item}”缺少独立证据")
    return errors


def validate_review_consistency_summary(round_text: str, label: str) -> list[str]:
    errors: list[str] = []
    section = extract_section(round_text, "## 4. 一致性复核")
    for item in [
        "可评审性",
        "需求/方案一致性",
        "注释和日志链路",
        "依赖/配置变更",
        "安全风险",
        "测试验证缺口",
        "幻觉审计",
    ]:
        value = extract_line_value(section, f"- {item}：")
        if not value:
            errors.append(f"{label} 一致性复核缺少结论: {item}")
        elif item == "测试验证缺口":
            if not value.startswith(("无", "不涉及", "通过")):
                errors.append(f"{label} 一致性复核“{item}”仍未收口")
        elif not value.startswith(("通过", "不涉及", "无")):
            errors.append(f"{label} 一致性复核“{item}”仍未通过")
    return errors


def validate_review_index_sync(
    index_text: str,
    latest_round: Path,
    round_id: str,
    label: str,
) -> list[str]:
    """确保索引、轮次明细和未关闭问题状态一致。"""
    errors: list[str] = []
    expected_number = review_round_number(latest_round)
    if expected_number < 0:
        errors.append(f"{label} 文件名必须使用 review-rNN.md")
    elif round_id != f"R{expected_number}":
        errors.append(f"{label} 轮次与文件名不一致: {round_id or '空'}")

    if extract_line_value(index_text, "- 最新轮次：") != round_id:
        errors.append("06-code-review.md 最新轮次与 Review 明细不一致")
    if extract_line_value(index_text, "- 是否允许进入测试验证：") not in {"是", "允许"}:
        errors.append("06-code-review.md Review 通过时必须明确允许进入测试验证")
    if extract_line_value(index_text, "- 需要回到实现阶段的问题：") not in {"无", "不涉及"}:
        errors.append("06-code-review.md Review 通过时不得保留需要回到实现阶段的问题")

    headers, rows = extract_first_table(extract_section(index_text, "## 1. Review 轮次索引"))
    matching = [row for row in rows if table_cell(headers, row, "轮次") == round_id]
    if len(matching) != 1:
        errors.append(f"06-code-review.md 必须且只能有一条 {round_id} 索引")
    else:
        row = matching[0]
        if table_cell(headers, row, "结论") != "通过":
            errors.append(f"06-code-review.md {round_id} 索引结论必须为通过")
        detail = table_cell(headers, row, "明细文档")
        if Path(detail).name != latest_round.name:
            errors.append(f"06-code-review.md {round_id} 明细文档与最新轮次文件不一致")

    issue_headers, issue_rows = extract_first_table(review_ledger_section(index_text))
    for row in issue_rows:
        issue_id = table_cell(issue_headers, row, "问题编号")
        if not re.fullmatch(r"CR\d+", issue_id):
            continue
        severity = table_cell(issue_headers, row, "级别")
        status = table_cell(issue_headers, row, "当前状态")
        if severity in {"阻塞", "必须修"} and status not in REVIEW_CLOSED_STATUSES:
            errors.append(f"06-code-review.md {issue_id} 仍是未关闭的{severity}问题")
        elif severity in {"阻塞", "必须修"} and table_cell(issue_headers, row, "关闭依据") in EMPTY_VALUES:
            errors.append(f"06-code-review.md {issue_id} 缺少关闭依据")
    return errors


def validate_review_diff_evidence(
    quality_section: str,
    actual_paths: set[str],
    label: str,
) -> list[str]:
    """将 full Review 的关键 Java/DDL 复核绑定到当前真实差异。"""
    errors: list[str] = []
    headers, rows = extract_first_table(quality_section)
    rows_by_item = {table_cell(headers, row, "检查项"): row for row in rows}

    java_paths = {path for path in actual_paths if path.lower().endswith(".java")}
    key_row = rows_by_item.get("关键业务逻辑注释")
    if java_paths and key_row:
        result = table_cell(headers, key_row, "结论")
        if result == "通过":
            evidence = " ".join(
                [
                    table_cell(headers, key_row, "适用文件"),
                    table_cell(headers, key_row, "独立证据（文件行号/命令）"),
                ]
            )
            errors.extend(
                validate_evidence_path_binding(
                    evidence,
                    actual_paths,
                    JAVA_PATH_PATTERN,
                    "关键业务逻辑注释",
                    label,
                )
            )

    ddl_paths = {path for path in actual_paths if path.lower().endswith(".sql")}
    ddl_row = rows_by_item.get("SQL/DDL 公共字段与方言")
    if ddl_paths and ddl_row:
        result = table_cell(headers, ddl_row, "结论")
        if result == "不适用":
            errors.append(f"{label} 本轮存在 SQL 文件，SQL/DDL 公共字段与方言不得标记不适用")
        elif result == "通过":
            evidence = " ".join(
                [
                    table_cell(headers, ddl_row, "适用文件"),
                    table_cell(headers, ddl_row, "独立证据（文件行号/命令）"),
                ]
            )
            if not any(token in evidence for token in ["参考表", "项目现有", "统一兜底", "共享兜底"]):
                errors.append(f"{label} 的 SQL/DDL 独立证据缺少参考表或统一兜底依据")
            if "公共字段" not in evidence:
                errors.append(f"{label} 的 SQL/DDL 独立证据缺少公共字段或例外说明")
            if not any(token in evidence for token in ["MySQL", "方言", "测试 schema", "测试脚本"]):
                errors.append(f"{label} 的 SQL/DDL 独立证据缺少生产方言与测试脚本区分")
            errors.extend(
                validate_evidence_path_binding(
                    evidence,
                    actual_paths,
                    SQL_PATH_PATTERN,
                    "SQL/DDL ",
                    label,
                    require_all=True,
                )
            )
    return errors


def validate_code_review_completion(
    index_path: Path,
    rounds_dir: Path,
    actual_paths: set[str] | None = None,
    expected_implementation_round: str | None = None,
    expected_fingerprint: str | None = None,
    expected_input_fingerprint: str | None = None,
    expected_reviewer_mode: str | None = None,
    expected_self_review_reason: str | None = None,
) -> list[str]:
    """验证 Review 通过证据；推进测试验证前调用。"""
    errors = validate_code_review_artifacts(index_path, rounds_dir)
    if not index_path.exists():
        return errors or ["缺少 06-code-review.md"]

    index_text = read_text(index_path)
    if extract_line_value(index_text, "- 当前结论：") != "通过":
        errors.append("06-code-review.md 当前结论必须明确为“通过”")

    round_files = (
        sorted(
            rounds_dir.glob("*.md"),
            key=lambda path: (review_round_number(path), path.name),
        )
        if rounds_dir.exists()
        else []
    )
    if not round_files:
        errors.append("缺少 Code Review 轮次明细，不能进入测试验证")
        return errors

    latest_round = round_files[-1]
    round_text = read_text(latest_round)
    errors.extend(
        validate_review_provenance(
            round_text,
            latest_round.name,
            expected_reviewer_mode,
            expected_self_review_reason,
        )
    )
    errors.extend(
        validate_review_provenance(
            index_text,
            "06-code-review.md",
            expected_reviewer_mode,
            expected_self_review_reason,
        )
    )
    round_mode = extract_line_value(round_text, "- Review 方式：")
    index_mode = extract_line_value(index_text, "- Review 方式：")
    round_reason = extract_line_value(round_text, "- Self-review 原因：")
    index_reason = extract_line_value(index_text, "- Self-review 原因：")
    if round_mode and index_mode and round_mode != index_mode:
        errors.append("06-code-review.md 与最新 Review 轮次的 Review 方式不一致")
    if round_reason and index_reason and round_reason != index_reason:
        errors.append("06-code-review.md 与最新 Review 轮次的 Self-review 原因不一致")
    new_format = "## 3. Gate A：Spec Compliance" in round_text
    if extract_line_value(round_text, "- 结论：") != "通过":
        errors.append(f"{latest_round.name} 最新 Review 结论必须明确为“通过”")
    if extract_line_value(round_text, "- 是否可进入测试验证：") not in {"是", "允许"}:
        errors.append(f"{latest_round.name} Review 通过时必须明确允许进入测试验证")
    if not extract_line_value(round_text, "- 主要原因："):
        errors.append(f"{latest_round.name} Review 通过时必须填写主要原因")
    recorded_round = extract_line_value(round_text, "- 对应实现轮次：")
    if not re.fullmatch(r"I\d+", recorded_round):
        errors.append(f"{latest_round.name} 缺少有效对应实现轮次")
    recorded_fingerprint = extract_line_value(round_text, "- 实现差异指纹：")
    if not re.fullmatch(r"[0-9a-f]{64}", recorded_fingerprint):
        errors.append(f"{latest_round.name} 缺少有效的 64 位实现差异指纹")
    if expected_implementation_round:
        if recorded_round != expected_implementation_round:
            errors.append(
                f"{latest_round.name} 对应实现轮次与当前完成快照不一致: "
                f"{recorded_round or '空'} != {expected_implementation_round}"
            )
    if expected_fingerprint:
        if recorded_fingerprint != expected_fingerprint:
            errors.append(f"{latest_round.name} 实现差异指纹与当前完成快照不一致")
    if new_format:
        recorded_input = extract_line_value(round_text, "- Review 输入指纹：")
        if not re.fullmatch(r"[0-9a-f]{64}", recorded_input):
            errors.append(f"{latest_round.name} 缺少有效的 64 位 Review 输入指纹")
        elif expected_input_fingerprint and recorded_input != expected_input_fingerprint:
            errors.append(f"{latest_round.name} Review 输入指纹与当前权威输入不一致")

    round_id = extract_line_value(round_text, "- 轮次：")
    if not re.fullmatch(r"R\d+", round_id):
        errors.append(f"{latest_round.name} 缺少有效 Review 轮次")
    errors.extend(validate_review_index_sync(index_text, latest_round, round_id, latest_round.name))
    errors.extend(validate_review_problem_closure(round_text, latest_round.name))
    if new_format:
        expected_sources = set(
            extract_baseline_verification_ids(
                read_text(index_path.parent / "00-baseline.md")
            )
        )
        expected_sources.update(
            implementation_task_ids(index_path.parent / "03-tasks.md")
        )
        errors.extend(
            validate_review_gate_a(
                round_text,
                latest_round.name,
                expected_sources,
            )
        )
        errors.extend(validate_review_gate_b(round_text, latest_round.name))
        errors.extend(
            validate_review_diff_manifest(
                round_text,
                actual_paths,
                latest_round.name,
            )
        )
        errors.extend(
            validate_review_issue_history(
                index_text,
                round_files,
                round_text,
            )
        )
        return errors

    errors.extend(validate_review_consistency_summary(round_text, latest_round.name))
    errors.extend(validate_review_hallucination_audit(round_text, latest_round.name))

    quality_heading = "### 4.1 高频代码质量独立复核"
    quality_section = extract_section(round_text, quality_heading)
    if not quality_section:
        errors.append(f"{latest_round.name} 缺少高频代码质量独立复核")
        return errors

    errors.extend(
        validate_high_frequency_quality_table(
            quality_section,
            f"{latest_round.name} 高频代码质量独立复核",
            "独立证据（文件行号/命令）",
            {"通过", "不适用"},
        )
    )
    if actual_paths is not None:
        errors.extend(
            validate_review_diff_evidence(
                quality_section,
                actual_paths,
                f"{latest_round.name} 高频代码质量独立复核",
            )
        )
    return errors


def validate_code_review_nonpass(
    index_path: Path,
    rounds_dir: Path,
    result: str,
    actual_paths: set[str],
    expected_implementation_round: str,
    expected_fingerprint: str,
    expected_input_fingerprint: str,
    expected_reviewer_mode: str | None = None,
    expected_self_review_reason: str | None = None,
) -> list[str]:
    """校验需修改/阻塞结论也绑定真实输入、完整 Diff 和具体 CRxx。"""
    errors = validate_code_review_artifacts(index_path, rounds_dir)
    if not index_path.exists():
        return errors or ["缺少 06-code-review.md"]
    expected_conclusion = {"needs_changes": "需修改", "blocked": "阻塞"}[result]
    index_text = read_text(index_path)
    if extract_line_value(index_text, "- 当前结论：") != expected_conclusion:
        errors.append(f"06-code-review.md 当前结论必须为“{expected_conclusion}”")
    round_files = (
        sorted(
            rounds_dir.glob("review-r*.md"),
            key=lambda path: (review_round_number(path), path.name),
        )
        if rounds_dir.exists()
        else []
    )
    if not round_files:
        errors.append("缺少 Code Review 轮次明细")
        return errors
    latest = round_files[-1]
    text = read_text(latest)
    errors.extend(
        validate_review_provenance(
            text,
            latest.name,
            expected_reviewer_mode,
            expected_self_review_reason,
        )
    )
    errors.extend(
        validate_review_provenance(
            index_text,
            "06-code-review.md",
            expected_reviewer_mode,
            expected_self_review_reason,
        )
    )
    if "## 3. Gate A：Spec Compliance" not in text:
        errors.append(f"{latest.name} 旧版 Review 不支持登记新的非通过结论，请按新模板新开轮次")
        return errors
    if extract_line_value(text, "- 结论：") != expected_conclusion:
        errors.append(f"{latest.name} 结论必须为“{expected_conclusion}”")
    if extract_line_value(text, "- 主要原因：") in EMPTY_VALUES:
        errors.append(f"{latest.name} 缺少主要原因")
    if extract_line_value(text, "- 对应实现轮次：") != expected_implementation_round:
        errors.append(f"{latest.name} 对应实现轮次与当前实现不一致")
    if extract_line_value(text, "- 实现差异指纹：") != expected_fingerprint:
        errors.append(f"{latest.name} 实现差异指纹与当前实现不一致")
    if extract_line_value(text, "- Review 输入指纹：") != expected_input_fingerprint:
        errors.append(f"{latest.name} Review 输入指纹与当前权威输入不一致")
    round_id = extract_line_value(text, "- 轮次：")
    if round_id != f"R{review_round_number(latest)}":
        errors.append(f"{latest.name} 轮次与文件名不一致")
    if extract_line_value(index_text, "- 最新轮次：") != round_id:
        errors.append("06-code-review.md 最新轮次与 Review 明细不一致")
    index_headers, index_rows = extract_first_table(
        extract_section(index_text, "## 1. Review 轮次索引")
    )
    matching = [
        row for row in index_rows
        if table_cell(index_headers, row, "轮次") == round_id
    ]
    if len(matching) != 1:
        errors.append(f"06-code-review.md 必须且只能有一条 {round_id} 索引")
    else:
        row = matching[0]
        if table_cell(index_headers, row, "结论") != expected_conclusion:
            errors.append(f"06-code-review.md {round_id} 索引结论必须为{expected_conclusion}")
        if Path(table_cell(index_headers, row, "明细文档")).name != latest.name:
            errors.append(f"06-code-review.md {round_id} 明细文档不一致")

    errors.extend(validate_review_diff_manifest(text, actual_paths, latest.name))
    gate_a = extract_line_value(text, "- Gate A 结论：")
    gate_b = extract_line_value(text, "- Gate B 结论：")
    if gate_a not in {"通过", "需修改", "阻塞"}:
        errors.append(f"{latest.name} Gate A 结论无效")
    if gate_b not in {"通过", "需修改", "阻塞", "未执行（Gate A 未通过）"}:
        errors.append(f"{latest.name} Gate B 结论无效")
    if gate_a == "通过" and gate_b == "通过":
        errors.append(f"{latest.name} 两门均通过，不能登记{expected_conclusion}")

    issue_headers, issue_rows = review_issue_table(text)
    open_issues = [
        row for row in issue_rows
        if re.fullmatch(r"CR\d+", table_cell(issue_headers, row, "问题编号"))
        and table_cell(issue_headers, row, "状态") == "open"
    ]
    if not open_issues:
        errors.append(f"{latest.name} {expected_conclusion}必须登记至少一个 open CRxx")
    for row in open_issues:
        issue_id = table_cell(issue_headers, row, "问题编号")
        severity = table_cell(issue_headers, row, "级别")
        if severity not in REVIEW_SEVERITIES:
            errors.append(f"{latest.name} {issue_id} 级别不合法")
        for header in ["Gate", "文件行号/全局依据", "问题", "风险", "建议"]:
            if table_cell(issue_headers, row, header) in EMPTY_VALUES:
                errors.append(f"{latest.name} {issue_id} 缺少{header}")
    errors.extend(validate_review_issue_history(index_text, round_files, text))
    return errors


def validate_quick_review_nonpass(
    path: Path,
    result: str,
    actual_paths: set[str],
    expected_reviewer_mode: str | None = None,
    expected_self_review_reason: str | None = None,
) -> list[str]:
    if not path.exists():
        return ["缺少 quick.md"]
    text = read_text(path)
    expected = "需修改" if result == "needs_changes" else "阻塞"
    if quick_schema_version(text) >= 4:
        return validate_optional_review(
            path,
            result,
            extract_line_value(text, "- Review 对应实现轮次："),
            extract_line_value(text, "- Review 对应差异指纹："),
        )
    if quick_schema_version(text) >= 3:
        errors: list[str] = []
        disposition = extract_line_value(text, "- Review 处置：").strip()
        recorded_result = extract_line_value(text, "- Review 结论：").strip()
        gate_satisfied = extract_line_value(
            text,
            "- Review Gate 是否满足：",
        ).strip()
        if disposition not in {"light", "formal"}:
            errors.append("quick.md v3 非通过 Review 的处置必须为 light 或 formal")
        if recorded_result != expected:
            errors.append(f"quick.md v3 Review 结论必须为{expected}")
        if gate_satisfied != "否":
            errors.append("quick.md v3 非通过 Review 的 Gate 是否满足必须为“否”")
        issue = extract_line_value(
            text,
            "- Review 未关闭阻塞/必须修问题：",
        ).strip()
        if issue in EMPTY_VALUES or issue in {"无", "不涉及"}:
            errors.append(f"quick Review {expected}必须记录未关闭问题")
        if disposition == "light":
            summary = extract_line_value(
                text,
                "- Light Review 简要结论：",
            ).strip()
            if not meaningful_design_value(summary) or summary.startswith("不涉及"):
                errors.append("quick.md v3 light Review 缺少简洁复核结论")
            return errors
        section = extract_section(
            text,
            "### 5.1 Formal Review 两门复核（仅 formal）",
        )
        tables = iter_markdown_tables(section)
        if len(tables) < 2:
            return errors + ["quick formal Review 缺少两门复核表或 Diff 覆盖表"]
        coverage_headers, coverage_rows = tables[1]
        covered: set[str] = set()
        for row in coverage_rows:
            paths = extract_quality_paths(
                table_cell(coverage_headers, row, "Diff 路径")
            )
            if len(paths) == 1:
                covered.update(paths)
        missing = {
            normalize_quality_path(value) for value in actual_paths
        } - covered
        if missing:
            errors.append(
                "quick formal Review 非通过结论仍遗漏 Diff 文件: "
                + ", ".join(sorted(missing))
            )
        return errors

    gate_values = {
        extract_line_value(text, "- Review Gate A："),
        extract_line_value(text, "- Review Gate B："),
    }
    errors = validate_review_provenance(
        text,
        "quick.md",
        expected_reviewer_mode,
        expected_self_review_reason,
    )
    if expected not in gate_values and "阻塞" not in gate_values:
        errors.append(f"quick Review {expected}结论缺少对应 Gate 结论")
    issue = extract_line_value(text, "- Review 未关闭阻塞/必须修问题：")
    if issue in EMPTY_VALUES or issue in {"无", "不涉及"}:
        errors.append(f"quick Review {expected}必须记录未关闭问题")
    section = extract_section(text, "### 5.1 Quick Review 两门复核")
    tables = iter_markdown_tables(section)
    if len(tables) < 2:
        return errors + ["quick Review 缺少两门复核表或 Diff 覆盖表"]
    coverage_headers, coverage_rows = tables[1]
    covered: set[str] = set()
    for row in coverage_rows:
        paths = extract_quality_paths(table_cell(coverage_headers, row, "Diff 路径"))
        if len(paths) == 1:
            covered.update(paths)
    missing = {normalize_quality_path(value) for value in actual_paths} - covered
    if missing:
        errors.append("quick Review 非通过结论仍遗漏 Diff 文件: " + ", ".join(sorted(missing)))
    return errors


def validate_test_report_artifacts(index_path: Path, rounds_dir: Path) -> list[str]:
    errors: list[str] = []
    if index_path.exists():
        text = read_text(index_path)
        assert_contains(
            text,
            TEST_REPORT_INDEX_REQUIRED_TOKENS[:2],
            index_path.name,
            errors,
        )
        if not test_gap_ledger_section(text):
            errors.append(
                f"{index_path.name} 缺少关键内容: "
                f"{TEST_REPORT_INDEX_REQUIRED_TOKENS[2]}"
            )
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
                ["场景ID", "来源依据", "业务场景", "级别", "预期结果", "结果", "证据或原因"],
                (
                    f"{round_file.name} 测试场景清单缺少关键表头: "
                    "场景ID、来源依据、业务场景、级别、预期结果、结果、证据或原因"
                ),
                errors,
            )
    return errors


TEST_SCENARIO_RESULTS = {"通过", "失败", "阻塞", "未执行", "不适用"}
TEST_CONCLUSIONS = {"通过", "需补测", "阻塞"}
TEST_CLOSED_GAP_STATUSES = {"fixed", "accepted", "not-applicable"}
TEST_EFFECTS = {
    "read-only",
    "local-write",
    "data-write",
    "state-change",
    "message-or-job",
    "external-side-effect",
}


def test_round_number(path: Path) -> int:
    match = re.fullmatch(r"test-r(\d+)\.md", path.name)
    return int(match.group(1)) if match else -1


def validate_test_scenario_table(
    section: str,
    label: str,
    require_passed: bool,
) -> tuple[list[str], set[str]]:
    """校验测试场景是否可执行、可判断，避免用“已验证”掩盖失败。"""
    errors: list[str] = []
    headers, rows = extract_first_table(section)
    required_headers = [
        "场景ID",
        "来源依据",
        "业务场景",
        "级别",
        "前置条件",
        "操作与测试数据",
        "预期结果",
        "Effect",
        "结果",
        "证据或原因",
    ]
    if not all(header in headers for header in required_headers):
        return [f"{label} 缺少关键表头: {', '.join(required_headers)}"], set()

    scenario_rows = [
        row for row in rows
        if re.fullmatch(r"TS\d+", table_cell(headers, row, "场景ID"))
    ]
    if not scenario_rows:
        return [f"{label} 缺少已填写的测试场景"], set()

    scenario_ids: set[str] = set()
    has_critical = False
    for row in scenario_rows:
        scenario_id = table_cell(headers, row, "场景ID")
        if scenario_id in scenario_ids:
            errors.append(f"{label} 场景ID重复: {scenario_id}")
            continue
        scenario_ids.add(scenario_id)
        source = table_cell(headers, row, "来源依据")
        scene = table_cell(headers, row, "业务场景")
        level = table_cell(headers, row, "级别")
        precondition = table_cell(headers, row, "前置条件")
        action = table_cell(headers, row, "操作与测试数据")
        expected = table_cell(headers, row, "预期结果")
        effect = table_cell(headers, row, "Effect")
        result = table_cell(headers, row, "结果")
        evidence = table_cell(headers, row, "证据或原因")

        if source in EMPTY_VALUES:
            errors.append(f"{label} {scenario_id} 缺少可追溯的来源依据")
        if scene in EMPTY_VALUES:
            errors.append(f"{label} {scenario_id} 缺少具体业务场景")
        if level not in {"关键", "一般"}:
            errors.append(f"{label} {scenario_id} 级别必须为“关键”或“一般”")
        has_critical = has_critical or level == "关键"
        if precondition == "":
            errors.append(f"{label} {scenario_id} 缺少前置条件；无前置条件时填写“无”")
        if action in EMPTY_VALUES:
            errors.append(f"{label} {scenario_id} 缺少可执行的操作与测试数据")
        if expected in EMPTY_VALUES:
            errors.append(f"{label} {scenario_id} 缺少可判断的预期结果")
        if effect not in TEST_EFFECTS:
            errors.append(f"{label} {scenario_id} Effect 不合法: {effect or '空'}")
        if result not in TEST_SCENARIO_RESULTS:
            errors.append(
                f"{label} {scenario_id} 结果必须为: {', '.join(sorted(TEST_SCENARIO_RESULTS))}"
            )
        if evidence in EMPTY_VALUES:
            errors.append(f"{label} {scenario_id} 缺少执行证据或未执行原因")

        if require_passed:
            if result in {"失败", "阻塞"}:
                errors.append(f"{label} {scenario_id} 仍为{result}，测试结论不能通过")
            if result == "未执行":
                errors.append(f"{label} {scenario_id} 尚未执行，测试结论不能通过")
            if level == "关键" and result != "通过":
                errors.append(f"{label} {scenario_id} 是关键场景，必须验证通过")

    if not has_critical:
        errors.append(f"{label} 至少需要一个由验收目标推导的关键场景")
    return errors, scenario_ids


def validate_test_basis_coverage(
    round_text: str,
    scenario_ids: set[str],
    label: str,
    expected_baseline_ids: set[str] | None = None,
    expected_diff_paths: set[str] | None = None,
    require_review_source: bool = False,
) -> list[str]:
    """确保验收标准、Review 缺口和改动风险先变成测试依据，再落到场景。"""
    errors: list[str] = []
    headers, rows = extract_first_table(extract_section(round_text, "## 3. 测试依据覆盖"))
    required_headers = [
        "依据ID",
        "来源类型",
        "来源定位",
        "要证明的业务结果或风险",
        "风险",
        "必测",
        "Effect",
        "覆盖场景",
        "覆盖结论",
        "不适用/豁免事实与授权",
    ]
    if not all(header in headers for header in required_headers):
        return [f"{label} 测试依据覆盖缺少关键表头: {', '.join(required_headers)}"]

    basis_rows = [
        row for row in rows
        if re.fullmatch(r"TB\d+", table_cell(headers, row, "依据ID"))
    ]
    if not basis_rows:
        return [f"{label} 缺少已填写的测试依据覆盖记录"]

    seen: set[str] = set()
    all_sources: list[str] = []
    source_types: set[str] = set()
    scenario_headers, scenario_rows = extract_first_table(
        extract_section(round_text, "## 4. 测试场景清单")
    )
    scenario_results = {
        table_cell(scenario_headers, row, "场景ID"): table_cell(scenario_headers, row, "结果")
        for row in scenario_rows
        if re.fullmatch(r"TS\d+", table_cell(scenario_headers, row, "场景ID"))
    }
    scenario_levels = {
        table_cell(scenario_headers, row, "场景ID"): table_cell(scenario_headers, row, "级别")
        for row in scenario_rows
        if re.fullmatch(r"TS\d+", table_cell(scenario_headers, row, "场景ID"))
    }
    for row in basis_rows:
        basis_id = table_cell(headers, row, "依据ID")
        if basis_id in seen:
            errors.append(f"{label} 测试依据ID重复: {basis_id}")
            continue
        seen.add(basis_id)
        source = table_cell(headers, row, "来源定位")
        source_type = table_cell(headers, row, "来源类型")
        source_types.add(source_type)
        target = table_cell(headers, row, "要证明的业务结果或风险")
        risk = table_cell(headers, row, "风险")
        mandatory = table_cell(headers, row, "必测")
        effect = table_cell(headers, row, "Effect")
        covered = set(re.findall(r"\bTS\d+\b", table_cell(headers, row, "覆盖场景")))
        conclusion = table_cell(headers, row, "覆盖结论")
        waiver = table_cell(headers, row, "不适用/豁免事实与授权")
        all_sources.append(source)
        if source_type not in {"验收", "规则", "Review", "diff", "兼容", "NFR"}:
            errors.append(f"{label} {basis_id} 来源类型不合法: {source_type or '空'}")
        if source in EMPTY_VALUES:
            errors.append(f"{label} {basis_id} 缺少需求、Review 或 diff 来源定位")
        if target in EMPTY_VALUES:
            errors.append(f"{label} {basis_id} 缺少要证明的业务结果或风险")
        if risk not in {"高", "中", "低"}:
            errors.append(f"{label} {basis_id} 风险必须为高、中或低")
        if mandatory not in {"是", "否"}:
            errors.append(f"{label} {basis_id} 必测必须为是或否")
        if risk == "高" and mandatory != "是":
            errors.append(f"{label} {basis_id} 是高风险来源，必须标记为必测")
        if effect not in TEST_EFFECTS:
            errors.append(f"{label} {basis_id} Effect 不合法: {effect or '空'}")
        if conclusion not in {"已覆盖", "不适用"}:
            errors.append(f"{label} {basis_id} 尚未被测试场景覆盖")
        if conclusion == "不适用":
            if risk == "高":
                errors.append(f"{label} {basis_id} 是高风险来源，不能标记为不适用")
            if waiver in EMPTY_VALUES or len(waiver) < 8:
                errors.append(f"{label} {basis_id} 标记不适用时必须写明事实、授权和剩余风险")
            if mandatory == "是":
                errors.append(f"{label} {basis_id} 已标记必测，不能同时标记不适用")
            continue
        if not covered:
            errors.append(f"{label} {basis_id} 缺少覆盖场景")
        unknown = covered - scenario_ids
        if unknown:
            errors.append(f"{label} {basis_id} 引用了不存在的场景: {', '.join(sorted(unknown))}")
        if mandatory == "是" and not any(
            scenario_results.get(scenario_id) == "通过"
            for scenario_id in covered
        ):
            errors.append(f"{label} {basis_id} 是必测来源，但没有通过的覆盖场景")
        if risk == "高":
            if waiver not in {"无", "不涉及"}:
                errors.append(f"{label} {basis_id} 是高风险来源，正式门禁不能使用豁免")
            critical = {
                scenario_id
                for scenario_id in covered
                if scenario_levels.get(scenario_id) == "关键"
            }
            if not critical:
                errors.append(f"{label} {basis_id} 是高风险来源，必须映射关键场景")
            elif not any(
                scenario_results.get(scenario_id) == "通过"
                for scenario_id in critical
            ):
                errors.append(f"{label} {basis_id} 的关键场景没有通过")
    source_text = "\n".join(all_sources)
    missing_baseline = sorted(
        baseline_id
        for baseline_id in (expected_baseline_ids or set())
        if not re.search(rf"\b{re.escape(baseline_id)}\b", source_text)
    )
    if missing_baseline:
        errors.append(f"{label} 来源 Manifest 遗漏基线项: " + ", ".join(missing_baseline))
    missing_diff = sorted(
        path
        for path in (expected_diff_paths or set())
        if normalize_quality_path(path) not in source_text
    )
    if missing_diff:
        errors.append(f"{label} 来源 Manifest 遗漏真实 Diff 文件: " + ", ".join(missing_diff))
    if require_review_source and "Review" not in source_types:
        errors.append(f"{label} 来源 Manifest 遗漏 Review 验证缺口")

    for row in scenario_rows:
        scenario_id = table_cell(scenario_headers, row, "场景ID")
        if not re.fullmatch(r"TS\d+", scenario_id):
            continue
        referenced = set(re.findall(r"\bTB\d+\b", table_cell(scenario_headers, row, "来源依据")))
        if not referenced:
            errors.append(f"{label} {scenario_id} 未引用 TBxx 来源")
        unknown = referenced - seen
        if unknown:
            errors.append(f"{label} {scenario_id} 引用了不存在的来源: {', '.join(sorted(unknown))}")
    return errors


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_execution_evidence_file(
    raw_evidence: str,
    evidence_hash: str,
    feature_dir: Path | None,
    label: str,
) -> list[str]:
    """可落盘的执行证据必须位于 feature/reports 且摘要与真实文件一致。"""
    if not re.fullmatch(r"[0-9a-fA-F]{64}", evidence_hash):
        if (
            "无法保存" not in evidence_hash
            or len(evidence_hash) < 8
            or "事实原因" in evidence_hash
        ):
            return [f"{label} 缺少有效证据 SHA-256 或无法保存的事实原因"]
        if raw_evidence in EMPTY_VALUES or len(raw_evidence) < 12:
            return [f"{label} 无法保存原始证据时必须提供足以复查的脱敏摘要"]
        return []
    if feature_dir is None:
        return []

    path_match = re.search(r"`(reports/[^`]+)`", raw_evidence)
    if path_match is None:
        path_match = re.fullmatch(r"(reports/\S+)", raw_evidence.strip())
    if path_match is None:
        return [f"{label} 有 SHA-256 时原始证据必须指向 `reports/...` 文件"]

    relative = Path(path_match.group(1))
    candidate = (feature_dir / relative).resolve()
    reports_dir = (feature_dir / "reports").resolve()
    try:
        candidate.relative_to(reports_dir)
    except ValueError:
        return [f"{label} 原始证据路径越出 feature/reports: {relative.as_posix()}"]
    if not candidate.is_file():
        return [f"{label} 原始证据文件不存在: {relative.as_posix()}"]
    actual_hash = sha256_file(candidate)
    if actual_hash.lower() != evidence_hash.lower():
        return [f"{label} 证据 SHA-256 与真实文件不一致: {relative.as_posix()}"]
    return []


def validate_test_execution_records(
    round_text: str,
    scenario_ids: set[str],
    label: str,
    feature_dir: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    headers, rows = extract_first_table(extract_section(round_text, "## 5. 执行记录"))
    required_headers = [
        "执行ID",
        "场景ID",
        "时间",
        "cwd / 环境 / 版本",
        "命令/接口/观察点",
        "退出码/协议结果",
        "实际结果摘要",
        "Effect",
        "原始证据",
        "证据 SHA-256",
        "结论",
    ]
    if not all(header in headers for header in required_headers):
        return [f"{label} 执行记录缺少关键表头: {', '.join(required_headers)}"]

    execution_rows = [
        row for row in rows
        if re.fullmatch(r"E\d+", table_cell(headers, row, "执行ID"))
    ]
    if not execution_rows:
        return [f"{label} 缺少已填写的执行记录"]

    executed_scenarios: set[str] = set()
    execution_ids: set[str] = set()
    latest_conclusion_by_scenario: dict[str, str] = {}
    for row in execution_rows:
        execution_id = table_cell(headers, row, "执行ID")
        if execution_id in execution_ids:
            errors.append(f"{label} 执行ID重复: {execution_id}")
        execution_ids.add(execution_id)
        scenario_id = table_cell(headers, row, "场景ID")
        executed_scenarios.add(scenario_id)
        latest_conclusion_by_scenario[scenario_id] = table_cell(headers, row, "结论")
        if scenario_id not in scenario_ids:
            errors.append(f"{label} {execution_id} 引用了不存在的场景: {scenario_id or '空'}")
        for header in [
            "时间",
            "cwd / 环境 / 版本",
            "命令/接口/观察点",
            "退出码/协议结果",
            "实际结果摘要",
            "原始证据",
        ]:
            if table_cell(headers, row, header) in EMPTY_VALUES:
                errors.append(f"{label} {execution_id} 缺少{header}")
        execution_method = table_cell(
            headers,
            row,
            "命令/接口/观察点",
        ).strip().strip("`").strip()
        if not execution_method.startswith(("command:", "api:", "observation:")):
            errors.append(
                f"{label} {execution_id} 命令/接口/观察点必须以 "
                "command:、api: 或 observation: 开头"
            )
        effect = table_cell(headers, row, "Effect")
        if effect not in TEST_EFFECTS:
            errors.append(f"{label} {execution_id} Effect 不合法: {effect or '空'}")
        evidence_hash = table_cell(headers, row, "证据 SHA-256")
        original_evidence = table_cell(headers, row, "原始证据")
        if original_evidence.startswith("脱敏输出") or original_evidence.endswith("的路径"):
            errors.append(f"{label} {execution_id} 原始证据仍是模板占位内容")
        errors.extend(
            validate_execution_evidence_file(
                original_evidence,
                evidence_hash,
                feature_dir,
                f"{label} {execution_id}",
            )
        )
        conclusion = table_cell(headers, row, "结论")
        if conclusion not in {"PASS", "FAIL", "BLOCKED"}:
            errors.append(f"{label} {execution_id} 执行结论不合法")

    scenario_headers, scenario_rows = extract_first_table(
        extract_section(round_text, "## 4. 测试场景清单")
    )
    passed_ids = {
        table_cell(scenario_headers, row, "场景ID")
        for row in scenario_rows
        if table_cell(scenario_headers, row, "结果") == "通过"
    }
    missing_execution = passed_ids - executed_scenarios
    if missing_execution:
        errors.append(
            f"{label} 标记通过的场景缺少执行记录: {', '.join(sorted(missing_execution))}"
        )
    for scenario_id in passed_ids:
        if latest_conclusion_by_scenario.get(scenario_id) != "PASS":
            errors.append(f"{label} {scenario_id} 最新执行记录不是 PASS")
    for row in scenario_rows:
        scenario_id = table_cell(scenario_headers, row, "场景ID")
        if scenario_id not in passed_ids:
            continue
        evidence_ids = set(re.findall(r"\bE\d+\b", table_cell(scenario_headers, row, "证据或原因")))
        if not evidence_ids:
            errors.append(f"{label} {scenario_id} 标记通过但未在场景行引用 Exx")
        unknown = evidence_ids - execution_ids
        if unknown:
            errors.append(f"{label} {scenario_id} 引用了不存在的执行记录: {', '.join(sorted(unknown))}")
    return errors


def validate_test_gap_closure(index_text: str, round_text: str, label: str) -> list[str]:
    errors: list[str] = []
    checks = [
        (test_gap_ledger_section(index_text), "缺口编号", "当前状态", "07-test-report.md"),
        (
            extract_section(round_text, "## 7. 缺口和阻塞"),
            "缺口编号",
            "当前状态",
            label,
        ),
    ]
    for section, id_header, status_header, source_label in checks:
        headers, rows = extract_first_table(section)
        for row in rows:
            gap_id = table_cell(headers, row, id_header)
            if not re.fullmatch(r"TV\d+", gap_id):
                continue
            status = table_cell(headers, row, status_header)
            if status not in TEST_CLOSED_GAP_STATUSES:
                errors.append(f"{source_label} {gap_id} 仍未关闭")
    return errors


def test_gap_rows(text: str) -> tuple[list[str], list[list[str]]]:
    return extract_first_table(extract_section(text, "## 7. 缺口和阻塞"))


def test_gap_ledger_section(text: str) -> str:
    for heading in ["## 3. 缺口账本（含历史）", "## 3. 未关闭缺口"]:
        section = extract_section(text, heading)
        if section:
            return section
    return ""


def validate_test_gap_history(
    index_text: str,
    round_files: list[Path],
) -> list[str]:
    """确保 TVxx、测试轮次和索引账本跨轮次 append-only。"""
    errors: list[str] = []
    numbers = [test_round_number(path) for path in round_files]
    if numbers and numbers != list(range(1, max(numbers) + 1)):
        errors.append("测试轮次文件不连续，可能有历史轮次被删除")

    historical: dict[str, tuple[str, str]] = {}
    previous_open: set[str] = set()
    for path in round_files[:-1]:
        headers, rows = test_gap_rows(read_text(path))
        for row in rows:
            gap_id = table_cell(headers, row, "缺口编号")
            if not re.fullmatch(r"TV\d+", gap_id):
                continue
            signature = (
                table_cell(headers, row, "首次轮次"),
                table_cell(headers, row, "问题"),
            )
            previous = historical.get(gap_id)
            if previous and previous != signature:
                errors.append(f"{gap_id} 在不同测试轮次被复用为不同缺口")
            historical[gap_id] = signature
            if table_cell(headers, row, "当前状态") == "open":
                previous_open.add(gap_id)
            else:
                previous_open.discard(gap_id)

    latest_text = read_text(round_files[-1]) if round_files else ""
    latest_headers, latest_rows = test_gap_rows(latest_text)
    latest_ids: set[str] = set()
    for row in latest_rows:
        gap_id = table_cell(latest_headers, row, "缺口编号")
        if not re.fullmatch(r"TV\d+", gap_id):
            continue
        latest_ids.add(gap_id)
        signature = (
            table_cell(latest_headers, row, "首次轮次"),
            table_cell(latest_headers, row, "问题"),
        )
        previous = historical.get(gap_id)
        if previous and previous != signature:
            errors.append(f"{gap_id} 在最新轮次被改号或改写为其他缺口")
        historical[gap_id] = signature
        status = table_cell(latest_headers, row, "当前状态")
        evidence = table_cell(latest_headers, row, "归因/关闭证据")
        if status in TEST_CLOSED_GAP_STATUSES and evidence in EMPTY_VALUES:
            errors.append(f"最新测试轮次 {gap_id} 已关闭但缺少归因/关闭证据")

    missing_inherited = sorted(previous_open - latest_ids)
    if missing_inherited:
        errors.append("最新测试轮次未继承上轮未关闭 TVxx: " + ", ".join(missing_inherited))
    if historical:
        gap_numbers = sorted(int(gap_id[2:]) for gap_id in historical)
        if gap_numbers != list(range(1, max(gap_numbers) + 1)):
            errors.append("TVxx 编号不连续，可能有历史缺口被删除或跳号")

    index_headers, index_rows = extract_first_table(test_gap_ledger_section(index_text))
    ledger: dict[str, list[str]] = {}
    for row in index_rows:
        gap_id = table_cell(index_headers, row, "缺口编号")
        if not re.fullmatch(r"TV\d+", gap_id):
            continue
        if gap_id in ledger:
            errors.append(f"07-test-report.md TVxx 账本编号重复: {gap_id}")
        ledger[gap_id] = row
    missing_ledger = sorted(set(historical) - set(ledger))
    if missing_ledger:
        errors.append("07-test-report.md TVxx 账本遗漏历史缺口: " + ", ".join(missing_ledger))
    for gap_id, row in ledger.items():
        status = table_cell(index_headers, row, "当前状态")
        evidence = table_cell(index_headers, row, "关闭轮次/证据")
        if status not in {"open", *TEST_CLOSED_GAP_STATUSES}:
            errors.append(f"07-test-report.md {gap_id} 状态不合法: {status or '空'}")
        if status in TEST_CLOSED_GAP_STATUSES and evidence in EMPTY_VALUES:
            errors.append(f"07-test-report.md {gap_id} 已关闭但缺少关闭轮次/证据")
    return errors


def validate_test_data_recovery(round_text: str, label: str) -> list[str]:
    errors: list[str] = []
    section = extract_section(round_text, "## 6. 数据影响与恢复")
    planned_effect = extract_line_value(section, "- 计划 Effect：")
    actual_effect = extract_line_value(section, "- 实际 Effect：")
    authorization = extract_line_value(section, "- Effect 授权：")
    changed = extract_line_value(section, "- 本轮是否产生或修改数据：")
    impact = extract_line_value(section, "- 影响范围：")
    recovery = extract_line_value(section, "- 清理、恢复或最终状态回查：")
    residual = extract_line_value(section, "- 遗留数据及影响：")
    recovery_evidence = extract_line_value(section, "- 恢复/回查证据及 SHA-256：")
    if planned_effect not in TEST_EFFECTS:
        errors.append(f"{label} 缺少合法的计划 Effect")
    if actual_effect not in TEST_EFFECTS:
        errors.append(f"{label} 缺少合法的实际 Effect")
    side_effecting = actual_effect not in {"", "read-only", "local-write"}
    if side_effecting and (
        authorization in EMPTY_VALUES
        or authorization.startswith("不需要")
    ):
        errors.append(f"{label} 存在真实副作用但缺少 Effect 授权")
    if changed not in {"是", "否"}:
        errors.append(f"{label} 必须明确本轮是否产生或修改数据")
    if impact == "":
        errors.append(f"{label} 缺少测试数据影响范围；不涉及时填写“无”")
    if recovery == "":
        errors.append(f"{label} 缺少清理、恢复或最终状态回查")
    if residual == "":
        errors.append(f"{label} 缺少遗留数据及影响说明")
    if changed == "是" and recovery in EMPTY_VALUES:
        errors.append(f"{label} 产生或修改数据后必须提供清理、恢复或回查证据")
    if side_effecting and (
        recovery_evidence in EMPTY_VALUES
        or not re.search(r"[0-9a-fA-F]{64}", recovery_evidence)
    ):
        errors.append(f"{label} 真实副作用缺少恢复/回查证据及 SHA-256")
    if residual not in {"无", "不涉及"}:
        errors.append(f"{label} 仍有遗留测试数据，测试结论不能通过")
    return errors


def validate_test_report_completion(
    index_path: Path,
    rounds_dir: Path,
    expected_implementation_round: str | None = None,
    expected_fingerprint: str | None = None,
    expected_review_round: str | None = None,
    actual_paths: set[str] | None = None,
) -> list[str]:
    """语义校验最新测试轮次；仅结构完整不能登记“通过”。"""
    errors = validate_test_report_artifacts(index_path, rounds_dir)
    if not index_path.exists():
        return errors or ["缺少 07-test-report.md"]

    index_text = read_text(index_path)
    if extract_line_value(index_text, "- 当前结论：") != "通过":
        errors.append("07-test-report.md 当前结论必须明确为“通过”")
    if extract_line_value(index_text, "- 当前模式：") != "formal-gate":
        errors.append("07-test-report.md 正式通过只能来自 formal-gate")
    if extract_line_value(index_text, "- 测试阶段是否完成：") not in {"是", "已完成"}:
        errors.append("07-test-report.md 必须明确测试阶段已完成")
    return_prefix = (
        "- 需要回到实现的问题："
        if "- 需要回到实现的问题：" in index_text
        else "- 需要回到实现或评审的问题："
    )
    if extract_line_value(index_text, return_prefix) not in {"无", "不涉及"}:
        errors.append("07-test-report.md 通过时不能保留需回到实现的问题")

    round_files = (
        sorted(rounds_dir.glob("test-r*.md"), key=lambda path: (test_round_number(path), path.name))
        if rounds_dir.exists()
        else []
    )
    if not round_files:
        errors.append("缺少测试轮次明细，不能登记测试通过")
        return errors

    latest_round = round_files[-1]
    round_text = read_text(latest_round)
    round_id = extract_line_value(round_text, "- 轮次：")
    expected_number = test_round_number(latest_round)
    if expected_number < 0:
        errors.append(f"{latest_round.name} 文件名必须使用 test-rNN.md")
    elif round_id != f"T{expected_number}":
        errors.append(f"{latest_round.name} 轮次与文件名不一致: {round_id or '空'}")
    if extract_line_value(index_text, "- 最新轮次：") != round_id:
        errors.append("07-test-report.md 最新轮次与测试明细不一致")
    if extract_line_value(round_text, "- 结论：") != "通过":
        errors.append(f"{latest_round.name} 最新测试结论必须明确为“通过”")
    if extract_line_value(round_text, "- 测试模式：") != "formal-gate":
        errors.append(f"{latest_round.name} 正式通过必须使用 formal-gate")
    if extract_line_value(round_text, "- 测试阶段是否完成：") not in {"是", "已完成"}:
        errors.append(f"{latest_round.name} 必须明确测试阶段已完成")
    if extract_line_value(round_text, "- 主要原因：") in EMPTY_VALUES:
        errors.append(f"{latest_round.name} 测试通过时必须填写主要原因")

    implementation_round = extract_line_value(round_text, "- 对应实现轮次：")
    fingerprint = extract_line_value(round_text, "- 实现差异指纹：")
    review_round = extract_line_value(round_text, "- 对应 Review 轮次：")
    if not re.fullmatch(r"I\d+", implementation_round):
        errors.append(f"{latest_round.name} 缺少有效对应实现轮次")
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        errors.append(f"{latest_round.name} 缺少有效的 64 位实现差异指纹")
    if expected_review_round and not re.fullmatch(r"R\d+|quick|skipped", review_round):
        errors.append(f"{latest_round.name} 缺少有效对应 Review 轮次")
    if expected_implementation_round and implementation_round != expected_implementation_round:
        errors.append(f"{latest_round.name} 对应实现轮次与当前实现不一致")
    if expected_fingerprint and fingerprint != expected_fingerprint:
        errors.append(f"{latest_round.name} 实现差异指纹与当前实现不一致")
    if expected_review_round and review_round != expected_review_round:
        errors.append(f"{latest_round.name} 对应 Review 轮次与最新通过轮次不一致")

    index_headers, index_rows = extract_first_table(
        extract_section(index_text, "## 1. 测试轮次索引")
    )
    matching = [row for row in index_rows if table_cell(index_headers, row, "轮次") == round_id]
    if len(matching) != 1:
        errors.append(f"07-test-report.md 必须且只能有一条 {round_id or '最新轮次'} 索引")
    else:
        row = matching[0]
        if table_cell(index_headers, row, "模式") != "formal-gate":
            errors.append(f"07-test-report.md {round_id} 索引模式必须为 formal-gate")
        if table_cell(index_headers, row, "结论") != "通过":
            errors.append(f"07-test-report.md {round_id} 索引结论必须为通过")
        if Path(table_cell(index_headers, row, "明细文档")).name != latest_round.name:
            errors.append(f"07-test-report.md {round_id} 明细文档与最新轮次文件不一致")

    scenario_errors, scenario_ids = validate_test_scenario_table(
        extract_section(round_text, "## 4. 测试场景清单"),
        latest_round.name,
        require_passed=True,
    )
    errors.extend(scenario_errors)
    baseline_path = index_path.parent / "00-baseline.md"
    expected_baseline_ids = set(
        extract_baseline_verification_ids(read_text(baseline_path))
    )
    review_gap = ""
    review_rounds_dir = index_path.parent / "review-rounds"
    review_rounds = (
        sorted(
            review_rounds_dir.glob("review-r*.md"),
            key=lambda path: (review_round_number(path), path.name),
        )
        if review_rounds_dir.exists()
        else []
    )
    if review_rounds:
        review_gap = extract_line_value(
            read_text(review_rounds[-1]),
            "- 未覆盖验证：",
        )
    errors.extend(
        validate_test_basis_coverage(
            round_text,
            scenario_ids,
            latest_round.name,
            expected_baseline_ids=expected_baseline_ids,
            expected_diff_paths=actual_paths or set(),
            require_review_source=review_gap not in {"", "无", "不涉及"},
        )
    )
    errors.extend(
        validate_test_execution_records(
            round_text,
            scenario_ids,
            latest_round.name,
            index_path.parent,
        )
    )
    errors.extend(validate_test_data_recovery(round_text, latest_round.name))
    errors.extend(validate_test_gap_closure(index_text, round_text, latest_round.name))
    errors.extend(validate_test_gap_history(index_text, round_files))

    integrity = extract_section(round_text, "## 8. 工件清单")
    for prefix in [
        "- 本轮证据文件清单及 SHA-256：",
        "- `reports/api-tests/` 关联文件：",
    ]:
        if extract_line_value(integrity, prefix) in EMPTY_VALUES:
            errors.append(f"{latest_round.name} 工件清单缺少: {prefix}")
    return errors


def validate_test_report_nonpass(
    index_path: Path,
    rounds_dir: Path,
    result: str,
    expected_implementation_round: str,
    expected_fingerprint: str,
    expected_review_round: str | None,
) -> list[str]:
    """校验需补测/阻塞也有真实轮次、来源、场景和可复现原因。"""
    errors = validate_test_report_artifacts(index_path, rounds_dir)
    if not index_path.exists():
        return errors or ["缺少 07-test-report.md"]
    expected_conclusion = {"needs_more": "需补测", "blocked": "阻塞"}[result]
    index_text = read_text(index_path)
    if extract_line_value(index_text, "- 当前模式：") != "formal-gate":
        errors.append("07-test-report.md 非通过结论仍必须来自 formal-gate")
    if extract_line_value(index_text, "- 当前结论：") != expected_conclusion:
        errors.append(f"07-test-report.md 当前结论必须为“{expected_conclusion}”")

    round_files = (
        sorted(rounds_dir.glob("test-r*.md"), key=lambda path: (test_round_number(path), path.name))
        if rounds_dir.exists()
        else []
    )
    if not round_files:
        errors.append("缺少测试轮次明细，不能登记非通过结论")
        return errors
    latest = round_files[-1]
    text = read_text(latest)
    if extract_line_value(text, "- 测试模式：") != "formal-gate":
        errors.append(f"{latest.name} 必须使用 formal-gate")
    if extract_line_value(text, "- 结论：") != expected_conclusion:
        errors.append(f"{latest.name} 结论必须为“{expected_conclusion}”")
    if extract_line_value(text, "- 主要原因：") in EMPTY_VALUES:
        errors.append(f"{latest.name} 缺少主要原因")
    if extract_line_value(text, "- 复验条件：") in EMPTY_VALUES:
        errors.append(f"{latest.name} 缺少复验条件")
    if extract_line_value(text, "- 对应实现轮次：") != expected_implementation_round:
        errors.append(f"{latest.name} 对应实现轮次与当前实现不一致")
    if extract_line_value(text, "- 实现差异指纹：") != expected_fingerprint:
        errors.append(f"{latest.name} 实现差异指纹与当前实现不一致")
    if expected_review_round and extract_line_value(text, "- 对应 Review 轮次：") != expected_review_round:
        errors.append(f"{latest.name} 对应 Review 轮次不一致")
    round_id = extract_line_value(text, "- 轮次：")
    if round_id != f"T{test_round_number(latest)}":
        errors.append(f"{latest.name} 轮次与文件名不一致")
    if extract_line_value(index_text, "- 最新轮次：") != round_id:
        errors.append("07-test-report.md 最新轮次与测试明细不一致")
    index_headers, index_rows = extract_first_table(
        extract_section(index_text, "## 1. 测试轮次索引")
    )
    matching = [
        row for row in index_rows
        if table_cell(index_headers, row, "轮次") == round_id
    ]
    if len(matching) != 1:
        errors.append(f"07-test-report.md 必须且只能有一条 {round_id} 索引")
    else:
        row = matching[0]
        if table_cell(index_headers, row, "模式") != "formal-gate":
            errors.append(f"07-test-report.md {round_id} 索引模式必须为 formal-gate")
        if table_cell(index_headers, row, "结论") != expected_conclusion:
            errors.append(f"07-test-report.md {round_id} 索引结论必须为{expected_conclusion}")
        if Path(table_cell(index_headers, row, "明细文档")).name != latest.name:
            errors.append(f"07-test-report.md {round_id} 明细文档不一致")

    scenario_errors, _ = validate_test_scenario_table(
        extract_section(text, "## 4. 测试场景清单"),
        latest.name,
        require_passed=False,
    )
    errors.extend(scenario_errors)
    execution_headers, execution_rows = extract_first_table(
        extract_section(text, "## 5. 执行记录")
    )
    execution_ids: set[str] = set()
    for row in execution_rows:
        execution_id = table_cell(execution_headers, row, "执行ID")
        if not re.fullmatch(r"E\d+", execution_id):
            continue
        execution_ids.add(execution_id)
        for header in [
            "场景ID",
            "时间",
            "cwd / 环境 / 版本",
            "命令/接口/观察点",
            "退出码/协议结果",
            "实际结果摘要",
            "原始证据",
        ]:
            if table_cell(execution_headers, row, header) in EMPTY_VALUES:
                errors.append(f"{latest.name} {execution_id} 缺少{header}")
        execution_method = table_cell(
            execution_headers,
            row,
            "命令/接口/观察点",
        ).strip().strip("`").strip()
        if not execution_method.startswith(("command:", "api:", "observation:")):
            errors.append(
                f"{latest.name} {execution_id} 命令/接口/观察点必须以 "
                "command:、api: 或 observation: 开头"
            )
        if table_cell(execution_headers, row, "结论") not in {"PASS", "FAIL", "BLOCKED"}:
            errors.append(f"{latest.name} {execution_id} 结论不合法")
        evidence_hash = table_cell(execution_headers, row, "证据 SHA-256")
        original_evidence = table_cell(execution_headers, row, "原始证据")
        if original_evidence.startswith("脱敏输出") or original_evidence.endswith("的路径"):
            errors.append(f"{latest.name} {execution_id} 原始证据仍是模板占位内容")
        errors.extend(
            validate_execution_evidence_file(
                original_evidence,
                evidence_hash,
                index_path.parent,
                f"{latest.name} {execution_id}",
            )
        )
    scenario_headers, scenario_rows = extract_first_table(
        extract_section(text, "## 4. 测试场景清单")
    )
    for row in scenario_rows:
        if table_cell(scenario_headers, row, "结果") != "失败":
            continue
        scenario_id = table_cell(scenario_headers, row, "场景ID")
        evidence_ids = set(
            re.findall(r"\bE\d+\b", table_cell(scenario_headers, row, "证据或原因"))
        )
        if not evidence_ids:
            errors.append(f"{latest.name} {scenario_id} 失败但未引用 Exx 原始证据")
        elif evidence_ids - execution_ids:
            errors.append(f"{latest.name} {scenario_id} 引用了不存在的 Exx")
    basis_headers, basis_rows = extract_first_table(extract_section(text, "## 3. 测试依据覆盖"))
    substantive_basis = [
        row for row in basis_rows
        if re.fullmatch(r"TB\d+", table_cell(basis_headers, row, "依据ID"))
    ]
    if not substantive_basis:
        errors.append(f"{latest.name} 缺少测试来源 Manifest")
    for row in substantive_basis:
        basis_id = table_cell(basis_headers, row, "依据ID")
        for header in ["来源类型", "来源定位", "要证明的业务结果或风险"]:
            if table_cell(basis_headers, row, header) in EMPTY_VALUES:
                errors.append(f"{latest.name} {basis_id} 缺少{header}")
        if table_cell(basis_headers, row, "风险") not in {"高", "中", "低"}:
            errors.append(f"{latest.name} {basis_id} 风险不合法")
        if table_cell(basis_headers, row, "Effect") not in TEST_EFFECTS:
            errors.append(f"{latest.name} {basis_id} Effect 不合法")

    gap_headers, gap_rows = test_gap_rows(text)
    open_gaps = [
        row for row in gap_rows
        if re.fullmatch(r"TV\d+", table_cell(gap_headers, row, "缺口编号"))
        and table_cell(gap_headers, row, "当前状态") == "open"
    ]
    if not open_gaps:
        errors.append(f"{latest.name} {expected_conclusion}必须登记至少一个 open TVxx")
    for row in open_gaps:
        gap_id = table_cell(gap_headers, row, "缺口编号")
        for header in ["问题", "主要归因", "归因/关闭证据", "返回阶段与复验条件"]:
            if table_cell(gap_headers, row, header) in EMPTY_VALUES:
                errors.append(f"{latest.name} {gap_id} 缺少{header}")
    errors.extend(validate_test_gap_history(index_text, round_files))
    return errors


def validate_quick_test_evidence(
    path: Path,
    require_passed: bool = True,
    actual_paths: set[str] | None = None,
) -> list[str]:
    """校验 Quick 独立测试场景；未触发测试时不调用。"""
    if not path.exists():
        return ["缺少 quick.md"]
    text = read_text(path)
    errors, _ = validate_test_scenario_table(
        extract_section(text, "### 5.2 Quick 测试场景"),
        "quick.md",
        require_passed=require_passed,
    )
    section = extract_section(text, "### 5.2 Quick 测试场景")
    headers, rows = extract_first_table(section)
    source_text = "\n".join(table_cell(headers, row, "来源依据") for row in rows)
    if not any(token in source_text for token in ["边界", "验收", "目标", "禁止项"]):
        errors.append("quick.md 测试来源未覆盖已确认边界或验收目标")
    if quick_schema_version(text) < 4 and "Review" not in source_text:
        errors.append("quick.md 测试来源未覆盖 Review 结论或验证缺口")
    missing_diff = [
        value
        for value in sorted(actual_paths or set())
        if normalize_quality_path(value) not in source_text
    ]
    if missing_diff:
        errors.append("quick.md 测试来源未覆盖真实 Diff 文件: " + ", ".join(missing_diff))
    if require_passed:
        for row in rows:
            scenario_id = table_cell(headers, row, "场景ID")
            if not re.fullmatch(r"TS\d+", scenario_id):
                continue
            if table_cell(headers, row, "结果") != "通过":
                continue
            evidence = table_cell(headers, row, "证据或原因")
            if not re.search(r"[0-9a-fA-F]{64}", evidence):
                errors.append(f"quick.md {scenario_id} 缺少原始证据 SHA-256")
            if not any(
                token in evidence
                for token in ["exit=", "HTTP", "响应", "日志", "SQL", "报告", "report"]
            ):
                errors.append(f"quick.md {scenario_id} 缺少退出码、协议结果或业务回查摘要")
    if not require_passed:
        has_nonpass = any(
            table_cell(headers, row, "结果") in {"失败", "阻塞", "未执行"}
            and table_cell(headers, row, "证据或原因") not in EMPTY_VALUES
            for row in rows
        )
        if not has_nonpass:
            errors.append("quick.md 非通过测试结论缺少失败、阻塞或未执行场景及原因")
    return errors


def feature_review_runtime_state(feature_dir: Path) -> tuple[dict, list[str]]:
    """只读提取 Review disposition；旧状态缺字段时安全解释为 formal。"""
    state_path = feature_dir / "implementation-state.json"
    if not state_path.exists():
        return {}, []
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {}, [f"implementation-state.json 无法读取: {error}"]
    review = state.get("review")
    if not isinstance(review, dict) or not review:
        return {}, []
    disposition = str(review.get("disposition", "")).strip()
    if disposition not in {"light", "formal", "skipped"}:
        disposition = "formal"
    result = str(review.get("result", "")).strip()
    return {
        "disposition": disposition,
        "result": result,
        "gate_satisfied": (
            result == "passed" and disposition in {"light", "formal"}
        )
        or (result == "skipped" and disposition == "skipped"),
        "passed": result == "passed" and disposition in {"light", "formal"},
        "implementation_round": str(
            review.get("implementation_round", state.get("round", ""))
        ),
        "fingerprint": str(review.get("fingerprint", "")),
    }, []


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
    legacy_blocking_issues = feature_dir / "01-blocking-issues.md"
    research = feature_dir / "01-research.md"
    design = feature_dir / "02-design.md"
    tasks = feature_dir / "03-tasks.md"
    sql_draft = feature_dir / "sql-draft.sql"
    schema = feature_dir / "04-schema.sql"
    implementation_log = feature_dir / "05-implementation-log.md"
    code_review_index = feature_dir / "06-code-review.md"
    test_report_index = feature_dir / "07-test-report.md"
    test_report_rounds = feature_dir / "test-rounds"
    interface_details = feature_dir / "interface-details"
    upgraded_from_quick = (feature_dir / "quick.md").exists()
    review_flags = meta.get("review_flags", {})
    gates = meta.get("gates", {})
    schema_version = int(meta.get("workflow_schema_version", 1))
    baseline_text = read_text(baseline)
    clarification_required = schema_version >= 3 or bool(gates.get("clarification_required", False))
    if schema_version >= 3 and gates.get("clarification_required") is not True:
        errors.append("meta.json 新版工作流必须开启 gates.clarification_required")
    baseline_schema_version = document_schema_version(baseline_text)
    if schema_version >= 3 and baseline_schema_version != schema_version:
        errors.append(
            f"00-baseline.md 为 schema v{baseline_schema_version}，但 meta.json.workflow_schema_version={schema_version}，两者必须一致"
        )
    elif baseline_schema_version >= 3 and schema_version != baseline_schema_version:
        errors.append(
            f"00-baseline.md 为 schema v{baseline_schema_version}，但 meta.json.workflow_schema_version={schema_version}，两者必须一致"
        )
    if schema_version >= 5:
        mode_selection = meta.get("mode_selection", {})
        expected_mode_selection = {
            "recommended_mode": extract_line_value(
                baseline_text,
                "- 推荐模式：",
            ).strip(),
            "recommendation_reason": extract_line_value(
                baseline_text,
                "- 推荐依据：",
            ).strip(),
            "selected_mode": extract_line_value(
                baseline_text,
                "- 最终模式：",
            ).strip(),
            "selection_source": extract_line_value(
                baseline_text,
                "- 模式选择来源：",
            ).strip(),
        }
        for key, expected in expected_mode_selection.items():
            if str(mode_selection.get(key, "")).strip() != expected:
                errors.append(
                    f"meta.json.mode_selection.{key} 与 00-baseline.md 不一致"
                )

    assert_stage_doc_naming(feature_dir, errors)

    if phase == "需求受理":
        assert_not_exists(research, "01-research.md", errors)
        assert_not_exists(design, "02-design.md", errors)
        assert_not_exists(tasks, "03-tasks.md", errors)
        assert_not_exists(sql_draft, "sql-draft.sql", errors)
        if not upgraded_from_quick:
            assert_not_exists(schema, "04-schema.sql", errors)
            assert_not_exists(interface_details, "interface-details/", errors)

    if phase == "需求对齐":
        assert_not_exists(design, "02-design.md", errors)
        assert_not_exists(tasks, "03-tasks.md", errors)
        if not upgraded_from_quick:
            assert_not_exists(schema, "04-schema.sql", errors)
            assert_not_exists(interface_details, "interface-details/", errors)

    if phase == "技术方案":
        assert_not_exists(tasks, "03-tasks.md", errors)

    if schema_version >= 5 and schema.exists():
        errors.append(
            "新版需求使用 sql-draft.sql 承载已确认 SQL；04-schema.sql 仅供历史需求兼容"
        )

    baseline_errors = validate_baseline_doc(baseline, clarification_gate_required=clarification_required)
    errors.extend(baseline_errors)
    if clarification_required:
        baseline_text = read_text(baseline)
        document_ready = (
            extract_line_value(baseline_text, "- 基线状态：") == "已确认"
            and extract_line_value(baseline_text, "- 最终反向确认：").startswith("已确认")
            and not baseline_errors
        )
        clarification = meta.get("clarification", {})
        confirmed_fingerprint = str(clarification.get("confirmed_baseline_sha256", "")).strip()
        current_fingerprint = baseline_business_fingerprint(baseline_text) if baseline_text else ""
        fingerprint_matches = bool(confirmed_fingerprint) and current_fingerprint == confirmed_fingerprint
        gate_confirmed = bool(gates.get("clarification_confirmed", False))
        if document_ready and not gate_confirmed:
            errors.append("00-baseline.md 内容已收口但尚未执行 confirm-baseline 锁定用户确认")
        if gate_confirmed and not confirmed_fingerprint:
            errors.append("meta.json 缺少已确认 baseline 业务指纹")
        if gate_confirmed and confirmed_fingerprint and not fingerprint_matches:
            errors.append("00-baseline.md 在最终确认后发生变化，必须重开澄清并重新确认")
        if gate_confirmed and not document_ready:
            errors.append("meta.json.gates.clarification_confirmed 与 00-baseline.md 不一致")
    research_text = read_text(research) if research.exists() else ""
    research_claim_ids = extract_claim_ids_from_research(research_text) if research_text else set()
    eligible_research_claim_ids = extract_design_eligible_claim_ids_from_research(research_text) if research_text else set()
    transferred_design_question_ids = (
        extract_transferred_design_question_ids_from_research(research_text) if research_text else set()
    )
    design_text = read_text(design) if design.exists() else ""
    design_ids = extract_decision_ledger_ids(
        extract_section(design_text, "## 十三、设计决策记录"), []
    ) if design_text else set()
    schema_design_ids = extract_design_ids_from_design(design_text) if design_text else set()

    if reached("需求对齐"):
        if legacy_blocking_issues.exists():
            errors.append(
                "发现旧版 01-blocking-issues.md；请将仍有效的问题合并到 01-research.md 唯一疑问账本后删除旧文件"
            )
        errors.extend(validate_research_doc(research, repo_root, baseline_text))
        if schema_version >= 5 and research_schema_version(research_text) != 3:
            errors.append("新版需求的 01-research.md 必须使用 Research v3")
        if schema_version >= 5 and (
            bool(gates.get("sql_confirmed")) or reached("技术方案")
        ):
            errors.extend(
                validate_sql_gate_binding(
                    feature_dir,
                    meta,
                    research_text,
                    research_claim_ids,
                )
            )

    if reached("技术方案"):
        if schema_version >= 5 and design_schema_version(design_text) != 6:
            errors.append("新版需求的 02-design.md 必须使用 Design v6")
        schema_confirmed = bool(gates.get("schema_confirmed", False))
        waiting_for_schema_confirmation = (
            schema_version < 5
            and phase == "技术方案"
            and design_schema_version(design_text) >= 2
            and extract_line_value(design_text, "- 设计状态：") == "SQL待确认"
            and schema.exists()
            and not schema_confirmed
        )
        if waiting_for_schema_confirmation:
            errors.extend(
                validate_design_precheck(
                    design,
                    eligible_research_claim_ids,
                    transferred_design_question_ids,
                )
            )
        else:
            errors.extend(
                validate_design_doc(
                    design,
                    interface_details,
                    research_claim_ids,
                    eligible_research_claim_ids,
                    transferred_design_question_ids,
                )
            )

        if schema_version >= 5 and design_schema_version(design_text) >= 6:
            errors.extend(
                validate_design_sql_gate_binding(
                    design_text,
                    research_text,
                    meta,
                )
            )
        mysql_change = extract_line_value(design_text, "- MySQL 结构变更：")
        if schema_version < 5 and design_schema_version(design_text) >= 2:
            if mysql_change == "有" and not schema.exists():
                errors.append("02-design.md 声明有 MySQL 结构变更，但缺少 04-schema.sql")
            if mysql_change == "无" and schema.exists():
                errors.append("02-design.md 声明无 MySQL 结构变更，但存在 04-schema.sql")
            if schema.exists() and not schema_confirmed and not waiting_for_schema_confirmation:
                errors.append("04-schema.sql 尚未执行 confirm-schema 锁定用户确认，禁止完成技术方案")

    if reached("任务拆分"):
        if schema_version >= 5 and task_schema_version(read_text(tasks)) != 3:
            errors.append("新版需求的 03-tasks.md 必须使用 Task v3")
        core_change_design_ids = extract_core_change_design_ids_from_design(design_text) if design_text else set()
        errors.extend(
            validate_tasks_doc(
                tasks,
                interface_details,
                design_ids,
                research_claim_ids,
                schema.exists(),
                core_change_design_ids,
                sql_draft.exists(),
            )
        )

    if reached("编码实现") and not implementation_log.exists():
        errors.append("当前阶段已进入编码实现，缺少 05-implementation-log.md")
    if phase == "代码检查" and not code_review_index.exists():
        errors.append("当前阶段已进入代码检查，缺少 06-code-review.md")
    if reached("测试验证") and not test_report_index.exists():
        errors.append("当前阶段已进入测试验证，缺少 07-test-report.md")

    if schema.exists() and schema_version < 5:
        errors.extend(validate_schema_doc(schema, meta, research_claim_ids, schema_design_ids))
        schema_confirmation = meta.get("schema_confirmation", {})
        confirmed_schema_fingerprint = str(schema_confirmation.get("confirmed_schema_sha256", "")).strip()
        current_schema_fingerprint = schema_fingerprint(read_text(schema))
        schema_gate = bool(gates.get("schema_confirmed", False))
        if schema_gate and not confirmed_schema_fingerprint:
            errors.append("meta.json 缺少已确认 SQL 指纹")
        if schema_gate and confirmed_schema_fingerprint != current_schema_fingerprint:
            errors.append("04-schema.sql 在用户确认后发生变化，必须重新执行 confirm-schema")
        if reached("任务拆分") and not schema_gate:
            errors.append("存在 04-schema.sql，但尚未完成用户 SQL 确认，不能进入任务拆分")

    errors.extend(validate_implementation_log(implementation_log))
    # Review 是完全可选的独立动作；通用需求校验不把 06 工件当成门禁。
    # 用户真正执行 Review 时，review-mark 会单独校验两项检查和结论。
    errors.extend(validate_test_report_artifacts(test_report_index, test_report_rounds))
    if reached("代码检查"):
        errors.extend(validate_implementation_completion(implementation_log))
    # Code Review 是可选阶段。测试验证只依赖已完成实现与测试工件；
    # 已存在的 Review 报告作为参考，不形成流程门禁。
    if gates.get("test_passed"):
        errors.extend(validate_test_report_completion(test_report_index, test_report_rounds))

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


def unresolved_research_questions(text: str) -> int:
    """从 01-research.md 的唯一疑问账本统计未解决问题。

    新版按 Qxx 行的「状态」判断；已确认和转下游不阻塞。旧版 research 若使用
    「是否阻塞」列，则值为「是」的 Qxx 仍视为未解决，以兼容已有需求目录。
    """
    heading = (
        "## 9. 进入技术方案前疑问账本"
        if "## 9. 进入技术方案前疑问账本" in text
        else "## 10. 进入技术方案前阻塞问题"
    )
    unresolved = 0
    for section in extract_sections(text, heading):
        headers, rows = extract_first_table(section)
        for row in rows:
            question_id = table_cell(headers, row, "编号")
            if not re.fullmatch(r"Q\d+", question_id or ""):
                continue
            if "状态" in headers:
                status = table_cell(headers, row, "状态")
                if status not in {"已确认", "转下游"}:
                    unresolved += 1
            elif "是否阻塞" in headers and table_cell(headers, row, "是否阻塞") == "是":
                unresolved += 1
    return unresolved


def current_scope_note() -> str:
    return f"当前 ggg dist 支持到 {PUBLIC_PHASES[-1]} 阶段"
