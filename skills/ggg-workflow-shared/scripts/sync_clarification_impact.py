#!/usr/bin/env python3
"""根据新增澄清同步需求状态、重审标记与门禁状态。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from workflow_contracts import PUBLIC_PHASES, REVIEW_FLAG_KEYS


IMPACT_CHOICES = ["baseline", "research", "sql", "design", "schema", "tasks"]
STATUS_PRIORITY = {
    "待重审": 1,
    "待澄清": 2,
}


def load_meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_meta(path: Path, meta: dict) -> None:
    meta.pop("blocking_issue_count", None)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_defaults(meta: dict) -> tuple[dict, dict]:
    gate_defaults = {
        # 旧需求目录默认不强制新版澄清门禁；一旦发生 baseline 变更会在 main 中升级并开启。
        "clarification_required": False,
        "clarification_confirmed": False,
        "alignment_completed": False,
        "design_confirmed": False,
        "tasks_confirmed": False,
        "implementation_completed": False,
        "test_passed": False,
        "release_ready": False,
        "business_model_confirmed": False,
        "upstream_contract_confirmed": False,
        "schema_confirmed": False,
        "sql_confirmed": False,
    }
    gates = meta.setdefault(
        "gates",
        gate_defaults.copy(),
    )
    for key, value in gate_defaults.items():
        gates.setdefault(key, value)
    if int(meta.get("workflow_schema_version", 1)) >= 3:
        gates["clarification_required"] = True
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
    clarification = meta.setdefault(
        "clarification",
        {
            "count": 0,
            "last_source": "",
            "last_summary": "",
            "last_updated_at": "",
            "last_impacts": [],
            "confirmed_baseline_sha256": "",
            "baseline_confirmation_source": "",
            "baseline_confirmed_at": "",
        },
    )
    for key, value in {
        "count": 0,
        "last_source": "",
        "last_summary": "",
        "last_updated_at": "",
        "last_impacts": [],
        "confirmed_baseline_sha256": "",
        "baseline_confirmation_source": "",
        "baseline_confirmed_at": "",
    }.items():
        clarification.setdefault(key, value)
    return gates, review_flags


def reset_schema_confirmation(meta: dict, gates: dict) -> None:
    gates["schema_confirmed"] = False
    confirmation = meta.setdefault("schema_confirmation", {})
    confirmation["confirmed_schema_sha256"] = ""
    confirmation["confirmation_source"] = ""
    confirmation["confirmed_at"] = ""


def reset_sql_confirmation(meta: dict, gates: dict) -> None:
    gates["sql_confirmed"] = False
    confirmation = meta.setdefault("sql_confirmation", {})
    confirmation["impact_type"] = ""
    confirmation["research_semantic_fingerprint"] = ""
    confirmation["draft_semantic_fingerprint"] = ""
    confirmation["semantic_fingerprint"] = ""
    confirmation["confirmation_source"] = ""
    confirmation["confirmed_at"] = ""


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
        gates["test_passed"] = False
        gates["release_ready"] = False
    elif from_phase == "tasks":
        gates["tasks_confirmed"] = False
        gates["implementation_completed"] = False
        gates["test_passed"] = False
        gates["release_ready"] = False


def reopen_baseline_confirmation(baseline_path: Path) -> None:
    """将已确认 baseline 回退到澄清中；不伪造新的疑问或用户结论。"""
    text = baseline_path.read_text(encoding="utf-8")
    status_line = "- 基线状态：澄清中"
    confirmation_line = "- 最终反向确认：待确认"

    if re.search(r"(?m)^- 基线状态：.*$", text):
        text = re.sub(r"(?m)^- 基线状态：.*$", status_line, text, count=1)
    else:
        text = re.sub(r"(?m)^(- 当前阶段：.*)$", rf"\1\n{status_line}", text, count=1)

    if re.search(r"(?m)^- 最终反向确认：.*$", text):
        text = re.sub(r"(?m)^- 最终反向确认：.*$", confirmation_line, text, count=1)
    else:
        text = re.sub(r"(?m)^(- 基线状态：.*)$", rf"\1\n{confirmation_line}", text, count=1)

    baseline_path.write_text(text, encoding="utf-8")


def reset_from_baseline(gates: dict) -> None:
    gates["clarification_required"] = True
    gates["clarification_confirmed"] = False
    gates["alignment_completed"] = False
    gates["design_confirmed"] = False
    gates["tasks_confirmed"] = False
    gates["implementation_completed"] = False
    gates["test_passed"] = False
    gates["release_ready"] = False
    gates["business_model_confirmed"] = False
    gates["upstream_contract_confirmed"] = False
    gates["schema_confirmed"] = False
    gates["sql_confirmed"] = False


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
    schema_confirmation = meta.setdefault("schema_confirmation", {})
    for key in ["confirmed_schema_sha256", "confirmation_source", "confirmed_at"]:
        schema_confirmation.setdefault(key, "")
    sql_confirmation = meta.setdefault("sql_confirmation", {})
    for key in [
        "impact_type",
        "research_semantic_fingerprint",
        "draft_semantic_fingerprint",
        "semantic_fingerprint",
        "confirmation_source",
        "confirmed_at",
    ]:
        sql_confirmation.setdefault(key, "")
    impacts = sorted(set(args.impact))
    phase = meta.get("current_phase", "需求受理")

    if "baseline" in impacts:
        baseline_text = (feature_dir / "00-baseline.md").read_text(encoding="utf-8")
        marker = re.search(r"<!--\s*GGG_SCHEMA_VERSION:\s*(\d+)\s*-->", baseline_text)
        baseline_schema_version = int(marker.group(1)) if marker else 1
        if int(meta.get("workflow_schema_version", 1)) < 3 and baseline_schema_version < 3:
            raise SystemExit("旧版 baseline 尚未迁移到新版 schema，不能直接开启澄清门禁；请先按最新模板迁移并保留原有结论")
        meta["workflow_schema_version"] = max(3, baseline_schema_version, int(meta.get("workflow_schema_version", 1)))
        reset_from_baseline(gates)
        reset_schema_confirmation(meta, gates)
        reset_sql_confirmation(meta, gates)
        reopen_baseline_confirmation(feature_dir / "00-baseline.md")
        clarification = meta["clarification"]
        clarification["confirmed_baseline_sha256"] = ""
        clarification["baseline_confirmation_source"] = ""
        clarification["baseline_confirmed_at"] = ""
        bump_status(meta, "待澄清")
        if phase_reached(phase, "需求对齐"):
            review_flags["alignment_needs_review"] = True
            review_flags["design_needs_review"] = True
        if phase_reached(phase, "任务拆分") and (feature_dir / "03-tasks.md").exists():
            review_flags["tasks_needs_review"] = True

    if "research" in impacts:
        review_flags["alignment_needs_review"] = True
        gates["alignment_completed"] = False
        reset_schema_confirmation(meta, gates)
        reset_sql_confirmation(meta, gates)
        bump_status(meta, "待澄清")

    if "design" in impacts:
        review_flags["design_needs_review"] = True
        reset_downstream_gates(gates, "design")
        reset_schema_confirmation(meta, gates)
        bump_status(meta, "待重审")
        if phase_reached(phase, "任务拆分") and (feature_dir / "03-tasks.md").exists():
            review_flags["tasks_needs_review"] = True

    if "schema" in impacts:
        review_flags["design_needs_review"] = True
        reset_downstream_gates(gates, "design")
        reset_schema_confirmation(meta, gates)
        reset_sql_confirmation(meta, gates)
        bump_status(meta, "待重审")
        if phase_reached(phase, "任务拆分") and (feature_dir / "03-tasks.md").exists():
            review_flags["tasks_needs_review"] = True
    if "sql" in impacts:
        review_flags["design_needs_review"] = True
        reset_downstream_gates(gates, "design")
        reset_sql_confirmation(meta, gates)
        bump_status(meta, "待重审")
        if phase_reached(phase, "任务拆分") and (feature_dir / "03-tasks.md").exists():
            review_flags["tasks_needs_review"] = True
    if "tasks" in impacts:
        review_flags["tasks_needs_review"] = True
        reset_downstream_gates(gates, "tasks")
        if phase_reached(phase, "任务拆分"):
            bump_status(meta, "待重审")

    if args.business_model_changed:
        gates["business_model_confirmed"] = False
        reset_schema_confirmation(meta, gates)
        reset_sql_confirmation(meta, gates)
        reset_downstream_gates(gates, "design")
        review_flags["design_needs_review"] = True
        bump_status(meta, "待重审")

    if args.upstream_contract_changed:
        gates["upstream_contract_confirmed"] = False
        reset_schema_confirmation(meta, gates)
        reset_sql_confirmation(meta, gates)
        reset_downstream_gates(gates, "design")
        review_flags["design_needs_review"] = True
        bump_status(meta, "待重审")

    clarification = meta["clarification"]
    clarification["count"] = int(clarification.get("count", 0)) + 1
    clarification["last_source"] = args.source
    clarification["last_summary"] = args.summary
    clarification["last_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clarification["last_impacts"] = impacts

    gates.pop("review_passed", None)
    gates.pop("review_gate_satisfied", None)
    meta.pop("review_disposition", None)
    if phase_reached(phase, "编码实现"):
        meta["review_status"] = "stale"

    save_meta(meta_path, meta)
    print("[OK] 已同步澄清影响")
    print(f"[OK] 影响范围: {', '.join(impacts)}")
    print(f"[OK] 当前状态: {meta.get('current_status', '')}")


if __name__ == "__main__":
    main()
