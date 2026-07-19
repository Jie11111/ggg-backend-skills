#!/usr/bin/env python3
"""用户确认 SQL 后，校验预检与 DDL 并锁定 04-schema.sql 指纹。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workflow_validation as validator


def main() -> None:
    parser = argparse.ArgumentParser(description="锁定用户已确认的 SQL 指纹")
    parser.add_argument("--feature-dir", required=True, help="需求目录")
    parser.add_argument("--source", required=True, help="用户确认 SQL 的消息定位或时间")
    args = parser.parse_args()

    confirmation_source = args.source.strip()
    if not confirmation_source:
        raise SystemExit("--source 不能只包含空白，必须填写可定位的用户确认消息或时间")

    feature_dir = Path(args.feature_dir).resolve()
    meta_path = feature_dir / "meta.json"
    if not meta_path.exists():
        raise SystemExit("缺少 meta.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("current_phase") != "技术方案":
        raise SystemExit("只有技术方案阶段可以确认 04-schema.sql")

    design_path = feature_dir / "02-design.md"
    research_text = validator.read_text(feature_dir / "01-research.md")
    eligible_claim_ids = validator.extract_design_eligible_claim_ids_from_research(research_text)
    transferred_question_ids = validator.extract_transferred_design_question_ids_from_research(research_text)
    precheck_errors = validator.validate_design_precheck(
        design_path,
        eligible_claim_ids,
        transferred_question_ids,
    )

    schema_path = feature_dir / "04-schema.sql"
    design_text = validator.read_text(design_path)
    schema_errors = validator.validate_schema_doc(
        schema_path,
        meta,
        validator.extract_claim_ids_from_research(research_text),
        validator.extract_design_ids_from_design(design_text),
    )
    errors = precheck_errors + schema_errors
    if errors:
        print("[FAIL] SQL 确认前校验未通过")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    schema_text = schema_path.read_text(encoding="utf-8")
    gates = meta.setdefault("gates", {})
    gates["schema_confirmed"] = True
    confirmation = meta.setdefault("schema_confirmation", {})
    confirmation["confirmed_schema_sha256"] = validator.schema_fingerprint(schema_text)
    confirmation["confirmation_source"] = confirmation_source
    confirmation["confirmed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("[OK] 04-schema.sql 已完成用户确认并锁定内容指纹")
    print(f"[OK] 确认来源: {confirmation_source}")


if __name__ == "__main__":
    main()
