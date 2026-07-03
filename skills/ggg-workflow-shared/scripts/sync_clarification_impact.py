#!/usr/bin/env python3
"""根据新增澄清同步需求状态、重审标记与门禁状态。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from workflow_contracts import PUBLIC_PHASES, REVIEW_FLAG_KEYS


IMPACT_CHOICES = ["baseline", "research", "blocking", "design", "schema", "tasks"]
STATUS_PRIORITY = {
    "待重审": 1,
    "待澄清": 2,
}


def load_meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_meta(path: Path, meta: dict) -> None:
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_defaults(meta: dict) -> tuple[dict, dict]:
    gate_defaults = {
        "alignment_completed": False,
        "design_confirmed": False,
        "tasks_confirmed": False,
        "implementation_completed": False,
        "review_passed": False,
        "test_passed": False,
        "release_ready": False,
        "business_model_confirmed": False,
        "upstream_contract_confirmed": False,
    }
    gates = meta.setdefault(
        "gates",
        gate_defaults.copy(),
    )
    for key, value in gate_defaults.items():
        gates.setdefault(key, value)
    review_flags = meta.setdefault(
        "review_flags",
        {
            "alignment_needs_review": False,
            "design_needs_review": False,
            "tasks_needs_review": False,
        },
    )
    review_flags.pop("baseline_needs_review", None)
    for key in REVIEW_FLAG_KEYS:
        review_flags.setdefault(key, False)
    meta.setdefault(
        "clarification",
        {
            "count": 0,
            "last_source": "",
            "last_summary": "",
            "last_updated_at": "",
            "last_impacts": [],
        },
    )
    return gates, review_flags


def bump_status(meta: dict, new_status: str) -> None:
    current_status = str(meta.get("current_status", "")).strip()
    if STATUS_PRIORITY.get(new_status, 0) >= STATUS_PRIORITY.get(current_status, 0):
        meta["current_status"] = new_status


def phase_reached(current_phase: str, target_phase: str) -> bool:
    if current_phase not in PUBLIC_PHASES or target_phase not in PUBLIC_PHASES:
        return False
    return PUBLIC_PHASES.index(current_phase) >= PUBLIC_PHASES.index(target_phase)


def reset_downstream_gates(gates: dict, from_phase: str) -> None:
    if from_phase == "design":
        gates["design_confirmed"] = False
        gates["tasks_confirmed"] = False
        gates["implementation_completed"] = False
        gates["review_passed"] = False
        gates["test_passed"] = False
        gates["release_ready"] = False
    elif from_phase == "tasks":
        gates["tasks_confirmed"] = False
        gates["implementation_completed"] = False
        gates["review_passed"] = False
        gates["test_passed"] = False
        gates["release_ready"] = False


def main() -> None:
    parser = argparse.ArgumentParser(description="同步澄清带来的状态影响")
    parser.add_argument("--feature-dir", required=True, help="需求目录")
    parser.add_argument(
        "--impact",
        nargs="+",
        required=True,
        choices=IMPACT_CHOICES,
        help="本次澄清影响范围，可多选",
    )
    parser.add_argument("--source", default="用户澄清", help="澄清来源")
    parser.add_argument("--summary", required=True, help="澄清摘要")
    parser.add_argument("--mark-blockers-unresolved", action="store_true", help="标记本次澄清会重新打开阻塞问题")
    parser.add_argument("--business-model-changed", action="store_true", help="标记关键业务模型已变化")
    parser.add_argument("--upstream-contract-changed", action="store_true", help="标记关键上下游契约已变化")
    args = parser.parse_args()

    feature_dir = Path(args.feature_dir).resolve()
    meta_path = feature_dir / "meta.json"
    if not meta_path.exists():
        raise SystemExit("缺少 meta.json")
    if not (feature_dir / "00-baseline.md").exists():
        raise SystemExit("缺少 00-baseline.md，不能同步澄清影响")

    meta = load_meta(meta_path)
    gates, review_flags = ensure_defaults(meta)
    impacts = sorted(set(args.impact))
    phase = meta.get("current_phase", "需求受理")

    if "research" in impacts or "blocking" in impacts:
        review_flags["alignment_needs_review"] = True
        gates["alignment_completed"] = False
        bump_status(meta, "待澄清")

    if "design" in impacts:
        review_flags["design_needs_review"] = True
        reset_downstream_gates(gates, "design")
        bump_status(meta, "待重审")
        if phase_reached(phase, "任务拆分") and (feature_dir / "03-tasks.md").exists():
            review_flags["tasks_needs_review"] = True

    if "schema" in impacts:
        review_flags["design_needs_review"] = True
        reset_downstream_gates(gates, "design")
        bump_status(meta, "待重审")
        if phase_reached(phase, "任务拆分") and (feature_dir / "03-tasks.md").exists():
            review_flags["tasks_needs_review"] = True
    if "tasks" in impacts:
        review_flags["tasks_needs_review"] = True
        reset_downstream_gates(gates, "tasks")
        if phase_reached(phase, "任务拆分"):
            bump_status(meta, "待重审")

    if args.mark_blockers_unresolved:
        review_flags["alignment_needs_review"] = True
        gates["alignment_completed"] = False
        bump_status(meta, "待澄清")
        meta["blocking_issue_count"] = max(1, int(meta.get("blocking_issue_count", 0)))

    if args.business_model_changed:
        gates["business_model_confirmed"] = False
        reset_downstream_gates(gates, "design")
        review_flags["design_needs_review"] = True
        bump_status(meta, "待重审")

    if args.upstream_contract_changed:
        gates["upstream_contract_confirmed"] = False
        reset_downstream_gates(gates, "design")
        review_flags["design_needs_review"] = True
        bump_status(meta, "待重审")

    clarification = meta["clarification"]
    clarification["count"] = int(clarification.get("count", 0)) + 1
    clarification["last_source"] = args.source
    clarification["last_summary"] = args.summary
    clarification["last_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clarification["last_impacts"] = impacts

    save_meta(meta_path, meta)
    print("[OK] 已同步澄清影响")
    print(f"[OK] 影响范围: {', '.join(impacts)}")
    print(f"[OK] 当前状态: {meta.get('current_status', '')}")


if __name__ == "__main__":
    main()
