#!/usr/bin/env python3
"""按硬门禁推进需求阶段，并按阶段解锁文档。"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workflow_validation as validator
import implementation_session
from workflow_contracts import PUBLIC_PHASES


PHASES = PUBLIC_PHASES
ALLOWED_SOURCE_PHASES = {
    "需求对齐": ["需求受理", "需求对齐"],
    "技术方案": ["需求对齐", "技术方案"],
    "任务拆分": ["技术方案", "任务拆分"],
    "编码实现": ["任务拆分", "编码实现"],
    "代码检查": ["编码实现", "代码检查"],
    # Review 是可选分支；实现完成后可直接进入测试验证。
    "测试验证": ["编码实现", "代码检查", "测试验证"],
    "交付完成": ["测试验证", "交付完成"],
}
SCHEMA_TEMPLATE = """-- GGG_SQL_SCHEMA_VERSION: 3
-- 变更目标:
-- 来源Cxx:
-- 来源Dxx:
-- SQL参考表:
-- SQL参考证据:
-- 最小变更结论:
-- 现有结构复用评估:
-- 核心写入:
-- 核心查询:
-- 索引/约束依据:
-- 数据规模与DDL风险:
-- 执行前备份:
-- 回滚方式:
-- 验证SQL:

-- 每条结构 DDL 前保留一条 GGG_DDL_OBJECT；members 必须完整列出真实字段、索引和约束。
-- GGG_DDL_OBJECT: {"object":"","operation":"","members":[],"risk":"","risk_reason":"","claims":[],"designs":[]}

"""


def load_meta(feature_dir: Path) -> dict:
    meta_path = feature_dir / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError("缺少 meta.json，不能推进阶段")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def save_meta(feature_dir: Path, meta: dict) -> None:
    meta.pop("blocking_issue_count", None)
    (feature_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def detect_repo_root(feature_dir: Path) -> Path:
    current = feature_dir.resolve()
    for parent in [current] + list(current.parents):
        if (parent / "ggg").exists():
            return parent
    raise FileNotFoundError("未找到仓库根目录")


def detect_workflow_root(repo_root: Path) -> Path:
    for relative in [Path("ggg/workflow"), Path("ggg/tech-workflow")]:
        candidate = repo_root / relative
        if (candidate / "templates").exists():
            return candidate
    raise FileNotFoundError("未找到工作流模板目录")


def copy_if_missing(src: Path, dst: Path) -> None:
    if not dst.exists():
        shutil.copyfile(src, dst)


def assert_transition_allowed(current_phase: str, target_phase: str) -> None:
    if target_phase not in PHASES:
        raise SystemExit(f"不支持推进到 {target_phase}。{validator.current_scope_note()}。")

    allowed_phases = ALLOWED_SOURCE_PHASES[target_phase]
    if current_phase in allowed_phases:
        return

    if current_phase not in PHASES:
        raise SystemExit(f"meta.json.current_phase 非法或缺失: {current_phase}")

    if PHASES.index(current_phase) > PHASES.index(target_phase):
        raise SystemExit(
            f"当前阶段为 {current_phase}，不能直接重新推进到 {target_phase}。"
            "如需回写旧结论，请在当前阶段按用户确认结果更新对应文档，并重新完成校验。"
        )

    allowed_text = " 或 ".join(allowed_phases)
    raise SystemExit(f"当前阶段为 {current_phase}，只有从 {allowed_text} 才能进入 {target_phase}")


def fail_with_validation_errors(errors: list[str], action_text: str) -> None:
    if not errors:
        return
    print(f"[FAIL] {action_text}")
    for error in errors:
        print(f"- {error}")
    raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="推进需求阶段")
    parser.add_argument("--feature-dir", required=True, help="需求目录")
    parser.add_argument("--to-phase", required=True, choices=PHASES, help="目标阶段")
    parser.add_argument("--design-confirmed", action="store_true", help="推进到任务拆分时标记方案已确认")
    parser.add_argument("--tasks-confirmed", action="store_true", help="推进到编码实现时标记任务拆分已确认")
    parser.add_argument("--implementation-completed", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--review-disposition", choices=["light", "formal"], help=argparse.SUPPRESS)
    parser.add_argument("--review-passed", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--review-gate-satisfied", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--test-passed", action="store_true", help="旧命令兼容参数；新版使用 test-mark 登记测试结论")
    parser.add_argument("--business-model-confirmed", action="store_true", help="允许生成 schema 的前提：业务模型已确认")
    parser.add_argument("--upstream-contract-confirmed", action="store_true", help="允许生成 schema 的前提：上下游契约已确认")
    parser.add_argument("--create-schema", action="store_true", help="推进到技术方案阶段时创建 04-schema.sql")
    args = parser.parse_args()

    feature_dir = Path(args.feature_dir).resolve()
    repo_root = detect_repo_root(feature_dir)
    workflow_root = detect_workflow_root(repo_root)
    meta = load_meta(feature_dir)
    workflow_schema_version = int(meta.get("workflow_schema_version", 1))
    templates_dir = (
        Path(__file__).resolve().parent.parent / "assets" / "workflow" / "templates"
        if int(meta.get("workflow_schema_version", 1)) >= 3
        else workflow_root / "templates"
    )
    review_flags = validator.ensure_review_flags(meta)

    target_phase = args.to_phase
    current_phase = meta.get("current_phase", "")
    assert_transition_allowed(current_phase, target_phase)

    if target_phase == "需求对齐":
        if current_phase == "需求受理":
            validation_errors = validator.validate_feature_dir(feature_dir)
            fail_with_validation_errors(validation_errors, "当前需求在进入需求对齐前未通过 baseline 门禁")
            if not meta.get("gates", {}).get("clarification_confirmed"):
                raise SystemExit("baseline 尚未完成用户最终确认，不能进入需求对齐阶段")
        copy_if_missing(templates_dir / "requirement-research-template.md", feature_dir / "01-research.md")
        meta["current_phase"] = "需求对齐"
        meta["current_status"] = "调研中"

    elif target_phase == "技术方案":
        if workflow_schema_version >= 5 and args.create_schema:
            raise SystemExit(
                "新版流程不在技术方案阶段首次创建 SQL；"
                "请回到需求对齐填写 sql-draft.sql 并执行 confirm-sql"
            )
        if current_phase == "需求对齐" and args.create_schema:
            raise SystemExit("请先进入技术方案并完成 02-design.md 预检，再重新执行 --create-schema")
        if current_phase == "技术方案" and args.create_schema:
            research_text = validator.read_text(feature_dir / "01-research.md")
            precheck_errors = validator.validate_design_precheck(
                feature_dir / "02-design.md",
                validator.extract_design_eligible_claim_ids_from_research(research_text),
                validator.extract_transferred_design_question_ids_from_research(research_text),
            )
            fail_with_validation_errors(precheck_errors, "创建 04-schema.sql 前设计预检未通过")
        else:
            validation_errors = validator.validate_feature_dir(feature_dir)
            fail_with_validation_errors(validation_errors, "当前需求在进入技术方案前未通过校验")
        if review_flags.get("alignment_needs_review"):
            raise SystemExit("需求对齐结果待重审，不能进入技术方案阶段")
        if workflow_schema_version >= 5 and not meta.get("gates", {}).get("sql_confirmed"):
            raise SystemExit(
                "SQL Gate 尚未完成；查询、DML、DDL 或“无 SQL”都必须先执行 confirm-sql"
            )

        research_text = (feature_dir / "01-research.md").read_text(encoding="utf-8")
        unresolved = validator.unresolved_research_questions(research_text)
        if unresolved > 0:
            raise SystemExit("01-research.md 疑问账本未清空，不能进入技术方案阶段")

        copy_if_missing(templates_dir / "technical-design-template.md", feature_dir / "02-design.md")
        if args.create_schema:
            if not (args.business_model_confirmed and args.upstream_contract_confirmed):
                raise SystemExit("生成 04-schema.sql 前必须确认关键业务模型和关键上下游契约")
            schema_path = feature_dir / "04-schema.sql"
            if not schema_path.exists() or not schema_path.read_text(encoding="utf-8").strip():
                schema_path.write_text(SCHEMA_TEMPLATE, encoding="utf-8")
            meta.setdefault("gates", {})["business_model_confirmed"] = True
            meta["gates"]["upstream_contract_confirmed"] = True
            meta["gates"]["schema_confirmed"] = False
            meta.setdefault("schema_confirmation", {})["confirmed_schema_sha256"] = ""
            meta["schema_confirmation"]["confirmation_source"] = ""
            meta["schema_confirmation"]["confirmed_at"] = ""

        meta.setdefault("gates", {})["alignment_completed"] = True
        review_flags["alignment_needs_review"] = False
        review_flags["design_needs_review"] = False
        meta["current_phase"] = "技术方案"
        meta["current_status"] = "方案中"

    elif target_phase == "任务拆分":
        if not args.design_confirmed:
            raise SystemExit("推进到任务拆分阶段必须显式确认 design 已通过")

        validation_errors = validator.validate_feature_dir(feature_dir)
        fail_with_validation_errors(validation_errors, "当前需求在进入任务拆分前未通过校验")
        if review_flags.get("alignment_needs_review") or review_flags.get("design_needs_review"):
            raise SystemExit("技术方案仍存在待重审内容，不能进入任务拆分阶段")

        copy_if_missing(templates_dir / "task-breakdown-template.md", feature_dir / "03-tasks.md")
        meta.setdefault("gates", {})["design_confirmed"] = True
        review_flags["design_needs_review"] = False
        review_flags["tasks_needs_review"] = False
        meta["current_phase"] = "任务拆分"
        meta["current_status"] = "拆分中"

    elif target_phase == "编码实现":
        if not args.tasks_confirmed:
            raise SystemExit("推进到编码实现阶段必须显式确认 tasks 已通过")

        validation_errors = validator.validate_feature_dir(feature_dir)
        fail_with_validation_errors(validation_errors, "当前需求在进入编码实现前未通过校验")
        if review_flags.get("alignment_needs_review") or review_flags.get("design_needs_review") or review_flags.get("tasks_needs_review"):
            raise SystemExit("任务拆分仍存在待重审内容，不能进入编码实现阶段")

        copy_if_missing(templates_dir / "implementation-log-template.md", feature_dir / "05-implementation-log.md")
        meta.setdefault("gates", {})["tasks_confirmed"] = True
        meta["gates"]["implementation_completed"] = False
        meta["gates"].pop("review_passed", None)
        meta["gates"].pop("review_gate_satisfied", None)
        meta.pop("review_disposition", None)
        meta["review_status"] = "not_run"
        meta["gates"]["test_passed"] = False
        meta["gates"]["release_ready"] = False
        meta["current_phase"] = "编码实现"
        meta["current_status"] = "编码中"

    elif target_phase == "代码检查":
        implementation_log = feature_dir / "05-implementation-log.md"
        if not implementation_log.exists():
            raise SystemExit("缺少 05-implementation-log.md，不能进入代码检查阶段")
        implementation_state = implementation_session.load_state(implementation_log)
        if implementation_state.get("status") != "completed":
            raise SystemExit("实现会话尚未完成，不能进入代码检查阶段")
        current_snapshot = implementation_session.current_snapshot(implementation_state)
        completed_snapshot = implementation_state.get("completion_snapshot") or {}
        if current_snapshot.get("fingerprint") != completed_snapshot.get("fingerprint"):
            raise SystemExit("实现完成后代码又发生变化；请重新开启 implementation 轮次并完成质量门禁")
        completion_errors = validator.validate_implementation_completion(implementation_log)
        fail_with_validation_errors(completion_errors, "编码实现质量门禁未通过")
        copy_if_missing(templates_dir / "code-review-index-template.md", feature_dir / "06-code-review.md")
        review_report = feature_dir / "06-code-review.md"
        if validator.review_schema_version(review_report.read_text(encoding="utf-8")) < 2:
            raise SystemExit("06-code-review.md 是旧版复杂 Review 工件；请保留历史文件并改用新版模板")
        implementation_session.update_record_line(
            review_report,
            "- 对应实现轮次：",
            implementation_state.get("round", ""),
        )
        implementation_session.update_record_line(
            review_report,
            "- 实现差异指纹：",
            current_snapshot.get("fingerprint", ""),
        )
        meta.setdefault("gates", {})["implementation_completed"] = True
        meta["gates"].pop("review_passed", None)
        meta["gates"].pop("review_gate_satisfied", None)
        meta.pop("review_disposition", None)
        meta["review_status"] = "in_progress"
        meta["gates"]["test_passed"] = False
        meta["gates"]["release_ready"] = False
        meta["current_phase"] = "代码检查"
        meta["current_status"] = "检查中"

    elif target_phase == "测试验证":
        implementation_log = feature_dir / "05-implementation-log.md"
        if not implementation_log.exists():
            raise SystemExit("缺少 05-implementation-log.md，不能进入测试验证阶段")
        implementation_state = implementation_session.load_state(implementation_log)
        if implementation_state.get("status") != "completed":
            raise SystemExit("实现会话尚未完成，不能进入测试验证阶段")
        current_snapshot = implementation_session.current_snapshot(implementation_state)
        completed_snapshot = implementation_state.get("completion_snapshot") or {}
        if current_snapshot.get("fingerprint") != completed_snapshot.get("fingerprint"):
            raise SystemExit("实现完成后代码又发生变化；请重新完成 implementation 轮次")
        completion_errors = validator.validate_implementation_completion(implementation_log)
        fail_with_validation_errors(completion_errors, "编码实现质量门禁未通过")
        validation_errors = validator.validate_feature_dir(feature_dir)
        fail_with_validation_errors(validation_errors, "当前需求在进入测试验证前未通过校验")

        copy_if_missing(templates_dir / "test-report-index-template.md", feature_dir / "07-test-report.md")
        (feature_dir / "test-rounds").mkdir(exist_ok=True)
        meta.setdefault("gates", {})["implementation_completed"] = True
        meta["gates"].pop("review_passed", None)
        meta["gates"].pop("review_gate_satisfied", None)
        meta.pop("review_disposition", None)
        meta["gates"]["test_passed"] = False
        meta["gates"]["release_ready"] = False
        meta["current_phase"] = "测试验证"
        meta["current_status"] = "验证中"

    elif target_phase == "交付完成":
        raise SystemExit(
            "GGG 流程止于测试验证，不自动推进交付或发布。"
            "请使用 workflow_cli.py test-mark --record <05-implementation-log.md> --result passed "
            "登记测试结论。"
        )

    save_meta(feature_dir, meta)
    print(f"[OK] 已推进到阶段: {target_phase}")


if __name__ == "__main__":
    main()
