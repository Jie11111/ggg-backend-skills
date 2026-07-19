#!/usr/bin/env python3
"""根据需求目录内文档状态回填 meta.json。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workflow_validation as validator
from sync_clarification_impact import phase_reached, reopen_baseline_confirmation, reset_from_baseline


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="同步 meta.json 状态")
    parser.add_argument("--feature-dir", required=True, help="需求目录")
    args = parser.parse_args()

    feature_dir = Path(args.feature_dir).resolve()
    meta_path = feature_dir / "meta.json"
    if not meta_path.exists():
        raise SystemExit("缺少 meta.json")

    meta = load_json(meta_path)
    meta.pop("blocking_issue_count", None)
    research_path = feature_dir / "01-research.md"
    unresolved = 0
    if research_path.exists():
        unresolved = validator.unresolved_research_questions(research_path.read_text(encoding="utf-8"))
    if (feature_dir / "01-blocking-issues.md").exists():
        # 旧文件必须先合并迁移，避免切换单一账本后静默丢失阻塞问题。
        unresolved += 1
    phase = meta.get("current_phase", "需求受理")
    gates = meta.setdefault("gates", {})
    for key in [
        "clarification_required",
        "clarification_confirmed",
        "alignment_completed",
        "design_confirmed",
        "tasks_confirmed",
        "implementation_completed",
        "review_passed",
        "test_passed",
        "release_ready",
        "business_model_confirmed",
        "upstream_contract_confirmed",
        "schema_confirmed",
    ]:
        gates.setdefault(key, False)
    if int(meta.get("workflow_schema_version", 1)) >= 3:
        gates["clarification_required"] = True
    review_flags = validator.ensure_review_flags(meta)
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
        "confirmed_baseline_sha256": "",
        "baseline_confirmation_source": "",
        "baseline_confirmed_at": "",
    }.items():
        clarification.setdefault(key, value)

    schema_confirmation = meta.setdefault(
        "schema_confirmation",
        {"confirmed_schema_sha256": "", "confirmation_source": "", "confirmed_at": ""},
    )
    for key in ["confirmed_schema_sha256", "confirmation_source", "confirmed_at"]:
        schema_confirmation.setdefault(key, "")
    schema_path = feature_dir / "04-schema.sql"
    if gates.get("schema_confirmed"):
        current_schema_sha = validator.schema_fingerprint(validator.read_text(schema_path)) if schema_path.exists() else ""
        if not current_schema_sha or current_schema_sha != schema_confirmation.get("confirmed_schema_sha256", ""):
            gates["schema_confirmed"] = False
            schema_confirmation["confirmed_schema_sha256"] = ""
            schema_confirmation["confirmation_source"] = ""
            schema_confirmation["confirmed_at"] = ""
            gates["design_confirmed"] = False
            review_flags["design_needs_review"] = True

    clarification_required = bool(gates.get("clarification_required", False))
    baseline_path = feature_dir / "00-baseline.md"
    baseline_text = validator.read_text(baseline_path)
    current_fingerprint = validator.baseline_business_fingerprint(baseline_text) if baseline_text else ""
    confirmed_fingerprint = str(clarification.get("confirmed_baseline_sha256", "")).strip()

    if (
        clarification_required
        and gates.get("clarification_confirmed")
        and confirmed_fingerprint
        and current_fingerprint != confirmed_fingerprint
    ):
        reset_from_baseline(gates)
        gates["schema_confirmed"] = False
        schema_confirmation["confirmed_schema_sha256"] = ""
        schema_confirmation["confirmation_source"] = ""
        schema_confirmation["confirmed_at"] = ""
        reopen_baseline_confirmation(baseline_path)
        meta["current_status"] = "待澄清"
        if phase_reached(phase, "需求对齐"):
            review_flags["alignment_needs_review"] = True
            review_flags["design_needs_review"] = True
        if phase_reached(phase, "任务拆分"):
            review_flags["tasks_needs_review"] = True

    baseline_ready = not validator.validate_baseline_doc(
        baseline_path,
        clarification_gate_required=clarification_required,
    )
    if clarification_required:
        current_fingerprint = validator.baseline_business_fingerprint(validator.read_text(baseline_path))
        gates["clarification_confirmed"] = bool(
            baseline_ready
            and gates.get("clarification_confirmed")
            and confirmed_fingerprint
            and current_fingerprint == confirmed_fingerprint
        )
    research_text = validator.read_text(feature_dir / "01-research.md")
    research_ready = not validator.validate_research_doc(feature_dir / "01-research.md")
    design_ready = not validator.validate_design_doc(
        feature_dir / "02-design.md",
        feature_dir / "interface-details",
        validator.extract_claim_ids_from_research(research_text),
        validator.extract_design_eligible_claim_ids_from_research(research_text),
        validator.extract_transferred_design_question_ids_from_research(research_text),
    )
    tasks_ready = not validator.validate_tasks_doc(feature_dir / "03-tasks.md")
    implementation_log = feature_dir / "05-implementation-log.md"
    code_review = feature_dir / "06-code-review.md"
    test_report = feature_dir / "07-test-report.md"
    implementation_ready = implementation_log.exists() and not validator.validate_implementation_log(implementation_log)
    review_ready = code_review.exists() and not validator.validate_code_review_artifacts(code_review, feature_dir / "review-rounds")
    test_ready = test_report.exists() and not validator.validate_test_report_artifacts(test_report, feature_dir / "test-rounds")
    validator.sync_primary_project_from_baseline(meta, feature_dir / "00-baseline.md")

    if unresolved > 0 or review_flags.get("alignment_needs_review"):
        meta["current_status"] = "待澄清"
        gates["alignment_completed"] = False
    elif review_flags.get("design_needs_review") or review_flags.get("tasks_needs_review"):
        meta["current_status"] = "待重审"
    elif phase == "需求受理":
        meta["current_status"] = "已确认" if gates.get("clarification_confirmed") else "待澄清"
    elif phase == "需求对齐":
        meta["current_status"] = "已对齐" if baseline_ready and research_ready and unresolved == 0 else "调研中"
        gates["alignment_completed"] = meta["current_status"] == "已对齐"
        if gates["alignment_completed"]:
            review_flags["alignment_needs_review"] = False
    elif phase == "技术方案":
        meta["current_status"] = "已确认" if design_ready else "方案中"
    elif phase == "任务拆分":
        meta["current_status"] = "已确认" if tasks_ready else "拆分中"
        gates["tasks_confirmed"] = meta["current_status"] == "已确认"
    elif phase == "编码实现":
        if gates.get("implementation_completed"):
            meta["current_status"] = "已实现"
        else:
            meta["current_status"] = "编码中" if implementation_ready else "待编码"
    elif phase == "代码检查":
        if gates.get("review_passed"):
            meta["current_status"] = "已通过"
        else:
            meta["current_status"] = "检查中" if review_ready else "待检查"
    elif phase == "测试验证":
        if gates.get("test_passed"):
            meta["current_status"] = "已通过"
        else:
            meta["current_status"] = "验证中" if test_ready else "待验证"
    elif phase == "交付完成":
        meta["current_status"] = "已交付" if gates.get("release_ready") else "待交付"
    else:
        raise SystemExit(f"不支持的 current_phase: {phase}。{validator.current_scope_note()}")

    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] 已同步 meta.json，当前阻塞问题数: {unresolved}")


if __name__ == "__main__":
    main()
