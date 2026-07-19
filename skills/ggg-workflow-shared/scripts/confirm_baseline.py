#!/usr/bin/env python3
"""在用户完成最终反向确认后，锁定 baseline 业务指纹。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workflow_validation as validator
from workflow_contracts import BASELINE_REQUIRED_TOKENS


def replace_confirmation_lines(text: str, source: str) -> str:
    text = re.sub(r"(?m)^- 基线状态：.*$", "- 基线状态：已确认", text, count=1)
    text = re.sub(
        r"(?m)^- 最终反向确认：.*$",
        f"- 最终反向确认：已确认（{source}）",
        text,
        count=1,
    )
    return text


def main() -> None:
    parser = argparse.ArgumentParser(description="确认并锁定 baseline 业务指纹")
    parser.add_argument("--feature-dir", required=True, help="需求目录")
    parser.add_argument("--source", required=True, help="本次用户最终确认的消息定位或时间")
    args = parser.parse_args()

    feature_dir = Path(args.feature_dir).resolve()
    meta_path = feature_dir / "meta.json"
    baseline_path = feature_dir / "00-baseline.md"
    if not meta_path.exists() or not baseline_path.exists():
        raise SystemExit("缺少 meta.json 或 00-baseline.md")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.pop("blocking_issue_count", None)
    if int(meta.get("workflow_schema_version", 1)) < 3:
        raise SystemExit("旧版需求目录不能直接确认新版 baseline，请先迁移模板")

    candidate = replace_confirmation_lines(baseline_path.read_text(encoding="utf-8"), args.source)
    errors: list[str] = []
    validator.assert_contains(candidate, BASELINE_REQUIRED_TOKENS, "00-baseline.md", errors)
    validator.assert_baseline_quality(candidate, errors, clarification_gate_required=True)
    if errors:
        print("[FAIL] baseline 尚未达到可确认标准")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    baseline_path.write_text(candidate, encoding="utf-8")
    gates = meta.setdefault("gates", {})
    gates["clarification_required"] = True
    gates["clarification_confirmed"] = True
    clarification = meta.setdefault("clarification", {})
    clarification["confirmed_baseline_sha256"] = validator.baseline_business_fingerprint(candidate)
    clarification["baseline_confirmation_source"] = args.source
    clarification["baseline_confirmed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if meta.get("current_phase") == "需求受理":
        meta["current_status"] = "已确认"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[OK] baseline 已确认并锁定业务指纹")


if __name__ == "__main__":
    main()
