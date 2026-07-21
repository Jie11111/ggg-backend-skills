#!/usr/bin/env python3
"""管理 GGG 编码实现会话，并用真实 Git 差异约束完成结论。"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workflow_validation as validator


STATE_FILE = "implementation-state.json"
STATE_SCHEMA_VERSION = 11
REVIEW_DISPOSITIONS = {"light", "formal", "skipped"}
DOCUMENT_SUFFIXES = {".md", ".rst", ".adoc"}
PRECHECK_ROWS = """| 轮次 | 检查面 | 预检结论 | 事实依据 | 状态 |
|---|---|---|---|---|
| I | 范围与主链路 |  |  | 通过 / 阻塞 |
| I | 代码落点与职责 |  |  | 通过 / 阻塞 |
| I | 数据、契约与失败边界 |  |  | 通过 / 阻塞 |
| I | 验证策略 |  |  | 通过 / 阻塞 |"""


def run_git(repo: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout.strip()


def run_git_bytes(repo: Path, *args: str, check: bool = True) -> bytes:
    """执行需要 NUL 分隔输出的 Git 命令，避免路径转义和换行歧义。"""
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
    )
    if check and completed.returncode != 0:
        message = completed.stderr or completed.stdout
        raise RuntimeError(message.decode("utf-8", errors="replace").strip())
    return completed.stdout


def decode_git_path(value: bytes) -> str:
    return value.decode("utf-8", errors="surrogateescape")


def file_digest(path: Path) -> str:
    if path.is_symlink():
        digest = hashlib.sha256()
        digest.update(b"symlink\0")
        digest.update(os.fsencode(os.readlink(path)))
        return digest.hexdigest()
    if not path.exists() or not path.is_file():
        return "<missing>"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_mode(path: Path) -> str:
    """返回 Git 关心的文件类型和可执行位；缺失文件使用稳定标记。"""
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return "<missing>"
    if stat.S_ISLNK(mode):
        return "120000"
    if stat.S_ISREG(mode):
        return "100755" if mode & 0o111 else "100644"
    return f"{stat.S_IFMT(mode):o}"


def file_snapshot(path: Path) -> dict[str, str]:
    return {"digest": file_digest(path), "mode": file_mode(path)}


def state_path(record: Path) -> Path:
    return record.resolve().parent / STATE_FILE


def atomic_write_text(path: Path, text: str) -> None:
    """在同目录落临时文件后原子替换，避免中断时留下半份状态或 Markdown。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), existing_mode)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def load_state(record: Path) -> dict:
    path = state_path(record)
    if not path.exists():
        raise SystemExit(f"缺少实现会话状态: {path}。编码前必须先执行 implementation-start")
    state = json.loads(path.read_text(encoding="utf-8"))
    normalize_legacy_review_state(state)
    return state


def save_state(record: Path, state: dict) -> None:
    state["schema_version"] = max(
        int(state.get("schema_version", 1)),
        STATE_SCHEMA_VERSION,
    )
    normalize_legacy_review_state(state)
    atomic_write_text(
        state_path(record),
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
    )


def normalize_legacy_review_state(state: dict) -> None:
    """给旧状态补出 disposition/gate 语义，但不把 skipped 冒充 passed。"""
    review = state.get("review")
    if not isinstance(review, dict) or not review:
        return
    if review.get("model") == "optional":
        review["passed"] = review.get("result") == "passed"
        return
    disposition = review.get("disposition")
    if disposition not in REVIEW_DISPOSITIONS:
        disposition = "formal"
        review["disposition"] = disposition
    result = review.get("result")
    review["passed"] = bool(result == "passed" and disposition != "skipped")
    review["gate_satisfied"] = bool(
        review["passed"] or (disposition == "skipped" and result == "skipped")
    )


def review_disposition(review: dict) -> str:
    disposition = review.get("disposition")
    return disposition if disposition in REVIEW_DISPOSITIONS else "formal"


def review_gate_satisfied(review: dict) -> bool:
    disposition = review_disposition(review)
    return bool(
        (disposition in {"light", "formal"} and review.get("result") == "passed")
        or (disposition == "skipped" and review.get("result") == "skipped")
    )


def review_passed(review: dict) -> bool:
    return bool(
        review_disposition(review) in {"light", "formal"}
        and review.get("result") == "passed"
    )


def update_record_line(record: Path, prefix: str, value: str) -> None:
    lines = record.read_text(encoding="utf-8").splitlines()
    changed = False
    for index, line in enumerate(lines):
        if line.strip().startswith(prefix):
            lines[index] = f"{prefix}{value}"
            changed = True
            break
    if not changed:
        raise SystemExit(f"记录模板缺少状态字段: {prefix}")
    atomic_write_text(record, "\n".join(lines) + "\n")


def upsert_record_line_after(
    record: Path,
    prefix: str,
    value: str,
    anchor_prefix: str,
) -> None:
    """更新字段；旧模板缺少字段时在稳定锚点后补入，避免要求用户迁移。"""
    lines = record.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith(prefix):
            lines[index] = f"{prefix}{value}"
            atomic_write_text(record, "\n".join(lines) + "\n")
            return
    for index, line in enumerate(lines):
        if line.strip().startswith(anchor_prefix):
            lines.insert(index + 1, f"{prefix}{value}")
            atomic_write_text(record, "\n".join(lines) + "\n")
            return
    raise SystemExit(f"记录模板缺少可插入字段的锚点: {anchor_prefix}")


def markdown_cell(value: str) -> str:
    """转义 Markdown 表格单元格，避免验证命令破坏记录结构。"""
    return value.replace("|", "&#124;").replace("\r", " ").replace("\n", " ")


def append_table_row(
    record: Path,
    heading: str,
    required_headers: tuple[str, ...],
    row: list[str],
    placeholder_round: str = "I",
) -> None:
    """替换模板占位行或向指定章节的首个表格追加一行。"""
    lines = record.read_text(encoding="utf-8").splitlines()
    try:
        heading_index = next(index for index, line in enumerate(lines) if line.strip() == heading)
    except StopIteration as error:
        raise SystemExit(f"记录模板缺少章节: {heading}") from error

    header_index = -1
    headers: list[str] = []
    for index in range(heading_index + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("#"):
            break
        if not stripped.startswith("|"):
            continue
        candidate = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(header in candidate for header in required_headers):
            header_index = index
            headers = candidate
            break
    if header_index < 0:
        raise SystemExit(f"{heading} 缺少表头: {', '.join(required_headers)}")

    table_end = header_index + 2
    while table_end < len(lines) and lines[table_end].strip().startswith("|"):
        table_end += 1

    first_header = headers[0]
    first_value = row[headers.index(first_header)]
    rendered = "| " + " | ".join(markdown_cell(value) for value in row) + " |"
    placeholder_index = None
    for index in range(header_index + 2, table_end):
        cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
        if cells and cells[0] == placeholder_round:
            placeholder_index = index
            break
    if placeholder_index is not None and first_value != placeholder_round:
        lines[placeholder_index] = rendered
    else:
        lines.insert(table_end, rendered)
    atomic_write_text(record, "\n".join(lines) + "\n")


def ensure_precheck_record_structure(record: Path) -> None:
    """轻量迁移旧记录，使已有 feature 无需手工复制新模板。"""
    text = record.read_text(encoding="utf-8")
    if record.name == "quick.md":
        heading = "### 3.1 编码前实现预检"
        insertion_point = "## 4. 验证记录"
        block = (
            f"{heading}\n\n"
            "> `implementation-start` 后、第一处新代码修改前填写并执行 `implementation-precheck`。"
            "简单改动每项一两句话即可。\n\n"
            f"{PRECHECK_ROWS}\n\n"
        )
    else:
        heading = "## 0. 编码前实现预检"
        insertion_point = "## 1. 实现记录索引"
        block = (
            f"{heading}\n\n"
            "> `implementation-start` 后、第一处新代码修改前填写并执行 `implementation-precheck`。"
            "每项一两句话即可；事实依据写 Txx/Dxx、文件、类、方法或项目约定。\n\n"
            f"{PRECHECK_ROWS}\n\n"
        )
    if heading not in text:
        if insertion_point not in text:
            raise SystemExit(f"记录模板缺少预检插入位置: {insertion_point}")
        text = text.replace(insertion_point, block + insertion_point, 1)

    required_fields = [
        "- 风险级别：",
        "- 预检状态：",
        "- 预检对应实现轮次：",
        "- 预检记录指纹：",
    ]
    if not all(prefix in text for prefix in required_fields):
        state_line = "- 实现会话状态文件：`implementation-state.json`"
        if state_line not in text:
            raise SystemExit(f"记录模板缺少状态字段: {state_line}")
        missing_lines = [prefix for prefix in required_fields if prefix not in text]
        text = text.replace(state_line, state_line + "\n" + "\n".join(missing_lines), 1)
    atomic_write_text(record, text)
    ensure_review_record_fields(record)


def is_quick_v3_record(record: Path, text: str | None = None) -> bool:
    """识别使用中文简洁 Review 字段的 quick v3 记录。"""
    if record.name != "quick.md":
        return False
    content = text if text is not None else record.read_text(encoding="utf-8")
    return validator.quick_schema_version(content) >= 3


def is_optional_review_record(record: Path, text: str | None = None) -> bool:
    content = text if text is not None else record.read_text(encoding="utf-8")
    if record.name == "quick.md":
        return validator.quick_schema_version(content) >= 4
    if record.name == "05-implementation-log.md":
        return validator.implementation_schema_version(content) >= 3
    if record.name == "06-code-review.md":
        return validator.review_schema_version(content) >= 2
    return False


def review_record_field_prefixes(
    record: Path,
    text: str | None = None,
) -> dict[str, str]:
    """返回当前记录 schema 的 Review 状态字段，兼容旧记录而不重复造字段。"""
    if is_optional_review_record(record, text):
        return {
            "status": "- Review 状态：",
            "result": "- Review 结论：",
            "implementation_round": "- Review 对应实现轮次：",
            "fingerprint": "- Review 对应差异指纹：",
        }
    if record.name == "06-code-review.md":
        return {
            "result": "- 当前结论：",
            "disposition": "- Review disposition：",
            "gate_satisfied": "- Review 门禁是否满足：",
            "skip_reason": "- Review 跳过原因：",
            "implementation_round": "- 对应实现轮次：",
            "fingerprint": "- 实现差异指纹：",
        }
    if is_quick_v3_record(record, text):
        return {
            "result": "- Review 结论：",
            "disposition": "- Review 处置：",
            "gate_satisfied": "- Review Gate 是否满足：",
            "skip_reason": "- Review 跳过来源：",
            "implementation_round": "- Review 对应实现轮次：",
            "fingerprint": "- Review 对应差异指纹：",
        }
    return {
        "result": "- Review 结论：",
        "disposition": "- Review disposition：",
        "gate_satisfied": "- Review 门禁是否满足：",
        "skip_reason": "- Review 跳过原因：",
        "implementation_round": "- Review 对应实现轮次：",
        "fingerprint": "- Review 对应差异指纹：",
    }


def ensure_review_record_fields(record: Path) -> None:
    """给旧实现记录补齐 disposition 与门禁字段。"""
    text = record.read_text(encoding="utf-8")
    if is_optional_review_record(record, text):
        return
    if not any(
        line.strip().startswith("- Review 结论：")
        for line in text.splitlines()
    ):
        return
    if is_quick_v3_record(record, text):
        return
    for prefix, value, anchor in [
        ("- Review disposition：", "未执行", "- Review 结论："),
        ("- Review 门禁是否满足：", "否", "- Review disposition："),
        ("- Review 跳过原因：", "", "- Review 门禁是否满足："),
    ]:
        upsert_record_line_after(record, prefix, value, anchor)


def prepare_precheck_round_rows(record: Path, round_id: str, risk_profile: str) -> None:
    """按风险档位复用模板占位行或追加当前 Ixx 所需预检项。"""
    text = record.read_text(encoding="utf-8")
    section = validator.implementation_precheck_section(record)
    if not section:
        raise SystemExit("实现记录缺少编码前实现预检章节")
    required_items = validator.IMPLEMENTATION_PRECHECK_PROFILES[risk_profile]
    if all(f"| {round_id} | {item} |" in section for item in required_items):
        return

    updated_section = section
    appended_rows: list[str] = []
    for item in required_items:
        if f"| {round_id} | {item} |" in updated_section:
            continue
        if f"| I | {item} |" in updated_section:
            updated_section = updated_section.replace(
                f"| I | {item} |",
                f"| {round_id} | {item} |",
                1,
            )
        else:
            appended_rows.append(f"| {round_id} | {item} |  |  | 通过 / 阻塞 |")
    if appended_rows:
        updated_section = updated_section.rstrip() + "\n" + "\n".join(appended_rows)
    atomic_write_text(record, text.replace(section, updated_section, 1))


def validate_record_state_fields(record: Path) -> None:
    """在保存会话状态前确认模板可承载全部实现与 Review 状态。"""
    text = record.read_text(encoding="utf-8")
    review_fields = review_record_field_prefixes(record, text)
    required = [
        "- 实现状态：",
        "- 当前实现轮次：",
        "- 风险级别：",
        "- 预检状态：",
        "- 预检对应实现轮次：",
        "- 预检记录指纹：",
        "- 涉及 Git 仓库及编码基线：",
        "- 最终差异指纹：",
        review_fields["result"],
        review_fields["implementation_round"],
        review_fields["fingerprint"],
    ]
    if is_optional_review_record(record, text):
        required.append(review_fields["status"])
    else:
        required.extend(
            [
                review_fields["disposition"],
                review_fields["gate_satisfied"],
                review_fields["skip_reason"],
            ]
        )
    missing = [prefix for prefix in required if not any(line.strip().startswith(prefix) for line in text.splitlines())]
    if missing:
        raise SystemExit("记录模板缺少实现会话字段: " + ", ".join(missing))


def require_quick_boundary_ready(record: Path) -> None:
    if record.name != "quick.md":
        return
    errors = validator.validate_quick_boundary_ready(record)
    if errors:
        message = "\n".join(f"- {error}" for error in errors)
        raise SystemExit(f"quick 边界尚未确认，不能进入或完成实现：\n{message}")


def quick_boundary_fingerprint(record: Path) -> str:
    """锁定 quick 本轮实现所依据的边界，避免确认后静默换题。"""
    if record.name != "quick.md":
        return ""
    text = record.read_text(encoding="utf-8")
    return fingerprint_entries(
        [
            (
                "quick-schema-version",
                str(validator.quick_schema_version(text)).encode("utf-8"),
            ),
            (
                "## 1. 边界确认",
                validator.extract_section(text, "## 1. 边界确认").encode("utf-8"),
            ),
            (
                "## 2. 升级 full 触发条件",
                validator.extract_section(text, "## 2. 升级 full 触发条件").encode("utf-8"),
            ),
        ]
    )


def repo_label(repo: Path, used: set[str]) -> str:
    base = repo.name or "repo"
    label = base
    suffix = 2
    while label in used:
        label = f"{base}-{suffix}"
        suffix += 1
    used.add(label)
    return label


def initial_dirty_snapshot(repo: Path) -> dict[str, dict[str, str]]:
    status = run_git_bytes(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    result: dict[str, dict[str, str]] = {}
    entries = status.split(b"\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        status_code = entry[:2].decode("ascii", errors="replace")
        relative = decode_git_path(entry[3:])
        if "R" in status_code or "C" in status_code:
            old_relative = decode_git_path(entries[index])
            index += 1
            result[old_relative] = {"status": status_code, **file_snapshot(repo / old_relative)}
        result[relative] = {"status": status_code, **file_snapshot(repo / relative)}
    return result


def resolve_commit(repo: Path, revision: str, label: str) -> str:
    revision = revision.strip()
    if not revision:
        raise SystemExit(f"{label} 不能为空")
    resolved = run_git(
        repo,
        "rev-parse",
        "--verify",
        f"{revision}^{{commit}}",
        check=False,
    )
    if not re.fullmatch(r"[0-9a-f]{40,64}", resolved):
        raise SystemExit(f"{label} 不是有效提交: {revision}")
    return resolved


def committed_diff_paths(repo: Path, base: str, target: str) -> list[str]:
    output = run_git_bytes(
        repo,
        "diff",
        "--name-only",
        "-z",
        "--diff-filter=ACMRD",
        base,
        target,
        "--",
    )
    return sorted(
        decode_git_path(value)
        for value in output.split(b"\0")
        if value
    )


def resolve_committed_diff_sources(
    repo_states: list[dict],
    diff_ranges: list[str],
    adopted_commits: list[str],
) -> None:
    """把已提交差异绑定到仓库；多仓按 --repo-root 顺序各提供一个值。"""
    if diff_ranges and adopted_commits:
        raise SystemExit("--diff-range 与 --adopt-commit 不能在同一实现轮次混用")
    values = diff_ranges or adopted_commits
    if not values:
        return
    if len(values) != len(repo_states):
        if len(repo_states) == 1:
            raise SystemExit("单仓实现只能提供一个 --diff-range 或 --adopt-commit")
        raise SystemExit("多仓实现必须按 --repo-root 顺序为每个仓库提供一个已提交差异")

    source_kind = "diff-range" if diff_ranges else "adopt-commit"
    for repo_state, value in zip(repo_states, values):
        repo = Path(repo_state["root"])
        if source_kind == "diff-range":
            if "..." in value or value.count("..") != 1:
                raise SystemExit("--diff-range 必须使用 <base>..<target>，不支持三点范围")
            base_expression, target_expression = value.split("..", 1)
            base = resolve_commit(repo, base_expression, "--diff-range base")
            target = resolve_commit(repo, target_expression, "--diff-range target")
        else:
            target = resolve_commit(repo, value, "--adopt-commit")
            base = resolve_commit(repo, f"{target}^", "--adopt-commit 父提交")

        ancestor = subprocess.run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor", target, "HEAD"],
            check=False,
            capture_output=True,
        )
        if ancestor.returncode != 0:
            raise SystemExit(
                f"已提交差异目标 {target[:12]} 不在当前 HEAD 历史中；"
                "请先切换到包含该提交的分支"
            )
        paths = committed_diff_paths(repo, base, target)
        if not paths:
            raise SystemExit(f"已提交差异 {base[:12]}..{target[:12]} 没有文件变化")
        repo_state["diff_source"] = {
            "type": source_kind,
            "base": base,
            "target": target,
            "requested": value,
        }
        repo_state["committed_diff_paths"] = paths
        repo_state["round_adopted_committed"] = paths


def resolve_adopted_existing_files(
    repo_states: list[dict],
    values: list[str],
) -> dict[str, set[str]]:
    """把用户明确接管的已有脏文件绑定到唯一仓库，避免吞入无关改动。"""
    adopted_by_root = {state["root"]: set() for state in repo_states}
    if not values:
        return adopted_by_root

    multiple_repositories = len(repo_states) > 1
    for value in values:
        raw_path = Path(value).expanduser()
        if multiple_repositories and not raw_path.is_absolute():
            raise SystemExit("多仓库接管已有实现时，--adopt-existing-file 必须使用绝对路径")

        matches: list[tuple[dict, str]] = []
        for repo_state in repo_states:
            repo = Path(repo_state["root"]).resolve()
            lexical_candidate = Path(
                os.path.abspath(os.fspath(raw_path if raw_path.is_absolute() else repo / raw_path))
            )
            candidates = [lexical_candidate, lexical_candidate.resolve()]
            relative = None
            for candidate in candidates:
                try:
                    relative = candidate.relative_to(repo)
                    break
                except ValueError:
                    continue
            if relative is None:
                continue
            if relative == Path("."):
                continue
            matches.append((repo_state, relative.as_posix()))

        if len(matches) != 1:
            reason = "不属于任何已声明仓库" if not matches else "同时匹配多个已声明仓库"
            raise SystemExit(f"无法接管已有实现文件 {value}: {reason}")

        repo_state, relative = matches[0]
        if relative not in repo_state["initial_dirty"]:
            raise SystemExit(
                f"无法接管已有实现文件 {value}: 该文件在 implementation-start 时不是 Git 脏文件"
            )
        adopted_by_root[repo_state["root"]].add(relative)
    return adopted_by_root


def inherited_previous_files(previous: dict, repo_states: list[dict]) -> dict[str, set[str]]:
    """继承上一完成轮次已锁定的需求文件，避免新 Ixx 把它们误判为无关脏文件。"""
    inherited = {state["root"]: set() for state in repo_states}
    if previous.get("status") != "completed":
        return inherited

    previous_repositories = {
        str(Path(item.get("root", "")).resolve()): item
        for item in previous.get("repositories", [])
        if item.get("root")
    }
    snapshot_by_label = {
        item.get("label"): item
        for item in (previous.get("completion_snapshot") or {}).get("repositories", [])
        if item.get("label")
    }
    for repo_state in repo_states:
        previous_repo = previous_repositories.get(repo_state["root"])
        if not previous_repo:
            continue
        snapshot = snapshot_by_label.get(previous_repo.get("label"), {})
        previous_paths = {
            item.get("path")
            for item in snapshot.get("files", [])
            if item.get("path")
        }
        inherited[repo_state["root"]].update(
            path for path in previous_paths if path in repo_state.get("initial_dirty", {})
        )
    return inherited


def changed_paths(repo_state: dict) -> set[str]:
    committed_paths = set(repo_state.get("committed_diff_paths", []))
    if committed_paths:
        return committed_paths | set(repo_state.get("adopted_existing", []))

    repo = Path(repo_state["root"])
    base_head = repo_state["base_head"]
    paths: set[str] = set()

    diff_output = run_git_bytes(repo, "diff", "--name-only", "-z", "--diff-filter=ACMRD", base_head, "--")
    paths.update(decode_git_path(value) for value in diff_output.split(b"\0") if value)

    untracked = run_git_bytes(repo, "ls-files", "-z", "--others", "--exclude-standard")
    paths.update(decode_git_path(value) for value in untracked.split(b"\0") if value)

    initial_dirty = repo_state.get("initial_dirty", {})
    adopted_existing = set(repo_state.get("adopted_existing", []))
    for relative, snapshot in initial_dirty.items():
        if relative not in paths:
            continue
        if relative in adopted_existing:
            continue
        current = file_snapshot(repo / relative)
        digest_matches = current["digest"] == snapshot.get("digest")
        mode_matches = "mode" not in snapshot or current["mode"] == snapshot.get("mode")
        if digest_matches and mode_matches:
            paths.remove(relative)
    return paths


def is_quality_file(path: str) -> bool:
    """除工作流文档外默认纳入实现差异，避免扩展名白名单漏掉真实产物。"""
    candidate = Path(path)
    return candidate.name != STATE_FILE and candidate.suffix.lower() not in DOCUMENT_SUFFIXES


def is_feature_report_file(state: dict, repo_state: dict, path: str) -> bool:
    """只排除当前 feature 的运行证据，业务仓库中的同名 reports 仍计入 Diff。"""
    record_value = state.get("record")
    if not record_value:
        return False
    feature_dir = Path(record_value).resolve().parent
    candidate = (Path(repo_state["root"]).resolve() / path).resolve()
    try:
        relative = candidate.relative_to(feature_dir)
    except ValueError:
        return False
    return bool(relative.parts) and relative.parts[0] == "reports"


def is_state_quality_file(
    state: dict,
    repo_state: dict,
    path: str,
) -> bool:
    return is_quality_file(path) and not is_feature_report_file(state, repo_state, path)


def collect_changes(state: dict) -> tuple[set[str], dict[str, list[str]]]:
    canonical: set[str] = set()
    by_repo: dict[str, list[str]] = {}
    for repo_state in state["repositories"]:
        label = repo_state["label"]
        repo_paths = sorted(
            path
            for path in changed_paths(repo_state)
            if is_state_quality_file(state, repo_state, path)
        )
        by_repo[label] = repo_paths
        canonical.update(f"{label}/{path}" for path in repo_paths)
    return canonical, by_repo


def current_snapshot(state: dict) -> dict:
    include_mode = int(state.get("schema_version", 2)) >= 3
    include_source = any(
        repository.get("diff_source")
        for repository in state.get("repositories", [])
    )
    repositories = []
    for repo_state in state["repositories"]:
        repo = Path(repo_state["root"])
        paths = sorted(
            path
            for path in changed_paths(repo_state)
            if is_state_quality_file(state, repo_state, path)
        )
        entries = []
        for relative in paths:
            snapshot = file_snapshot(repo / relative)
            entry = {"path": relative, "digest": snapshot["digest"]}
            if include_mode:
                entry["mode"] = snapshot["mode"]
            entries.append(entry)
        repositories.append(
            {
                "label": repo_state["label"],
                "head": run_git(repo, "rev-parse", "HEAD"),
                "source": repo_state.get("diff_source", {"type": "worktree"}),
                "files": entries,
            }
        )
    payload = {"repositories": repositories}
    fingerprint_payload = {"repositories": []}
    for item in repositories:
        fingerprint_repository = {
            "label": item["label"],
            "files": item["files"],
        }
        if include_source:
            fingerprint_repository["source"] = item.get(
                "source",
                {"type": "worktree"},
            )
        fingerprint_payload["repositories"].append(fingerprint_repository)
    encoded = json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    payload["fingerprint"] = hashlib.sha256(encoded).hexdigest()
    return payload


def snapshot_file_map(snapshot: dict) -> dict[tuple[str, str], tuple[str, str]]:
    result: dict[tuple[str, str], tuple[str, str]] = {}
    for repository in snapshot.get("repositories", []):
        label = repository.get("label", "")
        for item in repository.get("files", []):
            result[(label, item.get("path", ""))] = (
                item.get("digest", "<missing>"),
                item.get("mode", ""),
            )
    return result


def current_round_paths(state: dict, current: dict) -> set[str]:
    """返回本 Ixx 新增/改变的文件；完成快照仍锁定整个需求累计 Diff。"""
    start = state.get("start_snapshot") or reconstructed_start_snapshot(state)
    start_files = snapshot_file_map(start)
    current_files = snapshot_file_map(current)
    changed = {
        key
        for key in set(start_files) | set(current_files)
        if start_files.get(key) != current_files.get(key)
    }
    labels_by_root = {
        item.get("root"): item.get("label", "")
        for item in state.get("repositories", [])
    }
    repositories_by_label = {
        item.get("label", ""): item
        for item in state.get("repositories", [])
    }
    for repository in state.get("repositories", []):
        label = labels_by_root.get(repository.get("root"), "")
        inherited = set(repository.get("inherited_existing", []))
        explicitly_adopted = set(
            repository.get(
                "round_adopted_existing",
                set(repository.get("adopted_existing", [])) - inherited,
            )
        )
        for path in explicitly_adopted:
            if is_state_quality_file(state, repository, path):
                changed.add((label, path))
        for path in repository.get("round_adopted_committed", []):
            if is_state_quality_file(state, repository, path):
                changed.add((label, path))
    return {
        f"{label}/{path}"
        for label, path in changed
        if (
            label
            and path
            and label in repositories_by_label
            and is_state_quality_file(state, repositories_by_label[label], path)
        )
    }


def reconstructed_start_snapshot(state: dict) -> dict:
    """兼容旧状态文件：从启动时脏文件快照还原预检前允许存在的接管差异。"""
    include_mode = int(state.get("schema_version", 2)) >= 3
    repositories = []
    for repo_state in state["repositories"]:
        adopted = set(repo_state.get("adopted_existing", []))
        initial_dirty = repo_state.get("initial_dirty", {})
        entries = []
        for relative in sorted(adopted):
            if not is_state_quality_file(state, repo_state, relative):
                continue
            snapshot = initial_dirty.get(relative, {})
            entry = {"path": relative, "digest": snapshot.get("digest", "<missing>")}
            if include_mode:
                entry["mode"] = snapshot.get("mode", "<missing>")
            entries.append(entry)
        repositories.append(
            {
                "label": repo_state["label"],
                "head": repo_state.get("base_head", ""),
                "files": entries,
            }
        )
    fingerprint_payload = {
        "repositories": [
            {"label": item["label"], "files": item["files"]}
            for item in repositories
        ]
    }
    encoded = json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return {
        "repositories": repositories,
        "fingerprint": hashlib.sha256(encoded).hexdigest(),
    }


def recorded_quality_paths(record: Path, expected_round: str) -> set[str]:
    text = record.read_text(encoding="utf-8")
    if record.name == "quick.md":
        if "### 4.1 逐文件代码质量门禁" in text:
            section = validator.extract_section(text, "### 4.1 逐文件代码质量门禁")
            headers, rows = validator.extract_first_table(section)
            return {
                path
                for row in rows
                for path in validator.extract_quality_paths(validator.table_cell(headers, row, "文件"))
            }
        return validator.extract_quality_paths(validator.extract_line_value(text, "- 修改文件："))

    if "## 4. 逐文件代码质量门禁" in text:
        section = validator.extract_section(text, "## 4. 逐文件代码质量门禁")
        headers, rows = validator.extract_first_table(section)
        result: set[str] = set()
        for row in rows:
            if validator.table_cell(headers, row, "轮次") != expected_round:
                continue
            result.update(validator.extract_quality_paths(validator.table_cell(headers, row, "文件")))
        return result

    headers, rows = validator.extract_first_table(validator.extract_section(text, "## 1. 实现记录索引"))
    if "轮次" not in headers or "实际修改文件" not in headers:
        return set()
    result: set[str] = set()
    for row in rows:
        if validator.table_cell(headers, row, "轮次") != expected_round:
            continue
        result.update(validator.extract_quality_paths(validator.table_cell(headers, row, "实际修改文件")))
    return result


def recorded_completed_tasks(record: Path) -> set[str]:
    if record.name != "05-implementation-log.md":
        return set()
    text = record.read_text(encoding="utf-8")
    headers, rows = validator.extract_first_table(
        validator.extract_section(text, "## 1. 实现记录索引")
    )
    result: set[str] = set()
    for row in rows:
        if not re.fullmatch(r"I\d+", validator.table_cell(headers, row, "轮次")):
            continue
        result.update(
            re.findall(r"\bT\d+\b", validator.table_cell(headers, row, "任务"))
        )
    return result


def compare_recorded_paths(
    actual_paths: set[str],
    recorded_paths: set[str],
    repo_labels: set[str],
) -> list[str]:
    """双向核对实现记录；多仓库时禁止省略仓库标签。"""
    errors: list[str] = []
    normalized: set[str] = set()
    unqualified: set[str] = set()
    for path in recorded_paths:
        prefix = path.split("/", 1)[0]
        if prefix in repo_labels:
            normalized.add(path)
        elif len(repo_labels) == 1:
            normalized.add(f"{next(iter(repo_labels))}/{path}")
        else:
            unqualified.add(path)

    if unqualified:
        errors.append("多仓库实现记录必须使用 仓库标签/相对路径: " + ", ".join(sorted(unqualified)))
    missing = sorted(actual_paths - normalized)
    if missing:
        errors.append("实现记录未登记真实 Git 改动文件: " + ", ".join(missing))
    extra = sorted(normalized - actual_paths)
    if extra:
        errors.append("实现记录包含本轮未实际修改的文件: " + ", ".join(extra))
    return errors


def validate_record(
    record: Path,
    actual_paths: set[str],
    expected_round: str,
    repo_labels: set[str] | None = None,
    expected_task_ids: set[str] | None = None,
) -> list[str]:
    if record.name == "quick.md":
        errors = validator.validate_quick_implementation_completion(record)
    elif record.name == "05-implementation-log.md":
        errors = validator.validate_implementation_completion(record, expected_task_ids)
    else:
        return ["--record 只支持 quick.md 或 05-implementation-log.md"]

    recorded = recorded_quality_paths(record, expected_round)
    labels = repo_labels or {path.split("/", 1)[0] for path in actual_paths if "/" in path}
    errors.extend(compare_recorded_paths(actual_paths, recorded, labels))
    return errors


def next_round_number(record: Path, previous: dict) -> int:
    """同时参考状态文件和实现记录，避免状态迁移或删除后重复生成 I1。"""
    numbers = [int(value) for value in re.findall(r"\bI(\d+)\b", record.read_text(encoding="utf-8"))]
    previous_round = previous.get("round", "")
    if re.fullmatch(r"I\d+", previous_round):
        numbers.append(int(previous_round[1:]))
    return max(numbers, default=0) + 1


def update_active_round_record(record: Path, state: dict, baselines: str | None = None) -> None:
    """统一重置新一轮实现记录，避免 start/restart 状态语义漂移。"""
    review_fields = review_record_field_prefixes(record)
    quick_v3 = is_quick_v3_record(record)
    optional_review = is_optional_review_record(record)
    update_record_line(record, "- 实现状态：", "编码中")
    update_record_line(record, "- 当前实现轮次：", state["round"])
    update_record_line(record, "- 风险级别：", state["risk_profile"])
    update_record_line(record, "- 预检状态：", "未执行")
    update_record_line(record, "- 预检对应实现轮次：", "")
    update_record_line(record, "- 预检记录指纹：", "")
    if baselines is not None:
        update_record_line(record, "- 涉及 Git 仓库及编码基线：", baselines)
    update_record_line(record, "- 最终差异指纹：", "")
    if optional_review:
        update_record_line(record, review_fields["status"], "未执行")
        update_record_line(record, review_fields["result"], "未执行")
    else:
        update_record_line(record, review_fields["result"], "未执行")
        update_record_line(record, review_fields["disposition"], "未执行")
        update_record_line(record, review_fields["gate_satisfied"], "否")
        update_record_line(
            record,
            review_fields["skip_reason"],
            "不涉及" if quick_v3 else "",
        )
    update_record_line(record, review_fields["implementation_round"], "")
    update_record_line(record, review_fields["fingerprint"], "")
    if record.name == "quick.md":
        if not quick_v3 and not optional_review:
            upsert_record_line_after(
                record,
                "- Review 方式：",
                "未执行",
                "- Review 结论：",
            )
            upsert_record_line_after(
                record,
                "- Self-review 原因：",
                "",
                "- Review 方式：",
            )
        quick_text = record.read_text(encoding="utf-8")
        for prefix, value in [
            ("- Review Gate A：", "未执行"),
            ("- Review Gate B：", "未执行"),
            ("- 测试结论：", "未执行"),
            ("- 测试对应实现轮次：", ""),
            ("- 测试对应差异指纹：", ""),
        ]:
            if any(line.strip().startswith(prefix) for line in quick_text.splitlines()):
                update_record_line(record, prefix, value)


def command_start(args: argparse.Namespace) -> None:
    record = Path(args.record).resolve()
    if not record.exists():
        raise SystemExit(f"记录文件不存在: {record}")
    ensure_precheck_record_structure(record)
    validate_record_state_fields(record)
    require_quick_boundary_ready(record)

    repos = [Path(value).resolve() for value in args.repo_root]
    if not repos:
        raise SystemExit("implementation-start 至少需要一个 --repo-root")
    for repo in repos:
        if run_git(repo, "rev-parse", "--is-inside-work-tree", check=False) != "true":
            raise SystemExit(f"不是 Git 仓库: {repo}")

    path = state_path(record)
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if previous.get("status") == "in_progress":
        raise SystemExit(
            f"已有进行中的实现会话 {previous.get('round')}，请继续、完成或使用 implementation-restart 重开"
        )

    round_number = next_round_number(record, previous)
    round_id = f"I{round_number}"
    precheck_section = validator.implementation_precheck_section(record)
    risk_profile = (
        "legacy"
        if "数据一致性与失败边界" in precheck_section
        and "验证策略" not in precheck_section
        else args.risk_profile
    )
    completed_before_start = (
        set(previous.get("completed_task_ids", []))
        | recorded_completed_tasks(record)
    )
    selected_tasks: list[str] = []
    if record.name == "05-implementation-log.md":
        planned_tasks = validator.implementation_task_ids(record.parent / "03-tasks.md")
        requested_tasks = set(args.task)
        unknown_tasks = sorted(requested_tasks - planned_tasks)
        if unknown_tasks:
            raise SystemExit("implementation-start 指定了不存在的任务: " + ", ".join(unknown_tasks))
        remaining_tasks = planned_tasks - completed_before_start
        if not requested_tasks and not remaining_tasks:
            raise SystemExit(
                "03-tasks.md 的编码任务均已完成；继续修正时请用 --task Txx "
                "明确本轮归属"
            )
        selected_tasks = sorted(
            requested_tasks or remaining_tasks,
            key=lambda value: int(value[1:]),
        )
        if not selected_tasks:
            raise SystemExit("03-tasks.md 没有可执行的 Txx 编码任务")
    elif args.task:
        raise SystemExit("quick.md 不使用 --task；范围以 quick 边界为准")
    prepare_precheck_round_rows(record, round_id, risk_profile)
    used_labels: set[str] = set()
    repo_states = []
    for repo in repos:
        repo_states.append(
            {
                "root": str(repo),
                "label": repo_label(repo, used_labels),
                "base_head": run_git(repo, "rev-parse", "HEAD"),
                "initial_dirty": initial_dirty_snapshot(repo),
            }
        )
    resolve_committed_diff_sources(
        repo_states,
        list(getattr(args, "diff_range", []) or []),
        list(getattr(args, "adopt_commit", []) or []),
    )
    adopted_by_root = resolve_adopted_existing_files(
        repo_states,
        args.adopt_existing_file,
    )
    inherited_by_root = inherited_previous_files(previous, repo_states)
    for repo_state in repo_states:
        inherited = inherited_by_root[repo_state["root"]]
        repo_state["inherited_existing"] = sorted(inherited)
        repo_state["round_adopted_existing"] = sorted(
            adopted_by_root[repo_state["root"]]
        )
        repo_state["adopted_existing"] = sorted(
            adopted_by_root[repo_state["root"]] | inherited
        )

    state = {
        "schema_version": STATE_SCHEMA_VERSION,
        "record": str(record),
        "round": round_id,
        "status": "in_progress",
        "risk_profile": risk_profile,
        "quick_boundary_fingerprint": quick_boundary_fingerprint(record),
        "started_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "repositories": repo_states,
        "completion_snapshot": None,
        "precheck": None,
        "verification_runs": [],
        "verification_waiver": None,
        "selected_tasks": selected_tasks,
        "completed_task_ids": sorted(
            completed_before_start,
            key=lambda value: int(value[1:]),
        ),
        "review": None,
        "test": None,
        "superseded_rounds": previous.get("superseded_rounds", []),
    }
    state["start_snapshot"] = current_snapshot(state)
    save_state(record, state)
    baselines = "；".join(
        (
            f"{item['label']}@{item['base_head']} ({item['root']})"
            if not item.get("diff_source")
            else (
                f"{item['label']}@{item['diff_source']['base'][:12]}"
                f"..{item['diff_source']['target'][:12]} ({item['root']})"
            )
        )
        for item in repo_states
    )
    update_active_round_record(record, state, baselines)
    print(f"[OK] 已开启实现会话 {state['round']}: {path}")
    for repo_state in repo_states:
        print(f"- {repo_state['label']}: {repo_state['base_head']} ({repo_state['root']})")
        for relative in repo_state["adopted_existing"]:
            source = (
                "已继承上一完成轮次"
                if relative in repo_state["inherited_existing"]
                else "已接管已有实现"
            )
            print(f"  - {source}: {relative}")
    if selected_tasks:
        print("- 本轮任务: " + ", ".join(selected_tasks))


def command_restart(args: argparse.Namespace) -> None:
    """废弃无法继续的当前轮次，以现有代码状态为下一轮修改前快照。"""
    record = Path(args.record).resolve()
    ensure_precheck_record_structure(record)
    validate_record_state_fields(record)
    require_quick_boundary_ready(record)
    state = load_state(record)
    if state.get("status") != "in_progress":
        raise SystemExit("只有进行中的实现会话可以重开；已完成会话直接执行 implementation-start")

    reason = args.reason.strip()
    if not reason:
        raise SystemExit("implementation-restart 必须提供非空 --reason")

    previous_round = state.get("round", "")
    normalized_state = dict(state)
    normalized_state["schema_version"] = max(
        int(state.get("schema_version", 1)),
        STATE_SCHEMA_VERSION,
    )
    snapshot = current_snapshot(normalized_state)
    history = list(state.get("superseded_rounds", []))
    history.append(
        {
            "round": previous_round,
            "reason": reason,
            "superseded_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "snapshot_fingerprint": snapshot["fingerprint"],
        }
    )

    round_id = f"I{next_round_number(record, state)}"
    risk_profile = state.get("risk_profile", "normal")
    prepare_precheck_round_rows(record, round_id, risk_profile)
    state.update(
        {
            "schema_version": max(
                int(state.get("schema_version", 1)),
                STATE_SCHEMA_VERSION,
            ),
            "round": round_id,
            "status": "in_progress",
            "risk_profile": risk_profile,
            "quick_boundary_fingerprint": quick_boundary_fingerprint(record),
            "started_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "start_snapshot": snapshot,
            "completion_snapshot": None,
            "precheck": None,
            "verification_runs": [],
            "verification_waiver": None,
            "selected_tasks": state.get("selected_tasks", []),
            "review": None,
            "test": None,
            "superseded_rounds": history,
        }
    )
    for repository in state.get("repositories", []):
        repository["round_adopted_existing"] = []
        repository["round_adopted_committed"] = list(
            repository.get("committed_diff_paths", [])
        )
    save_state(record, state)
    update_active_round_record(record, state)
    print(f"[OK] 已废弃实现轮次 {previous_round} 并开启 {round_id}")
    print(f"- 原因: {reason}")
    print(f"- 新轮次起始差异指纹: {snapshot['fingerprint']}")


def command_precheck(args: argparse.Namespace) -> None:
    record = Path(args.record).resolve()
    ensure_precheck_record_structure(record)
    state = load_state(record)
    if state.get("status") != "in_progress":
        raise SystemExit("当前实现会话不是编码中状态，不能登记编码前预检")

    start_snapshot = state.get("start_snapshot") or reconstructed_start_snapshot(state)
    current = current_snapshot(state)
    if current.get("fingerprint") != start_snapshot.get("fingerprint"):
        print("[FAIL] 编码前实现预检必须在本轮新增代码修改之前完成")
        print(f"- 启动快照: {start_snapshot.get('fingerprint')}")
        print(f"- 当前快照: {current.get('fingerprint')}")
        raise SystemExit(1)

    errors = validator.validate_implementation_precheck(
        record,
        state.get("round", ""),
        state.get("risk_profile", "normal"),
        set(state.get("selected_tasks", [])) if record.name == "05-implementation-log.md" else None,
    )
    if errors:
        print("[FAIL] 编码前实现预检门禁未通过：")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    fingerprint = validator.implementation_precheck_fingerprint(record)
    state["precheck"] = {
        "implementation_round": state.get("round"),
        "result": "passed",
        "record_fingerprint": fingerprint,
        "start_snapshot_fingerprint": start_snapshot.get("fingerprint"),
        "checked_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    save_state(record, state)
    update_record_line(record, "- 预检状态：", "通过")
    update_record_line(record, "- 预检对应实现轮次：", state.get("round", ""))
    update_record_line(record, "- 预检记录指纹：", fingerprint)
    print(f"[OK] {state.get('round')} 编码前实现预检已通过")
    print(f"[OK] 预检记录指纹: {fingerprint}")


def output_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def verification_cwd(state: dict, value: str | None) -> Path:
    repositories = [Path(item["root"]).resolve() for item in state.get("repositories", [])]
    if not repositories:
        raise SystemExit("实现会话没有已声明的 Git 仓库")
    candidate = Path(value).expanduser().resolve() if value else repositories[0]
    if not candidate.is_dir():
        raise SystemExit(f"验证工作目录不存在或不是目录: {candidate}")
    for repository in repositories:
        try:
            candidate.relative_to(repository)
            return candidate
        except ValueError:
            continue
    raise SystemExit("验证工作目录必须位于本轮已声明的 Git 仓库内")


def record_verification_result(record: Path, run: dict) -> None:
    command_text = shlex.join(run["command"])
    result = {
        "passed": "通过",
        "environment_blocked": "未验证",
    }.get(run["result"], "失败")
    evidence = (
        f"{run['id']}; exit={run['exit_code']}; "
        f"snapshot={run['after_snapshot_fingerprint'][:12]}; "
        f"stdout={run['stdout_sha256'][:12]}; stderr={run['stderr_sha256'][:12]}"
    )
    if record.name == "quick.md":
        environment_reason = (
            f"{run['id']} 命令因环境无法启动，exit={run['exit_code']}"
            if run["result"] == "environment_blocked"
            else ""
        )
        update_record_line(record, "- 验证命令 / 方式：", f"`{command_text}`")
        update_record_line(record, "- 验证结果：", result)
        update_record_line(record, "- 未验证项：", environment_reason or "无")
        update_record_line(
            record,
            "- 阻塞原因：",
            (
                "无"
                if run["result"] == "passed"
                else environment_reason or f"{run['id']} exit={run['exit_code']}"
            ),
        )
        return
    append_table_row(
        record,
        "## 3. 验证记录",
        ("轮次", "命令/方式", "结果", "证据", "未验证原因"),
        [
            run["implementation_round"],
            f"`{command_text}`",
            result,
            evidence,
            (
                f"{run['id']} 命令因环境无法启动，exit={run['exit_code']}"
                if run["result"] == "environment_blocked"
                else ""
            ),
        ],
    )


def record_verification_waiver(record: Path, round_id: str, reason: str) -> None:
    if record.name == "quick.md":
        update_record_line(record, "- 验证命令 / 方式：", "未执行（显式豁免）")
        update_record_line(record, "- 验证结果：", "未验证")
        update_record_line(record, "- 未验证项：", reason)
        update_record_line(record, "- 阻塞原因：", reason)
        return
    append_table_row(
        record,
        "## 3. 验证记录",
        ("轮次", "命令/方式", "结果", "证据", "未验证原因"),
        [round_id, "未执行（显式豁免）", "未验证", "", reason],
    )


def command_verify(args: argparse.Namespace) -> None:
    """以一次性非 PTY 进程执行验证，并绑定代码快照和回收事实。"""
    record = Path(args.record).resolve()
    state = load_state(record)
    if state.get("status") != "in_progress":
        raise SystemExit("只有编码中的实现轮次可以执行 implementation-verify")
    precheck = state.get("precheck") or {}
    if (
        precheck.get("result") != "passed"
        or precheck.get("implementation_round") != state.get("round")
    ):
        raise SystemExit("当前实现轮次必须先通过 implementation-precheck")

    command = list(args.verification_command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("implementation-verify 必须在 -- 后提供验证命令")
    if args.timeout_seconds < 1 or args.timeout_seconds > 3600:
        raise SystemExit("--timeout-seconds 必须在 1 到 3600 之间")

    cwd = verification_cwd(state, args.cwd)
    before = current_snapshot(state)
    started_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    environment_blocked = False
    timed_out = False
    residual_processes_detected = False
    term_sent = False
    kill_sent = False
    residual_processes_after_cleanup = False
    try:
        (
            exit_code,
            stdout,
            stderr,
            timed_out,
            residual_processes_detected,
            term_sent,
            kill_sent,
            residual_processes_after_cleanup,
        ) = run_test_command_once(command, cwd, args.timeout_seconds)
    except OSError as error:
        environment_blocked = True
        exit_code = 127
        stdout = b""
        stderr = str(error).encode("utf-8", errors="replace")
    after = current_snapshot(state)
    redacted_command = redact_test_argv(command)
    sensitive_command_values = sensitive_test_argv_values(command)
    runs = list(state.get("verification_runs", []))
    run_id = f"V{len(runs) + 1}"
    result = (
        "stale"
        if before["fingerprint"] != after["fingerprint"]
        else "environment_blocked"
        if environment_blocked
        else "failed"
        if timed_out or residual_processes_after_cleanup
        else "passed"
        if exit_code == 0
        else "failed"
    )
    run = {
        "id": run_id,
        "implementation_round": state.get("round"),
        "label": args.label.strip() if args.label else "",
        "command": redacted_command,
        "cwd": str(cwd),
        "started_at": started_at,
        "completed_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "execution_mode": "one-shot non-PTY",
        "timeout_seconds": args.timeout_seconds,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "residual_processes_detected": residual_processes_detected,
        "process_group_term_sent": term_sent,
        "process_group_kill_sent": kill_sent,
        "residual_processes_after_cleanup": residual_processes_after_cleanup,
        "stdout_sha256": output_digest(stdout),
        "stderr_sha256": output_digest(stderr),
        "before_snapshot_fingerprint": before["fingerprint"],
        "after_snapshot_fingerprint": after["fingerprint"],
        "result": result,
    }
    runs.append(run)
    state["verification_runs"] = runs
    state["verification_waiver"] = None
    save_state(record, state)
    record_verification_result(record, run)

    redacted_stdout = redact_test_output(
        stdout,
        sensitive_values=sensitive_command_values,
    )["summary"]
    redacted_stderr = redact_test_output(
        stderr,
        sensitive_values=sensitive_command_values,
    )["summary"]
    if redacted_stdout:
        sys.stdout.write(redacted_stdout)
        if not redacted_stdout.endswith("\n"):
            sys.stdout.write("\n")
    if redacted_stderr:
        sys.stderr.write(redacted_stderr)
        if not redacted_stderr.endswith("\n"):
            sys.stderr.write("\n")
    outcome = "OK" if result == "passed" else "BLOCKED" if result == "environment_blocked" else "FAIL"
    print(f"[{outcome}] {run_id} 验证结果: {result}")
    print(f"- 命令: {shlex.join(redacted_command)}")
    print(f"- 代码快照: {after['fingerprint']}")
    print(f"- stdout SHA256: {run['stdout_sha256']}")
    print(f"- stderr SHA256: {run['stderr_sha256']}")
    print(
        "- 进程回收: "
        f"timeout={timed_out}, residual_detected={residual_processes_detected}, "
        f"term={term_sent}, kill={kill_sent}, "
        f"residual_after_cleanup={residual_processes_after_cleanup}"
    )
    if result == "stale":
        print("- 验证命令改变了实现文件；请确认生成结果后重新执行验证")
    if result != "passed":
        raise SystemExit(exit_code or 1)


def command_complete(args: argparse.Namespace) -> None:
    record = Path(args.record).resolve()
    require_quick_boundary_ready(record)
    state = load_state(record)
    if record.name == "quick.md":
        expected_boundary = state.get("quick_boundary_fingerprint", "")
        current_boundary = quick_boundary_fingerprint(record)
        if not expected_boundary:
            raise SystemExit(
                "当前 quick 实现会话未锁定边界指纹；请执行 implementation-restart "
                "重新确认本轮边界"
            )
        if current_boundary != expected_boundary:
            raise SystemExit(
                "quick 边界在本实现轮次开始后发生变化；请执行 implementation-restart "
                "废弃旧轮次并以新边界重开"
            )
    if state.get("status") != "in_progress":
        raise SystemExit(
            "当前实现会话不是编码中状态；如有新修改，请重新执行 implementation-start"
        )
    precheck = state.get("precheck") or {}
    if (
        precheck.get("result") != "passed"
        or precheck.get("implementation_round") != state.get("round")
    ):
        raise SystemExit("当前实现轮次缺少已通过的编码前实现预检")
    precheck_errors = validator.validate_implementation_precheck(
        record,
        state.get("round", ""),
        state.get("risk_profile", "normal"),
        set(state.get("selected_tasks", [])) if record.name == "05-implementation-log.md" else None,
    )
    if precheck_errors:
        print("[FAIL] 编码前实现预检记录已失效：")
        for error in precheck_errors:
            print(f"- {error}")
        raise SystemExit(1)
    current_precheck_fingerprint = validator.implementation_precheck_fingerprint(record)
    if current_precheck_fingerprint != precheck.get("record_fingerprint"):
        raise SystemExit("编码前实现预检记录在通过后发生变化，必须重新开启实现轮次")

    current = current_snapshot(state)
    waiver_reason = (args.verification_waiver or "").strip()
    current_runs = [
        run
        for run in state.get("verification_runs", [])
        if run.get("implementation_round") == state.get("round")
        and run.get("after_snapshot_fingerprint") == current.get("fingerprint")
    ]
    latest_executed_by_verification: dict[str, dict] = {}
    environment_blocked_by_verification: dict[str, dict] = {}
    for run in current_runs:
        key = run.get("label") or json.dumps(
            run.get("command", []),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if run.get("result") == "environment_blocked":
            environment_blocked_by_verification[key] = run
        else:
            latest_executed_by_verification[key] = run
    fresh_passes = [
        run
        for run in latest_executed_by_verification.values()
        if run.get("result") == "passed"
    ]
    known_failures = [
        run
        for run in latest_executed_by_verification.values()
        if run.get("result") in {"failed", "stale"}
    ]
    environment_blocked_runs = [
        run
        for key, run in environment_blocked_by_verification.items()
        if key not in latest_executed_by_verification
    ]
    unknown_unresolved_runs = [
        run
        for run in latest_executed_by_verification.values()
        if run.get("result") not in {"failed", "stale", "environment_blocked"}
        and run.get("result") != "passed"
    ]
    unresolved_runs = known_failures + environment_blocked_runs + unknown_unresolved_runs
    if waiver_reason:
        if known_failures:
            details = ", ".join(
                f"{run.get('id', '?')}={run.get('result', '?')}"
                for run in known_failures
            )
            raise SystemExit(
                "当前代码快照存在已执行且失败或失效的验证，"
                f"--verification-waiver 不能覆盖已知失败: {details}"
            )
        if unknown_unresolved_runs:
            details = ", ".join(
                f"{run.get('id', '?')}={run.get('result', '?')}"
                for run in unknown_unresolved_runs
            )
            raise SystemExit(f"当前代码快照存在未知验证状态，不能豁免: {details}")
        if current_runs and not environment_blocked_runs:
            raise SystemExit(
                "当前代码快照不存在环境阻塞的未执行验证；"
                "已有验证全部通过时请移除 --verification-waiver"
            )
        state["verification_waiver"] = {
            "implementation_round": state.get("round"),
            "snapshot_fingerprint": current.get("fingerprint"),
            "reason": waiver_reason,
            "waived_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        record_verification_waiver(record, state.get("round", ""), waiver_reason)
    elif not fresh_passes or unresolved_runs:
        unresolved = (
            "；未恢复: " + ", ".join(run.get("id", "?") for run in unresolved_runs)
            if unresolved_runs
            else ""
        )
        raise SystemExit(
            "当前代码快照缺少成功验证。请执行 implementation-verify；"
            "确因环境阻塞时显式传入 --verification-waiver 并说明原因"
            + unresolved
        )
    else:
        state["verification_waiver"] = None

    cumulative_paths, by_repo = collect_changes(state)
    round_paths = current_round_paths(state, current)
    if not cumulative_paths:
        raise SystemExit("当前实现会话没有检测到代码或配置改动")
    if not round_paths:
        raise SystemExit("当前实现轮次没有新增、修改、删除或显式接管的实现文件")
    repo_labels = {repo_state["label"] for repo_state in state["repositories"]}
    errors = validate_record(
        record,
        round_paths,
        state["round"],
        repo_labels,
        set(state.get("selected_tasks", [])) if record.name == "05-implementation-log.md" else None,
    )
    if errors:
        print("[FAIL] 实现完成门禁未通过：")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    state["status"] = "completed"
    state["completed_at"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    state["actual_changes"] = by_repo
    state["round_actual_paths"] = sorted(round_paths)
    state["completed_task_ids"] = sorted(
        set(state.get("completed_task_ids", [])) | set(state.get("selected_tasks", [])),
        key=lambda value: (
            0,
            int(value[1:]),
        )
        if re.fullmatch(r"T\d+", value)
        else (1, value),
    )
    state["completion_snapshot"] = current
    save_state(record, state)
    update_record_line(record, "- 实现状态：", "已完成")
    update_record_line(record, "- 当前实现轮次：", state["round"])
    update_record_line(record, "- 最终差异指纹：", state["completion_snapshot"]["fingerprint"])
    print(f"[OK] 实现会话 {state['round']} 已完成")
    print(f"[OK] 最终差异指纹: {state['completion_snapshot']['fingerprint']}")
    print(f"[OK] 本轮登记 {len(round_paths)} 个文件；累计锁定 {len(cumulative_paths)} 个文件")


def command_status(args: argparse.Namespace) -> None:
    record = Path(args.record).resolve()
    state = load_state(record)
    print(f"实现轮次: {state.get('round')}")
    print(f"实现状态: {state.get('status')}")
    if state.get("status") != "completed" or not state.get("completion_snapshot"):
        raise SystemExit(1)

    current = current_snapshot(state)
    completed = state["completion_snapshot"]
    if current["fingerprint"] != completed.get("fingerprint"):
        print("[STALE] 实现完成后代码又发生变化，旧质量门禁和 Review 结论已失效")
        print(f"- 完成时: {completed.get('fingerprint')}")
        print(f"- 当前值: {current['fingerprint']}")
        raise SystemExit(1)
    print(f"[OK] 实现差异仍与完成快照一致: {current['fingerprint']}")
    verification_runs = [
        run
        for run in state.get("verification_runs", [])
        if run.get("implementation_round") == state.get("round")
    ]
    print(f"验证执行数: {len(verification_runs)}")
    if state.get("verification_waiver"):
        print(f"验证豁免: {state['verification_waiver'].get('reason')}")


def fingerprint_entries(entries: list[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for name, content in sorted(entries, key=lambda item: item[0]):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def review_artifact_fingerprint(
    record: Path,
    include_disposition_fields: bool = True,
) -> str:
    """只锁定 Review 工件，避免 quick 后续测试字段让 Review 自行失效。"""
    if record.name != "quick.md":
        entries = [
            (
                "06-code-review.md",
                (record.parent / "06-code-review.md").read_bytes()
                if (record.parent / "06-code-review.md").exists()
                else b"<missing>",
            )
        ]
        rounds_dir = record.parent / "review-rounds"
        if rounds_dir.exists():
            entries.extend(
                (path.relative_to(record.parent).as_posix(), path.read_bytes())
                for path in rounds_dir.glob("review-r*.md")
                if path.is_file()
            )
        return fingerprint_entries(entries)

    text = record.read_text(encoding="utf-8")
    if is_quick_v3_record(record, text):
        fields = review_record_field_prefixes(record, text)
        labels = [
            fields["result"],
            fields["implementation_round"],
            fields["fingerprint"],
            "- Light Review 简要结论：",
            "- Review 未关闭阻塞/必须修问题：",
            "- Review 剩余风险：",
        ]
        if include_disposition_fields:
            labels[1:1] = [
                fields["disposition"],
                fields["gate_satisfied"],
                fields["skip_reason"],
            ]
        values = "\n".join(
            f"{label}{validator.extract_line_value(text, label)}"
            for label in labels
        )
        section = (
            validator.extract_section(
                text,
                "### 5.1 Formal Review 两门复核（仅 formal）",
            )
            if validator.extract_line_value(
                text,
                fields["disposition"],
            ).strip()
            == "formal"
            else ""
        )
        return fingerprint_entries(
            [("quick-review", f"{values}\n{section}".encode("utf-8"))]
        )

    new_format = "### 5.1 Quick Review 两门复核" in text
    labels = (
        [
            "- Review 结论：",
            "- Review 方式：",
            "- Self-review 原因：",
            "- Review 对应实现轮次：",
            "- Review 对应差异指纹：",
            "- Review Gate A：",
            "- Review Gate B：",
            "- Review 未关闭阻塞/必须修问题：",
            "- Review 剩余风险：",
        ]
        if new_format
        else [
            "- Review 结论：",
            "- Review 对应实现轮次：",
            "- Review 对应差异指纹：",
            "- Review 覆盖文件：",
            "- Review 未关闭阻塞/必须修问题：",
            "- Review 剩余风险：",
            "- Review 关键逻辑注释证据：",
            "- Review SQL/DDL 规范证据：",
        ]
    )
    if include_disposition_fields:
        labels[1:1] = [
            "- Review disposition：",
            "- Review 门禁是否满足：",
            "- Review 跳过原因：",
        ]
    values = "\n".join(
        f"{label}{validator.extract_line_value(text, label)}"
        for label in labels
    )
    heading = (
        "### 5.1 Quick Review 两门复核"
        if new_format
        else "### 5.1 Quick Review 独立复核"
    )
    section = validator.extract_section(text, heading)
    return fingerprint_entries([("quick-review", f"{values}\n{section}".encode("utf-8"))])


def review_skip_decision_fingerprint(record: Path) -> str:
    """只锁定跳过决定，不要求伪造 Review 轮次或报告。"""
    entries: list[tuple[str, bytes]] = []
    for path in [record, record.parent / "06-code-review.md"]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        fields = review_record_field_prefixes(path, text)
        labels = [
            fields["result"],
            fields["disposition"],
            fields["gate_satisfied"],
            fields["skip_reason"],
            fields["implementation_round"],
            fields["fingerprint"],
        ]
        values = "\n".join(
            f"{label}{validator.extract_line_value(text, label)}"
            for label in labels
        )
        entries.append((path.name, values.encode("utf-8")))
    return fingerprint_entries(entries)


def review_input_fingerprint(
    record: Path,
    code_fingerprint: str,
    disposition: str = "formal",
) -> str:
    """锁定 Review 所依据的需求、方案、任务、契约与实现差异。"""
    entries: list[tuple[str, bytes]] = [
        ("code-fingerprint", code_fingerprint.encode("utf-8")),
    ]
    if disposition != "legacy":
        entries.append(("review-disposition", disposition.encode("utf-8")))
    if record.name == "quick.md":
        text = record.read_text(encoding="utf-8")
        for heading in [
            "## 1. 边界确认",
            "## 2. 升级 full 触发条件",
            "## 3. 实现摘要",
            "## 4. 验证记录",
        ]:
            entries.append((heading, validator.extract_section(text, heading).encode("utf-8")))
        schema_path = record.parent / "04-schema.sql"
        entries.append(
            ("04-schema.sql", schema_path.read_bytes() if schema_path.exists() else b"<missing>")
        )
        interface_dir = record.parent / "interface-details"
        if interface_dir.exists() and interface_dir.is_dir():
            detail_files = sorted(path for path in interface_dir.rglob("*") if path.is_file())
            if detail_files:
                entries.extend(
                    (path.relative_to(record.parent).as_posix(), path.read_bytes())
                    for path in detail_files
                )
            else:
                entries.append(("interface-details/", b"<empty>"))
        else:
            entries.append(("interface-details/", b"<missing>"))
        return fingerprint_entries(entries)

    input_names = (
        [
            "00-baseline.md",
            "02-design.md",
            "03-tasks.md",
            "sql-draft.sql",
            "04-schema.sql",
        ]
        if disposition == "light"
        else [
            "00-baseline.md",
            "01-research.md",
            "02-design.md",
            "03-tasks.md",
            "sql-draft.sql",
            "04-schema.sql",
        ]
    )
    for name in input_names:
        path = record.parent / name
        entries.append((name, path.read_bytes() if path.exists() else b"<missing>"))
    interface_dir = record.parent / "interface-details"
    if interface_dir.exists():
        entries.extend(
            (path.relative_to(record.parent).as_posix(), path.read_bytes())
            for path in interface_dir.rglob("*")
            if path.is_file()
        )
    implementation_text = record.read_text(encoding="utf-8")
    implementation_sections = "\n".join(
        validator.extract_section(implementation_text, heading)
        for heading in [
            "## 0. 编码前实现预检",
            "## 1. 实现记录索引",
            "## 2. 偏差与回写记录",
            "## 3. 验证记录",
            "## 4. 代码质量自检",
        ]
    )
    entries.append(("05-implementation-evidence", implementation_sections.encode("utf-8")))
    return fingerprint_entries(entries)


def optional_review_subject_fingerprint(record: Path, code_fingerprint: str) -> str:
    """锁定可选 Review 的需求口径与代码差异，不绑定 Review 报告本身。"""
    entries: list[tuple[str, bytes]] = [
        ("code-fingerprint", code_fingerprint.encode("utf-8")),
    ]
    if record.name == "quick.md":
        text = record.read_text(encoding="utf-8")
        for heading in [
            "## 1. 边界确认",
            "## 2. 升级 full 触发条件",
            "## 3. 实现摘要",
            "## 4. 验证记录",
        ]:
            entries.append(
                (heading, validator.extract_section(text, heading).encode("utf-8"))
            )
        return fingerprint_entries(entries)

    for name in [
        "00-baseline.md",
        "02-design.md",
        "03-tasks.md",
        "sql-draft.sql",
        "04-schema.sql",
    ]:
        path = record.parent / name
        entries.append((name, path.read_bytes() if path.exists() else b"<missing>"))
    interface_dir = record.parent / "interface-details"
    if interface_dir.exists():
        entries.extend(
            (path.relative_to(record.parent).as_posix(), path.read_bytes())
            for path in sorted(interface_dir.rglob("*"))
            if path.is_file()
        )
    return fingerprint_entries(entries)


def current_review_binding_errors(record: Path, state: dict, current: dict) -> list[str]:
    review = state.get("review") or {}
    normalize_legacy_review_state(state)
    errors: list[str] = []
    if review.get("model") == "optional":
        if review.get("implementation_round") != state.get("round"):
            errors.append("Review 对应实现轮次已变化")
        if review.get("fingerprint") != current.get("fingerprint"):
            errors.append("Review 对应代码差异已变化")
        expected_subject = optional_review_subject_fingerprint(
            record,
            current.get("fingerprint", ""),
        )
        if review.get("subject_fingerprint") != expected_subject:
            errors.append("Review 对应需求口径已变化")
        return errors
    if review.get("implementation_round") != state.get("round"):
        errors.append("Review 对应实现轮次已变化")
    if review.get("fingerprint") != current.get("fingerprint"):
        errors.append("Review 对应代码差异已变化")
    disposition = review_disposition(review)
    if disposition == "skipped":
        if review.get("result") != "skipped":
            errors.append("Review skipped disposition 与结果不一致")
        if review.get("decision_fingerprint") != review_skip_decision_fingerprint(record):
            errors.append("Review 跳过决定在登记后发生变化")
        return errors

    if int(state.get("schema_version", 1)) >= 6:
        expected_input = review_input_fingerprint(
            record,
            current.get("fingerprint", ""),
            disposition,
        )
        legacy_input = (
            review_input_fingerprint(
                record,
                current.get("fingerprint", ""),
                "legacy",
            )
            if int(state.get("schema_version", 1)) < STATE_SCHEMA_VERSION
            else ""
        )
        if review.get("input_fingerprint") not in {expected_input, legacy_input}:
            errors.append("Review 输入基线已变化")
        expected_artifact = review_artifact_fingerprint(record)
        legacy_artifact = (
            review_artifact_fingerprint(
                record,
                include_disposition_fields=False,
            )
            if int(state.get("schema_version", 1)) < STATE_SCHEMA_VERSION
            else ""
        )
        if review.get("artifact_fingerprint") not in {
            expected_artifact,
            legacy_artifact,
        }:
            errors.append("Review 报告在登记后发生变化")
    if review.get("reviewer_mode") is not None:
        mode = review.get("reviewer_mode")
        reason = review.get("self_review_reason") or ""
        if mode not in validator.REVIEWER_MODES:
            errors.append("Review 状态缺少有效评审方式")
        if record.name == "quick.md":
            errors.extend(
                validator.validate_review_provenance(
                    record.read_text(encoding="utf-8"),
                    "quick.md",
                    mode,
                    reason,
                )
            )
        else:
            latest = latest_review_round_file(record)
            if latest is None:
                errors.append("Review 状态缺少轮次工件")
            else:
                errors.extend(
                    validator.validate_review_provenance(
                        latest.read_text(encoding="utf-8"),
                        latest.name,
                        mode,
                        reason,
                    )
                )
            index_path = record.parent / "06-code-review.md"
            if index_path.exists():
                errors.extend(
                    validator.validate_review_provenance(
                        index_path.read_text(encoding="utf-8"),
                        "06-code-review.md",
                        mode,
                        reason,
                    )
                )
    return errors


LEGACY_REVIEWER_REASON = (
    "兼容旧 review-mark 调用：未提供 reviewer-mode，无法证明 fresh reviewer 上下文"
)
REVIEW_MODE_PLACEHOLDERS = {
    "",
    "未执行",
    "fresh-review / self-review",
    "未执行 / fresh-review / self-review",
}
REVIEW_REASON_PLACEHOLDERS = {
    "",
    "不适用 / fresh reviewer 不可用的具体原因",
}


def validate_reviewer_mode(mode: str | None, reason: str) -> tuple[str, str]:
    normalized_reason = reason.strip()
    if not mode:
        mode = "self-review"
        normalized_reason = normalized_reason or LEGACY_REVIEWER_REASON
    if mode == "fresh-review":
        if normalized_reason:
            raise SystemExit("fresh-review 不得传入 --self-review-reason")
        return mode, "不适用"
    if (
        normalized_reason in validator.SELF_REVIEW_PLACEHOLDERS
        or len(normalized_reason) < 8
    ):
        raise SystemExit(
            "self-review 必须用 --self-review-reason "
            "记录 fresh reviewer 不可用或启动失败的具体原因"
        )
    return mode, normalized_reason


LIGHT_SELF_REVIEW_REASON = "light-review 默认由当前上下文执行，不要求 fresh reviewer"


def resolve_review_provenance(
    disposition: str,
    mode: str | None,
    reason: str,
) -> tuple[str, str]:
    if disposition == "light" and not mode:
        return "self-review", LIGHT_SELF_REVIEW_REASON
    return validate_reviewer_mode(mode, reason)


def review_provenance_paths(record: Path) -> list[Path]:
    if record.name == "quick.md":
        return [record]
    latest = latest_review_round_file(record)
    if latest is None:
        raise SystemExit("Review 记录缺少轮次明细，不能登记评审方式")
    return [latest, record.parent / "06-code-review.md"]


def reject_conflicting_review_provenance(
    record: Path,
    mode: str,
    reason: str,
) -> None:
    """登记命令只补占位字段，不得覆盖 reviewer 已写明的来源。"""
    for path in review_provenance_paths(record):
        text = path.read_text(encoding="utf-8")
        current_mode = validator.extract_line_value(text, "- Review 方式：").strip()
        current_reason = validator.extract_line_value(
            text,
            "- Self-review 原因：",
        ).strip()
        if (
            current_mode not in REVIEW_MODE_PLACEHOLDERS
            and current_mode not in validator.REVIEWER_MODES
        ):
            raise SystemExit(f"{path.name} 已填写无法识别的 Review 方式")
        if current_mode in validator.REVIEWER_MODES and current_mode != mode:
            raise SystemExit(
                f"{path.name} 已记录 {current_mode}，"
                f"不能由 review-mark 改写为 {mode}"
            )
        reason_is_concrete = (
            current_reason not in REVIEW_REASON_PLACEHOLDERS
            and current_reason not in validator.SELF_REVIEW_PLACEHOLDERS
        )
        if mode == "fresh-review" and reason_is_concrete:
            raise SystemExit(
                f"{path.name} 已记录 self-review 具体原因，不能登记 fresh-review"
            )
        if mode == "self-review" and reason_is_concrete and current_reason != reason:
            raise SystemExit(
                f"{path.name} 已记录不同的 Self-review 原因，登记命令不得覆盖"
            )


def write_review_provenance(record: Path, mode: str, reason: str) -> None:
    if record.name == "quick.md":
        if is_quick_v3_record(record):
            return
        upsert_record_line_after(record, "- Review 方式：", mode, "- Review 结论：")
        upsert_record_line_after(
            record,
            "- Self-review 原因：",
            reason,
            "- Review 方式：",
        )
        return

    latest = latest_review_round_file(record)
    if latest is None:
        raise SystemExit("Review 记录缺少轮次明细，不能登记评审方式")
    upsert_record_line_after(latest, "- Review 方式：", mode, "- 评审范围：")
    upsert_record_line_after(
        latest,
        "- Self-review 原因：",
        reason,
        "- Review 方式：",
    )
    index_path = record.parent / "06-code-review.md"
    upsert_record_line_after(
        index_path,
        "- Review 方式：",
        mode,
        "- 需要回到实现阶段的问题：",
    )
    upsert_record_line_after(
        index_path,
        "- Self-review 原因：",
        reason,
        "- Review 方式：",
    )


def write_review_disposition(record: Path, disposition: str) -> None:
    ensure_review_record_fields(record)
    fields = review_record_field_prefixes(record)
    update_record_line(record, fields["disposition"], disposition)
    if record.name == "quick.md":
        return

    latest = latest_review_round_file(record)
    if latest is not None:
        upsert_record_line_after(
            latest,
            "- Review disposition：",
            disposition,
            "- 评审范围：",
        )
    index = record.parent / "06-code-review.md"
    if index.exists():
        upsert_record_line_after(
            index,
            "- Review disposition：",
            disposition,
            "- 当前结论：",
        )


def validate_light_review_evidence(
    record: Path,
    result: str,
    implementation_round: str,
    fingerprint: str,
) -> list[str]:
    """Light Review 只校验逻辑、代码和文档结论，不强制全量 manifest。"""
    expected = {
        "passed": "通过",
        "needs_changes": "需修改",
        "blocked": "阻塞",
    }[result]
    errors: list[str] = []
    if record.name == "quick.md":
        text = record.read_text(encoding="utf-8")
        if is_quick_v3_record(record, text):
            fields = review_record_field_prefixes(record, text)
            if validator.extract_line_value(
                text,
                fields["disposition"],
            ).strip() != "light":
                errors.append("quick.md v3 Review 处置必须为 light")
            if result == "passed":
                errors.extend(
                    validator.validate_quick_review_evidence(
                        record,
                        set(),
                    )
                )
            else:
                errors.extend(
                    validator.validate_quick_review_nonpass(
                        record,
                        result,
                        set(),
                    )
                )
            return errors
        for label in ["- Review Gate A：", "- Review Gate B："]:
            value = validator.extract_line_value(text, label)
            if result == "passed" and value != "通过":
                errors.append(f"quick light Review 通过时 {label}必须为通过")
        return errors

    latest = latest_review_round_file(record)
    if latest is None:
        return ["light Review 缺少 review-rNN.md 明细"]
    text = latest.read_text(encoding="utf-8")
    round_id = validator.extract_line_value(text, "- 轮次：")
    if not re.fullmatch(r"R\d+", round_id):
        errors.append(f"{latest.name} 缺少有效 Review 轮次")
    if validator.extract_line_value(text, "- Review disposition：") != "light":
        errors.append(f"{latest.name} Review disposition 必须为 light")
    if validator.extract_line_value(text, "- 对应实现轮次：") != implementation_round:
        errors.append(f"{latest.name} 对应实现轮次不一致")
    if validator.extract_line_value(text, "- 实现差异指纹：") != fingerprint:
        errors.append(f"{latest.name} 实现差异指纹不一致")
    if validator.extract_line_value(text, "- 结论：") != expected:
        errors.append(f"{latest.name} 结论必须为“{expected}”")

    light_labels = [
        "- 业务逻辑结论：",
        "- 代码质量结论：",
        "- 文档一致性结论：",
        "- 契约 / SQL 结论：",
        "- 异常 / 日志 / Trace 结论：",
    ]
    if any(label in text for label in light_labels):
        for label in light_labels:
            value = validator.extract_line_value(text, label)
            can_be_not_applicable = label in {
                "- 契约 / SQL 结论：",
                "- 异常 / 日志 / Trace 结论：",
            }
            accepted = value == "通过" or (
                can_be_not_applicable
                and value.startswith("不涉及：")
                and len(value.removeprefix("不涉及：").strip()) >= 4
            )
            if result == "passed" and not accepted:
                errors.append(
                    f"{latest.name} 通过时 {label}必须为通过或写明不涉及的具体原因"
                )
            elif value in validator.EMPTY_VALUES:
                errors.append(f"{latest.name} 缺少 {label}")
    else:
        gate_a = validator.extract_line_value(text, "- Gate A 结论：")
        gate_b = validator.extract_line_value(text, "- Gate B 结论：")
        if result == "passed" and (gate_a != "通过" or gate_b != "通过"):
            errors.append(f"{latest.name} light Review 通过时 Gate A/B 必须为通过")

    index = record.parent / "06-code-review.md"
    if index.exists():
        index_text = index.read_text(encoding="utf-8")
        if validator.extract_line_value(index_text, "- Review disposition：") != "light":
            errors.append("06-code-review.md Review disposition 必须为 light")
        if validator.extract_line_value(index_text, "- 当前结论：") != expected:
            errors.append(f"06-code-review.md 当前结论必须为“{expected}”")
    return errors


def command_review_mark_legacy(args: argparse.Namespace) -> None:
    record = Path(args.record).resolve()
    requested_disposition = getattr(args, "disposition", None)
    if requested_disposition:
        disposition = requested_disposition
    elif getattr(args, "reviewer_mode", None):
        # 旧调用显式 fresh/self 时保持 formal 语义。
        disposition = "formal"
    else:
        record_text = record.read_text(encoding="utf-8")
        disposition = (
            "light"
            if (
                record.name == "quick.md"
                and validator.quick_schema_version(record_text) >= 3
            )
            or (
                record.name == "05-implementation-log.md"
                and validator.implementation_schema_version(record_text) >= 2
            )
            else "formal"
        )
    if disposition not in {"light", "formal"}:
        raise SystemExit("review-mark 的 --disposition 只允许 light 或 formal")
    reviewer_mode, self_review_reason = resolve_review_provenance(
        disposition,
        getattr(args, "reviewer_mode", None),
        getattr(args, "self_review_reason", None) or "",
    )
    state = load_state(record)
    if state.get("status") != "completed" or not state.get("completion_snapshot"):
        raise SystemExit("实现会话尚未完成，不能登记 Review 结论")
    current = current_snapshot(state)
    completed = state["completion_snapshot"]
    if current["fingerprint"] != completed.get("fingerprint"):
        raise SystemExit("代码已偏离实现完成快照，不能登记 Review 结论")
    if record.name == "05-implementation-log.md" and args.result == "passed":
        planned_tasks = validator.implementation_task_ids(record.parent / "03-tasks.md")
        missing_tasks = sorted(
            planned_tasks - set(state.get("completed_task_ids", [])),
            key=lambda value: int(value[1:]),
        )
        if missing_tasks:
            raise SystemExit(
                "仍有未完成的编码任务，不能登记 Review 通过: "
                + ", ".join(missing_tasks)
            )
    write_review_disposition(record, disposition)
    review_fields = review_record_field_prefixes(record)
    result_label = {
        "passed": "通过",
        "needs_changes": "需修改",
        "blocked": "阻塞",
    }[args.result]
    if is_quick_v3_record(record):
        # quick v3 的状态字段由登记命令维护，用户只需填写简洁复核证据。
        update_record_line(record, review_fields["result"], result_label)
        update_record_line(
            record,
            review_fields["gate_satisfied"],
            "是" if args.result == "passed" else "否",
        )
        update_record_line(record, review_fields["skip_reason"], "不涉及")
    input_fingerprint = review_input_fingerprint(
        record,
        current["fingerprint"],
        disposition,
    )
    reject_conflicting_review_provenance(
        record,
        reviewer_mode,
        self_review_reason,
    )
    write_review_provenance(record, reviewer_mode, self_review_reason)
    if record.name != "quick.md":
        latest_round_file = latest_review_round_file(record)
        if latest_round_file is None:
            raise SystemExit("Review 记录缺少轮次明细，不能登记结论")
        update_record_line(latest_round_file, "- Review 输入指纹：", input_fingerprint)
        index_path = record.parent / "06-code-review.md"
        if any(
            line.strip().startswith("- Review 输入指纹：")
            for line in index_path.read_text(encoding="utf-8").splitlines()
        ):
            update_record_line(index_path, "- Review 输入指纹：", input_fingerprint)
    repositories = current.get("repositories", [])
    multi_repo = len(repositories) > 1
    actual_paths = {
        f"{repository['label']}/{item['path']}" if multi_repo else item["path"]
        for repository in repositories
        for item in repository.get("files", [])
    }
    if disposition == "light":
        review_errors = validate_light_review_evidence(
            record,
            args.result,
            state.get("round", ""),
            current["fingerprint"],
        )
        if review_errors:
            print("[FAIL] Light Review 最小门禁未通过：")
            for error in review_errors:
                print(f"- {error}")
            raise SystemExit(1)
    elif args.result == "passed":
        if record.name == "quick.md":
            review_errors = validator.validate_quick_review_evidence(
                record,
                actual_paths,
                expected_reviewer_mode=reviewer_mode,
                expected_self_review_reason=self_review_reason,
            )
        else:
            review_errors = validator.validate_code_review_completion(
                record.parent / "06-code-review.md",
                record.parent / "review-rounds",
                actual_paths=actual_paths,
                expected_implementation_round=state.get("round"),
                expected_fingerprint=current["fingerprint"],
                expected_input_fingerprint=input_fingerprint,
                expected_reviewer_mode=reviewer_mode,
                expected_self_review_reason=self_review_reason,
            )
        if review_errors:
            print("[FAIL] Review 通过门禁未通过：")
            for error in review_errors:
                print(f"- {error}")
            raise SystemExit(1)
    else:
        if record.name == "quick.md":
            review_errors = validator.validate_quick_review_nonpass(
                record,
                args.result,
                actual_paths,
                expected_reviewer_mode=reviewer_mode,
                expected_self_review_reason=self_review_reason,
            )
        else:
            review_errors = validator.validate_code_review_nonpass(
                record.parent / "06-code-review.md",
                record.parent / "review-rounds",
                result=args.result,
                actual_paths=actual_paths,
                expected_implementation_round=state.get("round", ""),
                expected_fingerprint=current["fingerprint"],
                expected_input_fingerprint=input_fingerprint,
                expected_reviewer_mode=reviewer_mode,
                expected_self_review_reason=self_review_reason,
            )
        if review_errors:
            print("[FAIL] Review 非通过结论缺少最小证据：")
            for error in review_errors:
                print(f"- {error}")
            raise SystemExit(1)
    update_record_line(record, review_fields["result"], result_label)
    update_record_line(
        record,
        review_fields["gate_satisfied"],
        "是" if args.result == "passed" else "否",
    )
    update_record_line(
        record,
        review_fields["skip_reason"],
        "不涉及" if is_quick_v3_record(record) else "",
    )
    update_record_line(
        record,
        review_fields["implementation_round"],
        state.get("round", ""),
    )
    update_record_line(record, review_fields["fingerprint"], current["fingerprint"])
    review_round = "quick" if record.name == "quick.md" else latest_review_round(record)
    if not review_round:
        raise SystemExit("Review 记录缺少有效轮次，不能登记结论")
    state["review"] = {
        "implementation_round": state.get("round"),
        "fingerprint": current["fingerprint"],
        "review_round": review_round,
        "input_fingerprint": input_fingerprint,
        "artifact_fingerprint": review_artifact_fingerprint(record),
        "disposition": disposition,
        "gate_satisfied": args.result == "passed",
        "passed": args.result == "passed",
        "reviewer_mode": reviewer_mode,
        "self_review_reason": (
            self_review_reason if reviewer_mode == "self-review" else None
        ),
        "result": args.result,
        "reviewed_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    state["test"] = None
    save_state(record, state)
    print(f"[OK] 已登记 {state.get('round')} Review 结论: {args.result}")
    print(f"[OK] Review disposition: {disposition}")
    print(f"[OK] Review 方式: {reviewer_mode}")
    if reviewer_mode == "self-review":
        print(f"[SELF-REVIEW] 本轮不是独立评审: {self_review_reason}")
    print(f"[OK] Review 差异指纹: {current['fingerprint']}")


def sync_optional_review_status(record: Path, result: str) -> None:
    if record.name == "quick.md":
        return
    meta_path = record.parent / "meta.json"
    if not meta_path.exists():
        return
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["review_status"] = result
    meta.pop("review_disposition", None)
    gates = meta.setdefault("gates", {})
    gates.pop("review_passed", None)
    gates.pop("review_gate_satisfied", None)
    if meta.get("current_phase") == "代码检查":
        meta["current_status"] = {
            "passed": "已检查",
            "needs_changes": "发现问题",
            "blocked": "检查阻塞",
        }[result]
    atomic_write_text(meta_path, json.dumps(meta, ensure_ascii=False, indent=2) + "\n")


def command_optional_review_mark(args: argparse.Namespace) -> None:
    """登记单一可选 Review；结论只供用户参考，不形成测试门禁。"""
    record = Path(args.record).resolve()
    state = load_state(record)
    if state.get("status") != "completed" or not state.get("completion_snapshot"):
        raise SystemExit("实现会话尚未完成，不能登记 Review 结论")
    current = current_snapshot(state)
    if current.get("fingerprint") != state["completion_snapshot"].get("fingerprint"):
        raise SystemExit("代码已偏离实现完成快照，不能登记 Review 结论")

    result_label = {
        "passed": "通过",
        "needs_changes": "需修改",
        "blocked": "阻塞",
    }[args.result]
    report: Path | None = None
    if record.name != "quick.md":
        report = record.parent / "06-code-review.md"
        if not report.exists() or not is_optional_review_record(report):
            raise SystemExit("缺少新版 06-code-review.md；请先执行 to-review")
    fields = review_record_field_prefixes(record)
    update_record_line(record, fields["status"], "已执行")
    update_record_line(record, fields["result"], result_label)
    update_record_line(record, fields["implementation_round"], state.get("round", ""))
    update_record_line(record, fields["fingerprint"], current["fingerprint"])

    if report is not None:
        update_record_line(
            report,
            "- 检查时间：",
            dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        update_record_line(report, "- 对应实现轮次：", state.get("round", ""))
        update_record_line(report, "- 实现差异指纹：", current["fingerprint"])
        update_record_line(report, "- 结论：", result_label)

    review_errors = validator.validate_optional_review(
        record,
        args.result,
        state.get("round", ""),
        current["fingerprint"],
    )
    if review_errors:
        print("[FAIL] 可选 Review 记录未收口：")
        for error in review_errors:
            print(f"- {error}")
        raise SystemExit(1)

    state["review"] = {
        "model": "optional",
        "result": args.result,
        "implementation_round": state.get("round"),
        "fingerprint": current["fingerprint"],
        "subject_fingerprint": optional_review_subject_fingerprint(
            record,
            current["fingerprint"],
        ),
        "reviewed_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    save_state(record, state)
    sync_optional_review_status(record, args.result)
    print(f"[OK] 已登记可选 Review 结论: {args.result}")
    print("[NOTICE] Review 结论不构成测试门禁，后续动作由用户决定")


def command_review_mark(args: argparse.Namespace) -> None:
    record = Path(args.record).resolve()
    if is_optional_review_record(record):
        command_optional_review_mark(args)
        return
    command_review_mark_legacy(args)


def command_review_skip(args: argparse.Namespace) -> None:
    """记录用户跳过 Review；解除门禁但绝不伪装为 Review 通过。"""
    record = Path(args.record).resolve()
    if is_optional_review_record(record):
        raise SystemExit("新版 Review 本来就是可选的，未执行时无需登记 review-skip")
    reason = (args.reason or "").strip()
    if not reason:
        raise SystemExit("review-skip 必须提供用户明确跳过 Review 的 --reason")
    state = load_state(record)
    if state.get("status") != "completed" or not state.get("completion_snapshot"):
        raise SystemExit("实现会话尚未完成，不能跳过 Review")
    current = current_snapshot(state)
    if current.get("fingerprint") != state["completion_snapshot"].get("fingerprint"):
        raise SystemExit("代码已偏离实现完成快照，不能登记 Review 跳过决定")

    ensure_review_record_fields(record)
    review_fields = review_record_field_prefixes(record)
    quick_v3 = is_quick_v3_record(record)
    update_record_line(
        record,
        review_fields["result"],
        "已跳过" if quick_v3 else "已跳过（未评审）",
    )
    update_record_line(record, review_fields["disposition"], "skipped")
    update_record_line(record, review_fields["gate_satisfied"], "是")
    update_record_line(record, review_fields["skip_reason"], reason)
    update_record_line(
        record,
        review_fields["implementation_round"],
        state.get("round", ""),
    )
    update_record_line(record, review_fields["fingerprint"], current["fingerprint"])
    if record.name == "quick.md":
        if not quick_v3 and "- Review 方式：" in record.read_text(encoding="utf-8"):
            update_record_line(record, "- Review 方式：", "未执行")
    else:
        index = record.parent / "06-code-review.md"
        if index.exists():
            upsert_record_line_after(
                index,
                "- Review disposition：",
                "skipped",
                "- 当前结论：",
            )
            update_record_line(index, "- 当前结论：", "已跳过（未评审）")
            if "- Review 门禁是否满足：" in index.read_text(encoding="utf-8"):
                update_record_line(index, "- Review 门禁是否满足：", "是")
            update_record_line(
                index,
                "- 是否允许进入测试验证：",
                "是（用户明确跳过 Review，未评审）",
            )
            update_record_line(index, "- 需要回到实现阶段的问题：", "无")
            upsert_record_line_after(
                index,
                "- Review 跳过原因：",
                reason,
                "- Self-review 原因：",
            )
            update_record_line(index, "- 对应实现轮次：", state.get("round", ""))
            update_record_line(index, "- 实现差异指纹：", current["fingerprint"])

    state["review"] = {
        "implementation_round": state.get("round"),
        "fingerprint": current["fingerprint"],
        "review_round": "skipped",
        "disposition": "skipped",
        "result": "skipped",
        "gate_satisfied": True,
        "passed": False,
        "skip_reason": reason,
        "skipped_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    state["review"]["decision_fingerprint"] = review_skip_decision_fingerprint(
        record
    )
    state["test"] = None
    save_state(record, state)
    print(f"[OK] 已登记 {state.get('round')} Review disposition: skipped")
    print("[NOTICE] Review 门禁已解除，但本轮未经过 Review，不能表述为 Review 通过")
    print(f"- 跳过原因: {reason}")


def command_review_status(args: argparse.Namespace) -> None:
    record = Path(args.record).resolve()
    state = load_state(record)
    review = state.get("review") or {}
    if not review:
        print("[NOT RUN] 当前实现轮次未执行 Review；Review 可选，不影响测试")
        return
    current = current_snapshot(state)
    binding_errors = current_review_binding_errors(record, state, current)
    if binding_errors:
        print("[STALE] Review 结论已经失效：")
        for error in binding_errors:
            print(f"- {error}")
        raise SystemExit(1)
    if review.get("model") == "optional":
        print(f"对应实现轮次: {review.get('implementation_round')}")
        print(f"Review 结论: {review.get('result')}")
        print(f"Review 差异指纹: {review.get('fingerprint')}")
        print("Review 类型: 可选检查（不构成测试门禁）")
        if getattr(args, "require_passed", False) and review.get("result") != "passed":
            raise SystemExit(1)
        return
    print(f"Review 轮次: {review.get('review_round')}")
    print(f"对应实现轮次: {review.get('implementation_round')}")
    print(f"Review 结论: {review.get('result')}")
    print(f"Review 差异指纹: {review.get('fingerprint')}")
    print(f"Review 输入指纹: {review.get('input_fingerprint')}")
    print(f"Review 工件指纹: {review.get('artifact_fingerprint')}")
    disposition = review_disposition(review)
    print(f"Review disposition: {disposition}")
    print(f"Review 门禁是否满足: {'是' if review_gate_satisfied(review) else '否'}")
    print(f"Review 是否通过: {'是' if review_passed(review) else '否'}")
    if disposition == "skipped":
        print("[SKIPPED] 用户已跳过 Review，本轮未评审")
        print(f"跳过原因: {review.get('skip_reason')}")
    reviewer_mode = review.get("reviewer_mode") or "legacy-unknown"
    if disposition != "skipped":
        print(f"Review 方式: {reviewer_mode}")
    if disposition != "skipped" and reviewer_mode == "self-review":
        print("[SELF-REVIEW] 本轮不是独立评审")
        print(f"Self-review 原因: {review.get('self_review_reason')}")
    elif disposition != "skipped" and reviewer_mode == "legacy-unknown":
        print("[NOTICE] 旧 Review 未记录评审方式，不得视为独立评审")
    if getattr(args, "require_passed", False) and not review_passed(review):
        raise SystemExit(1)
    if (
        getattr(args, "require_gate_satisfied", False)
        and not review_gate_satisfied(review)
    ):
        raise SystemExit(1)


def test_artifact_fingerprint(record: Path) -> str:
    """锁定实际测试记录，避免登记通过后继续修改报告却沿用旧结论。"""
    if record.name == "quick.md":
        text = record.read_text(encoding="utf-8")
        test_values = "\n".join(
            f"{prefix}{validator.extract_line_value(text, prefix)}"
            for prefix in [
                "- 测试结论：",
                "- 测试对应实现轮次：",
                "- 测试对应差异指纹：",
                "- 最终结论：",
                "- 后续动作：",
            ]
        )
        entries = [
            (
                "quick-test",
                (
                    test_values
                    + "\n"
                    + validator.extract_section(text, "### 5.2 Quick 测试场景")
                    + "\n"
                    + validator.extract_section(text, "### 5.3 Quick 命令证据")
                ).encode("utf-8"),
            )
        ]
        reports_dir = record.parent / "reports"
        if reports_dir.exists():
            entries.extend(
                (
                    path.relative_to(record.parent).as_posix(),
                    path.read_bytes(),
                )
                for path in sorted(reports_dir.rglob("*"))
                if path.is_file()
            )
    else:
        paths = [record.parent / "07-test-report.md"]
        rounds_dir = record.parent / "test-rounds"
        paths.extend(sorted(rounds_dir.glob("test-r*.md")) if rounds_dir.exists() else [])
        reports_dir = record.parent / "reports"
        if reports_dir.exists():
            paths.extend(sorted(path for path in reports_dir.rglob("*") if path.is_file()))
        entries = [
            (
                path.relative_to(record.parent).as_posix(),
                path.read_bytes() if path.exists() else b"<missing>",
            )
            for path in paths
        ]
    return fingerprint_entries(entries)


def latest_review_round_file(record: Path) -> Path | None:
    if record.name == "quick.md":
        return None
    rounds_dir = record.parent / "review-rounds"
    candidates: list[tuple[int, Path]] = []
    for path in rounds_dir.glob("review-r*.md") if rounds_dir.exists() else []:
        match = re.fullmatch(r"review-r(\d+)\.md", path.name)
        if match:
            candidates.append((int(match.group(1)), path))
    if not candidates:
        return None
    _, latest = max(candidates, key=lambda item: (item[0], item[1].name))
    return latest


def latest_review_round(record: Path) -> str:
    latest = latest_review_round_file(record)
    if latest is None:
        return ""
    return validator.extract_line_value(latest.read_text(encoding="utf-8"), "- 轮次：")


def latest_test_round_file(record: Path) -> Path | None:
    if record.name == "quick.md":
        return record
    rounds_dir = record.parent / "test-rounds"
    candidates: list[tuple[int, Path]] = []
    for path in rounds_dir.glob("test-r*.md") if rounds_dir.exists() else []:
        match = re.fullmatch(r"test-r(\d+)\.md", path.name)
        if match:
            candidates.append((int(match.group(1)), path))
    if not candidates:
        return None
    _, latest = max(candidates, key=lambda item: (item[0], item[1].name))
    return latest


def test_round_context(record: Path, requested_round: str) -> tuple[Path, str, str]:
    latest = latest_test_round_file(record)
    if latest is None:
        raise SystemExit("缺少当前测试轮次；请先按模板创建 test-rNN.md")
    if record.name == "quick.md":
        if requested_round != "quick":
            raise SystemExit("quick 测试的 --round 必须为 quick")
        return latest, "quick", "quick"

    text = latest.read_text(encoding="utf-8")
    round_id = validator.extract_line_value(text, "- 轮次：")
    mode = validator.extract_line_value(text, "- 测试模式：")
    if requested_round != round_id:
        raise SystemExit(
            f"--round 必须绑定当前最新测试轮次: {round_id or '未填写'}"
        )
    if not re.fullmatch(r"T\d+", round_id):
        raise SystemExit("当前测试轮次缺少有效 Txx")
    if mode not in {"formal-gate", "run-only", "triage"}:
        raise SystemExit("当前测试轮次缺少有效测试模式")
    return latest, round_id, mode


def test_scenario_plan(
    record: Path,
    round_file: Path,
    scenario_id: str,
) -> tuple[dict[str, str], str]:
    text = round_file.read_text(encoding="utf-8")
    heading = (
        "### 5.2 Quick 测试场景"
        if record.name == "quick.md"
        else "## 4. 测试场景清单"
    )
    headers, rows = validator.extract_first_table(
        validator.extract_section(text, heading)
    )
    matching = [
        row
        for row in rows
        if validator.table_cell(headers, row, "场景ID") == scenario_id
    ]
    if len(matching) != 1:
        raise SystemExit(f"当前测试轮次必须且只能有一个场景 {scenario_id}")
    row = matching[0]
    fields = {
        header: validator.table_cell(headers, row, header)
        for header in [
            "场景ID",
            "来源依据",
            "业务场景",
            "级别",
            "前置条件",
            "操作与测试数据",
            "预期结果",
            "Effect",
        ]
    }
    for header in [
        "来源依据",
        "业务场景",
        "前置条件",
        "操作与测试数据",
        "预期结果",
    ]:
        if fields[header] in validator.EMPTY_VALUES:
            raise SystemExit(f"{scenario_id} 执行前必须填写{header}")
    if fields["级别"] not in {"关键", "一般"}:
        raise SystemExit(f"{scenario_id} 执行前必须明确场景级别")
    if fields["Effect"] not in validator.TEST_EFFECTS:
        raise SystemExit(f"{scenario_id} 执行前必须明确合法 Effect")
    plan_fingerprint = fingerprint_entries(
        [
            (
                scenario_id,
                json.dumps(
                    fields,
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8"),
            )
        ]
    )
    return fields, plan_fingerprint


SENSITIVE_ARG_FLAGS = {
    "--authorization",
    "--cookie",
    "--password",
    "--passwd",
    "--secret",
    "--token",
    "--api-key",
    "-p",
}


def redact_sensitive_text(value: str) -> str:
    """统一脱敏命令参数、输出和授权说明中的常见凭证表达。"""
    sensitive_names = (
        r"authorization|proxy-authorization|cookie|set-cookie|token|"
        r"access[_-]?token|password|passwd|secret|api[_-]?key"
    )
    value = re.sub(
        rf"""(?i)(["'](?:{sensitive_names})["']\s*:\s*)["'][^"'\r\n]*["']""",
        r'\1"<redacted>"',
        value,
    )
    value = re.sub(
        r"(?i)\b(authorization|proxy-authorization|cookie|set-cookie)"
        r"(\s*[:=]\s*)[^\r\n'\"]*",
        r"\1\2<redacted>",
        value,
    )
    value = re.sub(
        r"(?i)\b(token|access[_-]?token|password|passwd|cookie|secret|api[_-]?key)"
        r"(\s*[:=]\s*)[^\s,;&]+",
        r"\1\2<redacted>",
        value,
    )
    return re.sub(
        r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+",
        "Bearer <redacted>",
        value,
    )


def redact_test_argv(command: list[str]) -> list[str]:
    redacted: list[str] = []
    hide_next = False
    for value in command:
        if hide_next:
            redacted.append("<redacted>")
            hide_next = False
            continue
        lowered = value.lower()
        if lowered in SENSITIVE_ARG_FLAGS:
            redacted.append(value)
            hide_next = True
            continue
        matched = False
        for flag in SENSITIVE_ARG_FLAGS:
            prefix = f"{flag}="
            if lowered.startswith(prefix):
                redacted.append(f"{value[:len(prefix)]}<redacted>")
                matched = True
                break
        if matched:
            continue
        redacted.append(redact_sensitive_text(value))
    return redacted


def sensitive_test_argv_values(command: list[str]) -> set[str]:
    """提取已知敏感参数值，避免程序回显 argv 时重新泄露。"""
    secrets: set[str] = set()
    hide_next = False
    for value in command:
        if hide_next:
            if value:
                secrets.add(value)
            hide_next = False
            continue
        lowered = value.lower()
        if lowered in SENSITIVE_ARG_FLAGS:
            hide_next = True
            continue
        for flag in SENSITIVE_ARG_FLAGS:
            prefix = f"{flag}="
            if lowered.startswith(prefix):
                secret = value[len(prefix):]
                if secret:
                    secrets.add(secret)
                break
        else:
            if redact_sensitive_text(value) != value:
                secrets.add(value)
    return secrets


def redact_test_output(
    value: bytes,
    limit: int = 12000,
    sensitive_values: set[str] | None = None,
) -> dict:
    decoded = redact_sensitive_text(value.decode("utf-8", errors="replace"))
    for secret in sorted(sensitive_values or set(), key=len, reverse=True):
        if secret:
            decoded = decoded.replace(secret, "<redacted>")
    truncated = len(decoded) > limit
    if truncated:
        half = limit // 2
        summary = decoded[:half] + "\n...<truncated>...\n" + decoded[-half:]
    else:
        summary = decoded
    return {
        "bytes": len(value),
        "sha256": output_digest(value),
        "summary": summary,
        "truncated": truncated,
    }


def ensure_quick_test_command_section(record: Path) -> None:
    text = record.read_text(encoding="utf-8")
    heading = "### 5.3 Quick 命令证据"
    if heading in text:
        return
    block = (
        "\n"
        f"{heading}\n\n"
        "> 仅由 `test-run` 写入；命令退出码不自动替代业务场景结论。\n\n"
        "| 执行ID | 场景ID | 时间 | 命令 / cwd / 环境 | Effect | "
        "机器证据 | SHA-256 | 结论 |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| Exx | TSxx |  |  | read-only |  |  | PASS / FAIL / BLOCKED |\n"
    )
    atomic_write_text(record, text.rstrip() + "\n" + block)


def normalize_test_execution_placeholder(record: Path, heading: str) -> None:
    lines = record.read_text(encoding="utf-8").splitlines()
    in_section = False
    for index, line in enumerate(lines):
        if line.strip() == heading:
            in_section = True
            continue
        if in_section and line.strip().startswith("#"):
            break
        if not in_section or not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or cells[0] not in {"E1", "Exx"}:
            continue
        if cells[0] == "E1" and len(cells) >= 5 and cells[2] in validator.EMPTY_VALUES:
            cells[0] = "Exx"
            lines[index] = "| " + " | ".join(cells) + " |"
            atomic_write_text(record, "\n".join(lines) + "\n")
        return


def next_test_execution_id(state: dict, round_id: str) -> str:
    numbers = [
        int(match.group(1))
        for run in state.get("test_runs", [])
        if run.get("test_round") == round_id
        for match in [re.fullmatch(r"E(\d+)", str(run.get("execution_id", "")))]
        if match
    ]
    return f"E{max(numbers, default=0) + 1}"


def ensure_evidence_path_safe(feature_dir: Path, candidate: Path) -> None:
    """证据必须留在 feature 内，且路径任一层都不能借 symlink 跳出。"""
    lexical_root = feature_dir.absolute()
    lexical_candidate = candidate.absolute()
    root = feature_dir.resolve()
    try:
        relative = lexical_candidate.relative_to(lexical_root)
    except ValueError as error:
        raise SystemExit("机器证据路径越出当前 feature") from error
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise SystemExit("机器证据路径包含不安全的相对路径")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise SystemExit(f"机器证据路径不得经过符号链接: {current}")


def append_test_execution_record(
    record: Path,
    round_file: Path,
    run: dict,
) -> None:
    command_display = shlex.join(run["argv"])
    result = {
        "passed": "PASS",
        "failed": "FAIL",
        "blocked": "BLOCKED",
        "stale": "BLOCKED",
    }[run["result"]]
    if record.name == "quick.md":
        ensure_quick_test_command_section(record)
        normalize_test_execution_placeholder(record, "### 5.3 Quick 命令证据")
        append_table_row(
            record,
            "### 5.3 Quick 命令证据",
            ("执行ID", "场景ID", "时间", "机器证据", "SHA-256", "结论"),
            [
                run["execution_id"],
                run["scenario_id"],
                run["completed_at"],
                f"`{command_display}`；{run['cwd']}；{run['environment']}",
                run["effect"],
                f"`{run['evidence_path']}`",
                run["evidence_sha256"],
                result,
            ],
            placeholder_round="Exx",
        )
        return

    normalize_test_execution_placeholder(round_file, "## 5. 执行记录")
    append_table_row(
        round_file,
        "## 5. 执行记录",
        ("执行ID", "场景ID", "时间", "命令/接口/观察点", "结论"),
        [
            run["execution_id"],
            run["scenario_id"],
            run["completed_at"],
            f"{run['cwd']} / {run['environment']}",
            f"`command: {command_display}`",
            f"exit={run['exit_code']}",
            (
                f"机器执行；stdout={run['stdout']['sha256'][:12]}；"
                f"stderr={run['stderr']['sha256'][:12]}"
            ),
            run["effect"],
            f"`{run['evidence_path']}`",
            run["evidence_sha256"],
            result,
        ],
        placeholder_round="Exx",
    )


def record_test_process_execution(
    record: Path,
    round_file: Path,
    run: dict,
) -> None:
    if record.name == "quick.md":
        return
    text = round_file.read_text(encoding="utf-8")
    values = {
        "- 命令执行方式：": "one-shot non-PTY",
        "- 命令超时秒数：": str(run["timeout_seconds"]),
        "- 残留进程检查：": (
            "仍有残留"
            if run["residual_processes_after_cleanup"]
            else "检测到同进程组残留并已处理"
            if run["residual_processes_detected"]
            else "无"
        ),
        "- 进程回收结果：": (
            "回收失败"
            if run["residual_processes_after_cleanup"]
            else "TERM 后 KILL 已回收"
            if run["process_group_kill_sent"]
            else "TERM 已回收"
            if run["process_group_term_sent"]
            else "不涉及"
        ),
    }
    for prefix, value in values.items():
        if any(line.strip().startswith(prefix) for line in text.splitlines()):
            update_record_line(round_file, prefix, value)
            text = round_file.read_text(encoding="utf-8")


def process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def wait_for_process_group_exit(
    process_group_id: int,
    timeout_seconds: float,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while process_group_exists(process_group_id):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def terminate_process_group(
    process: subprocess.Popen,
    grace_seconds: float = 2.0,
) -> tuple[bytes, bytes, bool, bool, bool]:
    """先 TERM 再 KILL 回收整组进程，避免测试终端和孙进程常驻。"""
    term_sent = False
    kill_sent = False
    if process_group_exists(process.pid):
        try:
            os.killpg(process.pid, signal.SIGTERM)
            term_sent = True
        except ProcessLookupError:
            pass
    try:
        stdout, stderr = process.communicate(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        stdout = b""
        stderr = b""

    exited = wait_for_process_group_exit(process.pid, grace_seconds)
    if not exited:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            kill_sent = True
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            stdout = stdout or b""
            stderr = stderr or b""
        wait_for_process_group_exit(process.pid, grace_seconds)
    else:
        completed_stdout, completed_stderr = process.communicate()
        stdout = completed_stdout if completed_stdout is not None else stdout
        stderr = completed_stderr if completed_stderr is not None else stderr
    remaining = process_group_exists(process.pid)
    return stdout or b"", stderr or b"", term_sent, kill_sent, remaining


def run_test_command_once(
    command: list[str],
    cwd: Path,
    timeout_seconds: int,
) -> tuple[int, bytes, bytes, bool, bool, bool, bool, bool]:
    """以一次性、非 PTY 进程组执行命令并返回回收事实。"""
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        residual_detected = process_group_exists(process.pid)
        term_sent = False
        kill_sent = False
        residual_remaining = residual_detected
        if residual_detected:
            (
                cleanup_stdout,
                cleanup_stderr,
                term_sent,
                kill_sent,
                residual_remaining,
            ) = terminate_process_group(process)
            stdout = cleanup_stdout if cleanup_stdout else stdout
            stderr = cleanup_stderr if cleanup_stderr else stderr
        return (
            int(process.returncode),
            stdout or b"",
            stderr or b"",
            False,
            residual_detected,
            term_sent,
            kill_sent,
            residual_remaining,
        )
    except subprocess.TimeoutExpired:
        (
            stdout,
            stderr,
            term_sent,
            kill_sent,
            residual_remaining,
        ) = terminate_process_group(process)
        return (
            124,
            stdout,
            stderr,
            True,
            True,
            term_sent,
            kill_sent,
            residual_remaining,
        )
    except BaseException:
        terminate_process_group(process)
        raise


def command_test_run(args: argparse.Namespace) -> None:
    """无 shell 执行自动化测试，并把机器证据绑定到当前实现和 TSxx。"""
    record = Path(args.record).resolve()
    state = load_state(record)
    if state.get("status") != "completed" or not state.get("completion_snapshot"):
        raise SystemExit("实现会话尚未完成，不能执行正式测试命令")
    current = current_snapshot(state)
    if current.get("fingerprint") != state["completion_snapshot"].get("fingerprint"):
        raise SystemExit("代码已偏离实现完成快照，不能执行测试")
    command = list(args.test_command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("test-run 必须在 -- 后提供命令及参数")
    if args.timeout_seconds < 1 or args.timeout_seconds > 3600:
        raise SystemExit("--timeout-seconds 必须在 1 到 3600 之间")
    round_file, round_id, mode = test_round_context(record, args.round)
    scenario, scenario_fingerprint = test_scenario_plan(
        record,
        round_file,
        args.scenario,
    )
    if scenario["Effect"] != args.effect:
        raise SystemExit(
            f"{args.scenario} 的计划 Effect 为 {scenario['Effect']}，"
            f"与 --effect {args.effect} 不一致"
        )
    authorization = (args.effect_authorization or "").strip()
    if args.effect not in {"read-only", "local-write"} and len(authorization) < 8:
        raise SystemExit("存在数据、状态或外部副作用时必须提供具体 --effect-authorization")
    if not args.environment.strip():
        raise SystemExit("test-run 必须提供非空 --environment")

    cwd = verification_cwd(state, args.cwd)
    before = current_snapshot(state)
    started_wall = time.monotonic()
    started_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    timed_out = False
    environment_blocked = False
    residual_processes_detected = False
    term_sent = False
    kill_sent = False
    residual_processes_after_cleanup = False
    try:
        (
            exit_code,
            stdout,
            stderr,
            timed_out,
            residual_processes_detected,
            term_sent,
            kill_sent,
            residual_processes_after_cleanup,
        ) = run_test_command_once(
            command,
            cwd,
            args.timeout_seconds,
        )
    except OSError as error:
        environment_blocked = True
        exit_code = 127
        stdout = b""
        stderr = str(error).encode("utf-8", errors="replace")
    after = current_snapshot(state)
    result = (
        "stale"
        if before["fingerprint"] != after["fingerprint"]
        else "blocked"
        if timed_out or environment_blocked or residual_processes_after_cleanup
        else "passed"
        if exit_code == 0
        else "failed"
    )
    execution_id = next_test_execution_id(state, round_id)
    evidence_relative = Path("reports") / "test-evidence" / f"{round_id}-{execution_id}.json"
    evidence_path = record.parent / evidence_relative
    ensure_evidence_path_safe(record.parent, evidence_path)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_evidence_path_safe(record.parent, evidence_path)
    redacted_argv = redact_test_argv(command)
    sensitive_argv_values = sensitive_test_argv_values(command)
    run = {
        "schema_version": 2,
        "execution_id": execution_id,
        "test_round": round_id,
        "test_mode": mode,
        "scenario_id": args.scenario,
        "scenario_plan_fingerprint": scenario_fingerprint,
        "implementation_round": state.get("round"),
        "implementation_fingerprint": current["fingerprint"],
        "argv": redacted_argv,
        "cwd": str(cwd),
        "environment": redact_sensitive_text(args.environment.strip()),
        "effect": args.effect,
        "effect_authorization": redact_sensitive_text(authorization) or "不需要",
        "started_at": started_at,
        "completed_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "duration_ms": int((time.monotonic() - started_wall) * 1000),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "execution_mode": "one-shot non-PTY",
        "timeout_seconds": args.timeout_seconds,
        "residual_processes_detected": residual_processes_detected,
        "process_group_term_sent": term_sent,
        "process_group_kill_sent": kill_sent,
        "residual_processes_after_cleanup": residual_processes_after_cleanup,
        "stdout": redact_test_output(stdout, sensitive_values=sensitive_argv_values),
        "stderr": redact_test_output(stderr, sensitive_values=sensitive_argv_values),
        "before_snapshot_fingerprint": before["fingerprint"],
        "after_snapshot_fingerprint": after["fingerprint"],
        "evidence_path": evidence_relative.as_posix(),
        "result": result,
    }
    atomic_write_text(
        evidence_path,
        json.dumps(run, ensure_ascii=False, indent=2) + "\n",
    )
    run["evidence_sha256"] = file_digest(evidence_path)
    test_runs = list(state.get("test_runs", []))
    test_runs.append(run)
    state["test_runs"] = test_runs
    save_state(record, state)
    append_test_execution_record(record, round_file, run)
    record_test_process_execution(record, round_file, run)

    stdout_summary = run["stdout"]["summary"]
    stderr_summary = run["stderr"]["summary"]
    if stdout_summary:
        print(stdout_summary)
    if stderr_summary:
        print(stderr_summary, file=sys.stderr)
    outcome = "OK" if result == "passed" else "BLOCKED" if result == "blocked" else "FAIL"
    print(f"[{outcome}] {execution_id} test-run: {result}")
    print(f"- 轮次/场景: {round_id}/{args.scenario}")
    print(f"- 命令: {shlex.join(redacted_argv)}")
    print(f"- 证据: {evidence_relative.as_posix()}")
    print(f"- 证据 SHA256: {run['evidence_sha256']}")
    if result != "passed":
        raise SystemExit(exit_code or 1)


def machine_test_run_errors(record: Path, state: dict, current: dict) -> list[str]:
    """核对 test-run 状态、报告行和证据文件，API/人工观察不受此门禁替代。"""
    round_file = latest_test_round_file(record)
    if round_file is None:
        return []
    round_id = (
        "quick"
        if record.name == "quick.md"
        else validator.extract_line_value(
            round_file.read_text(encoding="utf-8"),
            "- 轮次：",
        )
    )
    runs = [
        run
        for run in state.get("test_runs", [])
        if run.get("test_round") == round_id
    ]
    text = round_file.read_text(encoding="utf-8")
    heading = (
        "### 5.3 Quick 命令证据"
        if record.name == "quick.md"
        else "## 5. 执行记录"
    )
    headers, rows = validator.extract_first_table(
        validator.extract_section(text, heading)
    )
    machine_rows = {
        validator.table_cell(headers, row, "执行ID"): row
        for row in rows
        if (
            re.fullmatch(
                r"E\d+",
                validator.table_cell(headers, row, "执行ID"),
            )
            and (
                record.name == "quick.md"
                or validator.table_cell(
                    headers,
                    row,
                    "命令/接口/观察点",
                ).strip("`").startswith("command:")
            )
        )
    }
    errors: list[str] = []
    run_ids = {str(run.get("execution_id")) for run in runs}
    handwritten = sorted(set(machine_rows) - run_ids)
    if handwritten:
        errors.append(
            "存在没有 test-run 状态的手写 command 证据: "
            + ", ".join(handwritten)
        )
    for run in runs:
        execution_id = str(run.get("execution_id"))
        row = machine_rows.get(execution_id)
        if row is None:
            errors.append(f"{execution_id} 机器执行未写入当前测试报告")
            continue
        for key, expected in [
            ("implementation_round", state.get("round")),
            ("implementation_fingerprint", current.get("fingerprint")),
        ]:
            if run.get(key) != expected:
                errors.append(f"{execution_id} 的 {key} 已失效")
        try:
            _, current_plan_fingerprint = test_scenario_plan(
                record,
                round_file,
                str(run.get("scenario_id")),
            )
        except SystemExit as error:
            errors.append(f"{execution_id} 场景计划不可用: {error}")
        else:
            if run.get("scenario_plan_fingerprint") != current_plan_fingerprint:
                errors.append(f"{execution_id} 执行后场景计划发生变化")
        evidence_relative = Path(str(run.get("evidence_path", "")))
        evidence_path = record.parent / evidence_relative
        try:
            ensure_evidence_path_safe(record.parent, evidence_path)
        except SystemExit as error:
            errors.append(f"{execution_id} {error}")
            continue
        evidence_path = evidence_path.resolve()
        expected_root = (record.parent.resolve() / "reports" / "test-evidence")
        try:
            evidence_path.relative_to(expected_root)
        except ValueError:
            errors.append(f"{execution_id} 证据路径越出 reports/test-evidence")
            continue
        if not evidence_path.is_file():
            errors.append(f"{execution_id} 机器证据文件不存在")
            continue
        if file_digest(evidence_path) != run.get("evidence_sha256"):
            errors.append(f"{execution_id} 机器证据文件已被修改")
        try:
            evidence_data = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"{execution_id} 机器证据不是有效 JSON")
        else:
            expected_evidence = {
                key: value
                for key, value in run.items()
                if key != "evidence_sha256"
            }
            if evidence_data != expected_evidence:
                errors.append(f"{execution_id} 机器证据内容与状态不一致")
        if validator.table_cell(headers, row, "场景ID") != run.get("scenario_id"):
            errors.append(f"{execution_id} 报告场景与机器状态不一致")
        if validator.table_cell(headers, row, "Effect") != run.get("effect"):
            errors.append(f"{execution_id} 报告 Effect 与机器状态不一致")
        hash_header = "SHA-256" if record.name == "quick.md" else "证据 SHA-256"
        if validator.table_cell(headers, row, hash_header) != run.get("evidence_sha256"):
            errors.append(f"{execution_id} 报告 SHA 与机器状态不一致")
        evidence_header = "机器证据" if record.name == "quick.md" else "原始证据"
        original = validator.table_cell(headers, row, evidence_header)
        if run.get("evidence_path") not in original:
            errors.append(f"{execution_id} 报告证据路径与机器状态不一致")
        expected_result = {
            "passed": "PASS",
            "failed": "FAIL",
            "blocked": "BLOCKED",
            "stale": "BLOCKED",
        }.get(str(run.get("result")))
        if validator.table_cell(headers, row, "结论") != expected_result:
            errors.append(f"{execution_id} 报告结论与机器状态不一致")
    return errors


def machine_test_runs_fingerprint(record: Path, state: dict) -> str:
    round_file = latest_test_round_file(record)
    if round_file is None:
        return fingerprint_entries([])
    round_id = (
        "quick"
        if record.name == "quick.md"
        else validator.extract_line_value(
            round_file.read_text(encoding="utf-8"),
            "- 轮次：",
        )
    )
    entries: list[tuple[str, bytes]] = []
    for run in state.get("test_runs", []):
        if run.get("test_round") != round_id:
            continue
        entries.append(
            (
                f"state/{run.get('execution_id')}",
                json.dumps(
                    run,
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8"),
            )
        )
        evidence_path = record.parent / str(run.get("evidence_path", ""))
        entries.append(
            (
                str(run.get("evidence_path", "")),
                evidence_path.read_bytes()
                if evidence_path.is_file()
                else b"<missing>",
            )
        )
    return fingerprint_entries(entries)


def sync_test_gate(record: Path, result: str) -> None:
    """Full 流程止于测试验证；这里只更新测试门禁，不声明交付或发布就绪。"""
    if record.name == "quick.md":
        return
    meta_path = record.parent / "meta.json"
    if not meta_path.exists():
        return
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    gates = meta.setdefault("gates", {})
    gates["test_passed"] = result == "passed"
    gates["release_ready"] = False
    meta["current_phase"] = "测试验证"
    meta["current_status"] = {
        "passed": "已通过",
        "needs_more": "需补测",
        "blocked": "阻塞",
    }[result]
    atomic_write_text(meta_path, json.dumps(meta, ensure_ascii=False, indent=2) + "\n")


def command_test_mark(args: argparse.Namespace) -> None:
    record = Path(args.record).resolve()
    state = load_state(record)
    if state.get("status") != "completed" or not state.get("completion_snapshot"):
        raise SystemExit("实现会话尚未完成，不能登记测试结论")

    current = current_snapshot(state)
    completed = state["completion_snapshot"]
    if current["fingerprint"] != completed.get("fingerprint"):
        raise SystemExit("代码已偏离实现完成快照，不能登记测试结论")
    machine_errors = machine_test_run_errors(record, state, current)
    if machine_errors:
        print("[FAIL] test-run 机器证据门禁未通过：")
        for error in machine_errors:
            print(f"- {error}")
        raise SystemExit(1)

    repositories = current.get("repositories", [])
    multi_repo = len(repositories) > 1
    actual_paths = {
        f"{repository['label']}/{item['path']}" if multi_repo else item["path"]
        for repository in repositories
        for item in repository.get("files", [])
    }
    if args.result == "passed":
        if record.name == "quick.md":
            test_errors = validator.validate_quick_test_evidence(
                record,
                actual_paths=actual_paths,
            )
        else:
            test_errors = validator.validate_test_report_completion(
                record.parent / "07-test-report.md",
                record.parent / "test-rounds",
                expected_implementation_round=state.get("round"),
                expected_fingerprint=current["fingerprint"],
                expected_review_round=None,
                actual_paths=actual_paths,
            )
        if test_errors:
            print("[FAIL] 测试通过门禁未通过：")
            for error in test_errors:
                print(f"- {error}")
            raise SystemExit(1)
    else:
        if record.name == "quick.md":
            test_errors = validator.validate_quick_test_evidence(
                record,
                require_passed=False,
                actual_paths=actual_paths,
            )
        else:
            test_errors = validator.validate_test_report_nonpass(
                record.parent / "07-test-report.md",
                record.parent / "test-rounds",
                result=args.result,
                expected_implementation_round=state.get("round", ""),
                expected_fingerprint=current["fingerprint"],
                expected_review_round=None,
            )
        if test_errors:
            print("[FAIL] 测试非通过结论缺少最小证据：")
            for error in test_errors:
                print(f"- {error}")
            raise SystemExit(1)

    result_label = {"passed": "通过", "needs_more": "需补测", "blocked": "阻塞"}[args.result]
    if record.name == "quick.md":
        update_record_line(record, "- 测试结论：", result_label)
        update_record_line(record, "- 测试对应实现轮次：", state.get("round", ""))
        update_record_line(record, "- 测试对应差异指纹：", current["fingerprint"])

    state["test"] = {
        "implementation_round": state.get("round"),
        "fingerprint": current["fingerprint"],
        "result": args.result,
        "artifact_fingerprint": test_artifact_fingerprint(record),
        "machine_evidence_fingerprint": machine_test_runs_fingerprint(
            record,
            state,
        ),
        "tested_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    save_state(record, state)
    sync_test_gate(record, args.result)
    print(f"[OK] 已登记 {state.get('round')} 测试结论: {args.result}")
    print(f"[OK] 测试对应差异指纹: {current['fingerprint']}")


def command_test_status(args: argparse.Namespace) -> None:
    record = Path(args.record).resolve()
    state = load_state(record)
    test = state.get("test") or {}
    if not test:
        print("[PENDING] 当前实现轮次尚未登记测试结论")
        raise SystemExit(1)
    current = current_snapshot(state)
    if (
        test.get("implementation_round") != state.get("round")
        or test.get("fingerprint") != current.get("fingerprint")
    ):
        print("[STALE] 测试结论对应的实现轮次或差异指纹已经变化")
        raise SystemExit(1)
    current_artifact_fingerprint = test_artifact_fingerprint(record)
    if test.get("artifact_fingerprint") != current_artifact_fingerprint:
        print("[STALE] 测试记录在登记结论后发生变化，必须重新登记")
        raise SystemExit(1)
    if int(state.get("schema_version", 1)) >= 9:
        machine_errors = machine_test_run_errors(record, state, current)
        if machine_errors:
            print("[STALE] test-run 机器证据已经失效：")
            for error in machine_errors:
                print(f"- {error}")
            raise SystemExit(1)
        if test.get("machine_evidence_fingerprint") != machine_test_runs_fingerprint(
            record,
            state,
        ):
            print("[STALE] test-run 机器证据指纹已经变化")
            raise SystemExit(1)
    print(f"测试对应实现轮次: {test.get('implementation_round')}")
    print(f"测试结论: {test.get('result')}")
    print(f"测试差异指纹: {test.get('fingerprint')}")
    print(f"测试工件指纹: {test.get('artifact_fingerprint')}")
    if args.require_passed and test.get("result") != "passed":
        raise SystemExit(1)


def main() -> None:
    # 历史直调命令仍可读，但不再出现在新版命令帮助中。
    if len(sys.argv) > 1 and sys.argv[1] == "review-skip":
        legacy_parser = argparse.ArgumentParser(description="历史 Review 记录兼容")
        legacy_parser.add_argument("--record", required=True)
        legacy_parser.add_argument("--reason", required=True)
        command_review_skip(legacy_parser.parse_args(sys.argv[2:]))
        return

    parser = argparse.ArgumentParser(description="管理 GGG 编码实现会话")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("--record", required=True)
    start_parser.add_argument(
        "--risk-profile",
        choices=["tiny", "normal", "high"],
        default="normal",
    )
    start_parser.add_argument(
        "--repo-root",
        action="append",
        default=[],
        help="本轮涉及的 Git 仓库，可重复",
    )
    start_parser.add_argument(
        "--adopt-existing-file",
        action="append",
        default=[],
        help="接管启动前已属于本需求的 Git 脏文件；单仓可用相对路径，多仓必须用绝对路径",
    )
    start_parser.add_argument(
        "--diff-range",
        action="append",
        default=[],
        help="绑定已提交差异 <base>..<target>；多仓时按 --repo-root 顺序各传一次",
    )
    start_parser.add_argument(
        "--adopt-commit",
        action="append",
        default=[],
        help="绑定单个已提交功能提交，等价 commit^..commit；多仓时按顺序各传一次",
    )
    start_parser.add_argument(
        "--task",
        action="append",
        default=[],
        help="本轮要实现的 Txx，可重复；full 默认选择全部编码任务",
    )
    start_parser.set_defaults(handler=command_start)

    precheck_parser = subparsers.add_parser("precheck")
    precheck_parser.add_argument("--record", required=True)
    precheck_parser.set_defaults(handler=command_precheck)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--record", required=True)
    verify_parser.add_argument("--cwd")
    verify_parser.add_argument("--label")
    verify_parser.add_argument("--timeout-seconds", type=int, default=60)
    verify_parser.add_argument("verification_command", nargs=argparse.REMAINDER)
    verify_parser.set_defaults(handler=command_verify)

    restart_parser = subparsers.add_parser("restart")
    restart_parser.add_argument("--record", required=True)
    restart_parser.add_argument("--reason", required=True)
    restart_parser.set_defaults(handler=command_restart)

    complete_parser = subparsers.add_parser("complete")
    complete_parser.add_argument("--record", required=True)
    complete_parser.add_argument("--verification-waiver")
    complete_parser.set_defaults(handler=command_complete)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--record", required=True)
    status_parser.set_defaults(handler=command_status)

    review_mark_parser = subparsers.add_parser("review-mark")
    review_mark_parser.add_argument("--record", required=True)
    review_mark_parser.add_argument("--result", required=True, choices=["passed", "needs_changes", "blocked"])
    review_mark_parser.add_argument(
        "--disposition",
        choices=["light", "formal"],
        help=argparse.SUPPRESS,
    )
    review_mark_parser.add_argument(
        "--reviewer-mode",
        choices=["fresh-review", "self-review"],
        help=argparse.SUPPRESS,
    )
    review_mark_parser.add_argument("--self-review-reason", help=argparse.SUPPRESS)
    review_mark_parser.set_defaults(handler=command_review_mark)

    review_status_parser = subparsers.add_parser("review-status")
    review_status_parser.add_argument("--record", required=True)
    review_status_parser.add_argument(
        "--require-passed",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    review_status_parser.add_argument(
        "--require-gate-satisfied",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    review_status_parser.set_defaults(handler=command_review_status)

    test_run_parser = subparsers.add_parser("test-run")
    test_run_parser.add_argument("--record", required=True)
    test_run_parser.add_argument("--round", required=True)
    test_run_parser.add_argument("--scenario", required=True)
    test_run_parser.add_argument("--cwd")
    test_run_parser.add_argument("--environment", required=True)
    test_run_parser.add_argument(
        "--effect",
        required=True,
        choices=sorted(validator.TEST_EFFECTS),
    )
    test_run_parser.add_argument("--effect-authorization")
    test_run_parser.add_argument("--timeout-seconds", type=int, default=60)
    test_run_parser.add_argument("test_command", nargs=argparse.REMAINDER)
    test_run_parser.set_defaults(handler=command_test_run)

    test_mark_parser = subparsers.add_parser("test-mark")
    test_mark_parser.add_argument("--record", required=True)
    test_mark_parser.add_argument("--result", required=True, choices=["passed", "needs_more", "blocked"])
    test_mark_parser.set_defaults(handler=command_test_mark)

    test_status_parser = subparsers.add_parser("test-status")
    test_status_parser.add_argument("--record", required=True)
    test_status_parser.add_argument("--require-passed", action="store_true")
    test_status_parser.set_defaults(handler=command_test_status)

    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
