#!/usr/bin/env python3
"""在需求对齐阶段锁定用户已确认的 SQL 语义。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workflow_validation as validator


def replace_confirmation_lines(text: str, source: str, fingerprint: str) -> str:
    replacements = [
        (
            r"(?m)^- SQL 确认状态：.*$",
            "- SQL 确认状态：已确认",
            "SQL 确认状态",
        ),
        (
            r"(?m)^- SQL 确认来源：.*$",
            f"- SQL 确认来源：{source}",
            "SQL 确认来源",
        ),
        (
            r"(?m)^- SQL 语义指纹：.*$",
            f"- SQL 语义指纹：{fingerprint}",
            "SQL 语义指纹",
        ),
    ]
    candidate = text
    for pattern, replacement, label in replacements:
        candidate, count = re.subn(
            pattern,
            lambda _match, value=replacement: value,
            candidate,
            count=1,
        )
        if count != 1:
            raise ValueError(f"01-research.md 缺少唯一的{label}字段")
    return candidate


def fail(errors: list[str]) -> None:
    print("[FAIL] SQL 确认前校验未通过")
    for error in errors:
        print(f"- {error}")
    raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="确认并锁定需求对齐阶段的 SQL 语义",
    )
    parser.add_argument("--feature-dir", required=True, help="需求目录")
    parser.add_argument(
        "--source",
        required=True,
        help="用户确认 SQL 的消息定位或时间",
    )
    args = parser.parse_args()

    confirmation_source = args.source.strip()
    if (
        not confirmation_source
        or "\n" in confirmation_source
        or "\r" in confirmation_source
        or confirmation_source in {"用户消息", "用户确认", "已确认"}
    ):
        raise SystemExit("--source 必须填写单行、可回查的用户确认消息定位或时间")

    feature_dir = Path(args.feature_dir).resolve()
    meta_path = feature_dir / "meta.json"
    research_path = feature_dir / "01-research.md"
    if not meta_path.exists() or not research_path.exists():
        raise SystemExit("缺少 meta.json 或 01-research.md")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if int(meta.get("workflow_schema_version", 1)) < 5:
        raise SystemExit("旧版需求目录继续使用原 SQL 契约，不能直接执行 confirm-sql")
    if meta.get("current_phase") != "需求对齐":
        raise SystemExit("只有需求对齐阶段可以执行 confirm-sql")

    research_text = research_path.read_text(encoding="utf-8")
    if validator.research_schema_version(research_text) < 3:
        raise SystemExit("01-research.md 不是支持 SQL Gate 的 v3 文档")

    errors = validator.validate_research_doc(
        research_path,
        validator.infer_repo_root_from_feature(feature_dir),
        validator.read_text(feature_dir / "00-baseline.md"),
    )
    valid_claim_ids = validator.extract_claim_ids_from_research(research_text)
    snapshot = validator.research_sql_gate_snapshot(
        research_text,
        errors,
        valid_claim_ids,
    )
    impact_type = str(snapshot["impact_type"])
    draft_path = feature_dir / "sql-draft.sql"
    if impact_type == "none":
        if draft_path.exists():
            errors.append("SQL 影响类型为不涉及时不得保留 sql-draft.sql")
        draft_fingerprint = ""
    elif impact_type in {"query_dml", "ddl"}:
        errors.extend(
            validator.validate_sql_draft_doc(
                draft_path,
                valid_claim_ids,
                snapshot["rows"],  # type: ignore[arg-type]
                impact_type,
            )
        )
        draft_fingerprint = validator.sql_draft_semantic_fingerprint(
            validator.read_text(draft_path)
        )
        if not draft_fingerprint:
            errors.append("sql-draft.sql 无法生成有效语义指纹")
    else:
        draft_fingerprint = ""

    if errors:
        fail(errors)

    research_fingerprint = validator.research_sql_semantic_fingerprint(
        research_text
    )
    semantic_fingerprint = hashlib.sha256(
        (
            f"{impact_type}\n"
            f"{research_fingerprint}\n"
            f"{draft_fingerprint}\n"
        ).encode("utf-8")
    ).hexdigest()
    try:
        candidate_research = replace_confirmation_lines(
            research_text,
            confirmation_source,
            semantic_fingerprint,
        )
    except ValueError as exc:
        fail([str(exc)])

    candidate_errors: list[str] = []
    candidate_snapshot = validator.research_sql_gate_snapshot(
        candidate_research,
        candidate_errors,
        valid_claim_ids,
    )
    if candidate_snapshot["status"] != "已确认":
        candidate_errors.append("01-research.md SQL 确认状态回写失败")
    if candidate_snapshot["semantic_fingerprint"] != semantic_fingerprint:
        candidate_errors.append("01-research.md SQL 语义指纹回写失败")
    if candidate_errors:
        fail(candidate_errors)

    confirmed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    gates = meta.setdefault("gates", {})
    gates["sql_confirmed"] = True
    confirmation = meta.setdefault("sql_confirmation", {})
    confirmation.update(
        {
            "impact_type": impact_type,
            "research_semantic_fingerprint": research_fingerprint,
            "draft_semantic_fingerprint": draft_fingerprint,
            "semantic_fingerprint": semantic_fingerprint,
            "confirmation_source": confirmation_source,
            "confirmed_at": confirmed_at,
        }
    )
    meta["current_status"] = "SQL已确认"

    research_path.write_text(candidate_research, encoding="utf-8")
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("[OK] SQL 语义已完成用户确认并锁定")
    print(f"[OK] SQL 影响类型: {impact_type}")
    print(f"[OK] SQL 语义指纹: {semantic_fingerprint}")
    print(f"[OK] 确认来源: {confirmation_source}")


if __name__ == "__main__":
    main()
