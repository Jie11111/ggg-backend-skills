#!/usr/bin/env python3
"""安全回退需求阶段。回退时不删除已有文档，只修改 meta.json 的阶段和状态。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from workflow_contracts import PUBLIC_PHASES


def main() -> None:
    parser = argparse.ArgumentParser(description="回退需求阶段")
    parser.add_argument("--feature-dir", required=True, help="需求目录")
    parser.add_argument("--to-phase", required=True, choices=PUBLIC_PHASES, help="目标阶段")
    args = parser.parse_args()

    feature_dir = Path(args.feature_dir).resolve()
    meta_path = feature_dir / "meta.json"
    if not meta_path.exists():
        print("[FAIL] 缺少 meta.json")
        raise SystemExit(1)

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.pop("blocking_issue_count", None)
    current_phase = meta.get("current_phase", "")
    target_phase = args.to_phase

    if current_phase not in PUBLIC_PHASES:
        print(f"[FAIL] 当前阶段非法: {current_phase}")
        raise SystemExit(1)

    current_idx = PUBLIC_PHASES.index(current_phase)
    target_idx = PUBLIC_PHASES.index(target_phase)

    if target_idx >= current_idx:
        print(f"[FAIL] 目标阶段 {target_phase} 不在当前阶段 {current_phase} 之前，无需回退")
        print("[提示] 如需前进到下一阶段，请使用 to-alignment / to-design / to-tasks 命令")
        raise SystemExit(1)

    # 回退阶段
    meta["current_phase"] = target_phase

    # 回退状态
    status_map = {
        "需求受理": "调研中",
        "需求对齐": "调研中",
        "技术方案": "方案中",
        "任务拆分": "拆分中",
        "编码实现": "编码中",
        "代码检查": "检查中",
        "测试验证": "验证中",
        "交付完成": "已交付",
    }
    meta["current_status"] = status_map.get(target_phase, "调研中")

    # 回退门禁
    gates = meta.setdefault("gates", {})
    if target_idx < PUBLIC_PHASES.index("技术方案"):
        gates["alignment_completed"] = False
        gates["design_confirmed"] = False
        gates["schema_confirmed"] = False
        confirmation = meta.setdefault("schema_confirmation", {})
        confirmation["confirmed_schema_sha256"] = ""
        confirmation["confirmation_source"] = ""
        confirmation["confirmed_at"] = ""
    if target_idx < PUBLIC_PHASES.index("任务拆分"):
        gates["design_confirmed"] = False
        gates["tasks_confirmed"] = False
    if target_idx < PUBLIC_PHASES.index("编码实现"):
        gates["tasks_confirmed"] = False
        gates["implementation_completed"] = False
        gates["review_passed"] = False
        gates["test_passed"] = False
        gates["release_ready"] = False
    if target_idx < PUBLIC_PHASES.index("代码检查"):
        gates["implementation_completed"] = False
        gates["review_passed"] = False
        gates["test_passed"] = False
        gates["release_ready"] = False
    if target_idx < PUBLIC_PHASES.index("测试验证"):
        gates["review_passed"] = False
        gates["test_passed"] = False
        gates["release_ready"] = False
    if target_idx < PUBLIC_PHASES.index("交付完成"):
        gates["test_passed"] = False
        gates["release_ready"] = False

    # 清除回退范围内的重审标记
    review_flags = meta.setdefault("review_flags", {})
    review_flags["alignment_needs_review"] = False
    review_flags["design_needs_review"] = False
    review_flags["tasks_needs_review"] = False

    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] 已回退到阶段: {target_phase}")
    print(f"[OK] 当前状态: {meta['current_status']}")
    print("[提示] 已有文档未删除，请根据需要手动清理或更新")


if __name__ == "__main__":
    main()
