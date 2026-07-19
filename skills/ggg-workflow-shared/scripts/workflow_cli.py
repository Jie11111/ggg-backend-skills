#!/usr/bin/env python3
"""PRD 工作流统一命令入口。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def run_script(script_name: str, extra_args: list[str]) -> int:
    script_path = SCRIPT_DIR / script_name
    command = [sys.executable, str(script_path), *extra_args]
    completed = subprocess.run(command, check=False)
    return completed.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="PRD 工作流统一命令入口")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="初始化需求目录，只生成 meta.json 和 00-baseline.md")
    init_parser.add_argument(
        "--repo-root",
        help="项目根目录；默认当前 Git 仓库根目录，非 Git 目录时使用当前目录",
    )
    init_parser.add_argument("--feature-name", required=True, help="需求名称")
    init_parser.add_argument("--date", help="目录日期，格式 YYYYMMDD")
    init_parser.add_argument("--refresh-workflow-assets", action="store_true", help="覆盖同步 ggg/workflow 下的共享 README 和模板")

    quick_parser = subparsers.add_parser("init-quick", help="在统一 ggg/features 目录初始化 quick 记录")
    quick_parser.add_argument(
        "--repo-root",
        help="项目根目录；默认当前 Git 仓库根目录，非 Git 目录时使用当前目录",
    )
    quick_parser.add_argument("--quick-name", required=True, help="quick 小需求名称")
    quick_parser.add_argument("--date", help="目录日期，格式 YYYYMMDD")
    quick_parser.add_argument("--create-schema", action="store_true", help="按需创建 04-schema.sql")
    quick_parser.add_argument("--interface-name", action="append", default=[], help="按需创建接口明细，可重复")

    align_parser = subparsers.add_parser("to-alignment", help="推进到需求对齐阶段，解锁 01-research.md")
    align_parser.add_argument("--feature-dir", required=True, help="需求目录")

    sync_parser = subparsers.add_parser("sync-meta", help="根据当前文档同步 meta.json")
    sync_parser.add_argument("--feature-dir", required=True, help="需求目录")

    confirm_baseline_parser = subparsers.add_parser("confirm-baseline", help="用户最终确认后锁定 baseline 业务指纹")
    confirm_baseline_parser.add_argument("--feature-dir", required=True, help="需求目录")
    confirm_baseline_parser.add_argument("--source", required=True, help="用户最终确认的消息定位或时间")

    confirm_schema_parser = subparsers.add_parser("confirm-schema", help="用户确认 SQL 后锁定 04-schema.sql 内容指纹")
    confirm_schema_parser.add_argument("--feature-dir", required=True, help="需求目录")
    confirm_schema_parser.add_argument("--source", required=True, help="用户确认 SQL 的消息定位或时间")

    validate_parser = subparsers.add_parser("validate", help="按当前阶段校验需求目录")
    validate_parser.add_argument("--feature-dir", required=True, help="需求目录")

    quality_parser = subparsers.add_parser("quality-gate", help="验证 full/quick 的任务完成、代码质量和验证证据")
    quality_parser.add_argument("--record", required=True, help="05-implementation-log.md 或 quick.md 路径")

    implementation_start_parser = subparsers.add_parser(
        "implementation-start",
        help="编码前开启实现会话，记录一个或多个 Git 仓库的基线",
    )
    implementation_start_parser.add_argument("--record", required=True, help="05-implementation-log.md 或 quick.md 路径")
    implementation_start_parser.add_argument(
        "--repo-root",
        action="append",
        required=True,
        help="本轮涉及的 Git 仓库根目录；跨仓需求重复传入",
    )
    implementation_start_parser.add_argument(
        "--risk-profile",
        choices=["tiny", "normal", "high"],
        default="normal",
        help="实现预检档位；默认 normal",
    )
    implementation_start_parser.add_argument(
        "--adopt-existing-file",
        action="append",
        default=[],
        help="接管启动前已属于本需求的 Git 脏文件；单仓可用相对路径，多仓必须用绝对路径，可重复",
    )
    implementation_start_parser.add_argument(
        "--task",
        action="append",
        default=[],
        help="本轮要实现的 Txx，可重复；full 默认选择全部编码任务",
    )

    implementation_precheck_parser = subparsers.add_parser(
        "implementation-precheck",
        help="在新增代码修改前校验并锁定本轮轻量实现草图",
    )
    implementation_precheck_parser.add_argument(
        "--record",
        required=True,
        help="05-implementation-log.md 或 quick.md 路径",
    )

    implementation_verify_parser = subparsers.add_parser(
        "implementation-verify",
        help="执行验证命令，并把退出码与输出摘要绑定到当前代码快照",
    )
    implementation_verify_parser.add_argument(
        "--record",
        required=True,
        help="05-implementation-log.md 或 quick.md 路径",
    )
    implementation_verify_parser.add_argument("--cwd", help="验证命令工作目录；默认第一个已声明仓库")
    implementation_verify_parser.add_argument("--label", help="验证用途，例如 compile、unit-test")
    implementation_verify_parser.add_argument(
        "verification_command",
        nargs=argparse.REMAINDER,
        help="在 -- 后传入命令及参数；命令不会经 shell 执行",
    )

    implementation_restart_parser = subparsers.add_parser(
        "implementation-restart",
        help="当前轮次无法继续时保留现有差异并轻量重开下一实现轮次",
    )
    implementation_restart_parser.add_argument(
        "--record",
        required=True,
        help="05-implementation-log.md 或 quick.md 路径",
    )
    implementation_restart_parser.add_argument(
        "--reason",
        required=True,
        help="重开原因，例如旧会话已有代码或核心实现草图已变化",
    )

    implementation_complete_parser = subparsers.add_parser(
        "implementation-complete",
        help="基于真实 Git 差异执行实现质量门禁并锁定完成快照",
    )
    implementation_complete_parser.add_argument("--record", required=True, help="05-implementation-log.md 或 quick.md 路径")
    implementation_complete_parser.add_argument(
        "--verification-waiver",
        help="确因环境阻塞无法执行验证时，显式记录未验证原因",
    )

    implementation_status_parser = subparsers.add_parser(
        "implementation-status",
        help="检查实现完成快照是否仍与当前代码一致",
    )
    implementation_status_parser.add_argument("--record", required=True, help="05-implementation-log.md 或 quick.md 路径")

    review_mark_parser = subparsers.add_parser(
        "review-mark",
        help="将 Review 结论及评审方式绑定到当前实现轮次和差异指纹",
    )
    review_mark_parser.add_argument("--record", required=True, help="05-implementation-log.md 或 quick.md 路径")
    review_mark_parser.add_argument("--result", required=True, choices=["passed", "needs_changes", "blocked"])
    review_mark_parser.add_argument(
        "--reviewer-mode",
        choices=["fresh-review", "self-review"],
        help=(
            "明确本轮是否由无实现历史的 fresh reviewer 执行；"
            "旧调用省略时安全降级为 self-review"
        ),
    )
    review_mark_parser.add_argument(
        "--self-review-reason",
        help="仅 self-review 必填：fresh reviewer 不可用或启动失败的具体原因",
    )

    review_status_parser = subparsers.add_parser(
        "review-status",
        help="检查 Review 结论是否仍对应当前实现差异",
    )
    review_status_parser.add_argument("--record", required=True, help="05-implementation-log.md 或 quick.md 路径")
    review_status_parser.add_argument("--require-passed", action="store_true")

    test_run_parser = subparsers.add_parser(
        "test-run",
        help="无 shell 执行自动化测试，并生成绑定当前实现、Review 和 TSxx 的机器证据",
    )
    test_run_parser.add_argument("--record", required=True, help="05-implementation-log.md 或 quick.md 路径")
    test_run_parser.add_argument("--round", required=True, help="当前测试轮次 Txx；quick 使用 quick")
    test_run_parser.add_argument("--scenario", required=True, help="当前测试轮次中已规划的 TSxx")
    test_run_parser.add_argument("--cwd", help="命令工作目录；必须位于实现阶段声明的仓库内")
    test_run_parser.add_argument("--environment", required=True, help="可复查的环境/版本标签")
    test_run_parser.add_argument(
        "--effect",
        required=True,
        choices=[
            "read-only",
            "local-write",
            "data-write",
            "state-change",
            "message-or-job",
            "external-side-effect",
        ],
    )
    test_run_parser.add_argument(
        "--effect-authorization",
        help="data-write 及更高副作用命令的用户授权定位",
    )
    test_run_parser.add_argument("--timeout-seconds", type=int, default=300)
    test_run_parser.add_argument(
        "test_command",
        nargs=argparse.REMAINDER,
        help="在 -- 后传入命令及参数；不会经 shell 执行",
    )

    test_mark_parser = subparsers.add_parser(
        "test-mark",
        help="校验测试场景和证据，并将测试结论绑定到当前实现差异",
    )
    test_mark_parser.add_argument("--record", required=True, help="05-implementation-log.md 或 quick.md 路径")
    test_mark_parser.add_argument("--result", required=True, choices=["passed", "needs_more", "blocked"])

    test_status_parser = subparsers.add_parser(
        "test-status",
        help="检查测试结论是否仍对应当前实现差异和测试记录",
    )
    test_status_parser.add_argument("--record", required=True, help="05-implementation-log.md 或 quick.md 路径")
    test_status_parser.add_argument("--require-passed", action="store_true")

    scan_parser = subparsers.add_parser("scan-design-inputs", help="在已确认的目标项目或模块内扫描入口和依赖候选")
    scan_parser.add_argument("--scope-root", required=True, help="已确认的目标项目或模块目录")
    scan_parser.add_argument("--max-files", type=int, default=500, help="实际纳入扫描的文件上限")
    scan_parser.add_argument("--max-depth", type=int, default=8, help="目录深度上限")
    scan_parser.add_argument("--limit", type=int, default=20, help="每类结果最多输出多少行")

    design_parser = subparsers.add_parser("to-design", help="进入技术方案；完成预检后可按需创建 04-schema.sql")
    design_parser.add_argument("--feature-dir", required=True, help="需求目录")
    design_parser.add_argument("--create-schema", action="store_true", help="同时创建 04-schema.sql")
    design_parser.add_argument("--business-model-confirmed", action="store_true", help="确认关键业务模型")
    design_parser.add_argument("--upstream-contract-confirmed", action="store_true", help="确认关键上下游契约")

    tasks_parser = subparsers.add_parser("to-tasks", help="推进到任务拆分阶段，解锁 03-tasks.md")
    tasks_parser.add_argument("--feature-dir", required=True, help="需求目录")
    tasks_parser.add_argument("--design-confirmed", action="store_true", help="确认技术方案已通过")

    implementation_parser = subparsers.add_parser("to-implementation", help="推进到编码实现阶段，解锁 05-implementation-log.md")
    implementation_parser.add_argument("--feature-dir", required=True, help="需求目录")
    implementation_parser.add_argument("--tasks-confirmed", action="store_true", help="确认任务拆分已通过")

    review_parser = subparsers.add_parser("to-review", help="推进到代码检查阶段，解锁 06-code-review.md")
    review_parser.add_argument("--feature-dir", required=True, help="需求目录")
    review_parser.add_argument("--implementation-completed", action="store_true", help="确认编码实现已完成")

    test_parser = subparsers.add_parser("to-test", help="推进到测试验证阶段，解锁 07-test-report.md")
    test_parser.add_argument("--feature-dir", required=True, help="需求目录")
    test_parser.add_argument("--review-passed", action="store_true", help="确认代码检查已通过")

    complete_parser = subparsers.add_parser(
        "complete",
        help="兼容旧命令：登记测试通过；流程停在测试验证，不声明交付或发布就绪",
    )
    complete_parser.add_argument("--feature-dir", required=True, help="需求目录")
    complete_parser.add_argument("--test-passed", action="store_true", help="确认测试验证已通过")

    clarify_parser = subparsers.add_parser("sync-clarification", help="同步新增澄清的影响到 meta.json")
    clarify_parser.add_argument("--feature-dir", required=True, help="需求目录")
    clarify_parser.add_argument("--impact", nargs="+", required=True,
                                choices=["baseline", "research", "design", "schema", "tasks"],
                                help="本次澄清影响范围，可多选")
    clarify_parser.add_argument("--source", default="用户澄清", help="澄清来源")
    clarify_parser.add_argument("--summary", required=True, help="澄清摘要")
    clarify_parser.add_argument("--business-model-changed", action="store_true", help="标记关键业务模型已变化")
    clarify_parser.add_argument("--upstream-contract-changed", action="store_true", help="标记关键上下游契约已变化")

    status_parser = subparsers.add_parser("status", help="查看需求当前状态看板")
    status_parser.add_argument("--feature-dir", required=True, help="需求目录")

    reset_parser = subparsers.add_parser("reset", help="回退到指定阶段")
    reset_parser.add_argument("--feature-dir", required=True, help="需求目录")
    reset_parser.add_argument("--to-phase", required=True, help="目标阶段")

    args = parser.parse_args()

    if args.command == "init":
        extra_args = ["--feature-name", args.feature_name]
        if args.repo_root:
            extra_args.extend(["--repo-root", args.repo_root])
        if args.date:
            extra_args.extend(["--date", args.date])
        if args.refresh_workflow_assets:
            extra_args.append("--refresh-workflow-assets")
        code = run_script("init_feature_docs.py", extra_args)
    elif args.command == "init-quick":
        extra_args = ["--quick-name", args.quick_name]
        if args.repo_root:
            extra_args.extend(["--repo-root", args.repo_root])
        if args.date:
            extra_args.extend(["--date", args.date])
        if args.create_schema:
            extra_args.append("--create-schema")
        for interface_name in args.interface_name:
            extra_args.extend(["--interface-name", interface_name])
        code = run_script("init_quick_record.py", extra_args)
    elif args.command == "to-alignment":
        code = run_script("advance_feature_phase.py", ["--feature-dir", args.feature_dir, "--to-phase", "需求对齐"])
    elif args.command == "sync-meta":
        code = run_script("sync_feature_meta.py", ["--feature-dir", args.feature_dir])
    elif args.command == "confirm-baseline":
        code = run_script(
            "confirm_baseline.py",
            ["--feature-dir", args.feature_dir, "--source", args.source],
        )
    elif args.command == "confirm-schema":
        code = run_script(
            "confirm_schema.py",
            ["--feature-dir", args.feature_dir, "--source", args.source],
        )
    elif args.command == "validate":
        code = run_script("validate_feature_docs.py", ["--feature-dir", args.feature_dir])
    elif args.command == "quality-gate":
        code = run_script("validate_quality_gate.py", ["--record", args.record])
    elif args.command == "implementation-start":
        extra_args = [
            "start",
            "--record",
            args.record,
            "--risk-profile",
            args.risk_profile,
        ]
        for repo_root in args.repo_root:
            extra_args.extend(["--repo-root", repo_root])
        for adopted_file in args.adopt_existing_file:
            extra_args.extend(["--adopt-existing-file", adopted_file])
        for task_id in args.task:
            extra_args.extend(["--task", task_id])
        code = run_script("implementation_session.py", extra_args)
    elif args.command == "implementation-precheck":
        code = run_script("implementation_session.py", ["precheck", "--record", args.record])
    elif args.command == "implementation-verify":
        extra_args = ["verify", "--record", args.record]
        if args.cwd:
            extra_args.extend(["--cwd", args.cwd])
        if args.label:
            extra_args.extend(["--label", args.label])
        extra_args.append("--")
        extra_args.extend(args.verification_command[1:] if args.verification_command[:1] == ["--"] else args.verification_command)
        code = run_script("implementation_session.py", extra_args)
    elif args.command == "implementation-restart":
        code = run_script(
            "implementation_session.py",
            ["restart", "--record", args.record, "--reason", args.reason],
        )
    elif args.command == "implementation-complete":
        extra_args = ["complete", "--record", args.record]
        if args.verification_waiver:
            extra_args.extend(["--verification-waiver", args.verification_waiver])
        code = run_script("implementation_session.py", extra_args)
    elif args.command == "implementation-status":
        code = run_script("implementation_session.py", ["status", "--record", args.record])
    elif args.command == "review-mark":
        extra_args = [
            "review-mark",
            "--record",
            args.record,
            "--result",
            args.result,
        ]
        if args.reviewer_mode:
            extra_args.extend(["--reviewer-mode", args.reviewer_mode])
        if args.self_review_reason:
            extra_args.extend(["--self-review-reason", args.self_review_reason])
        code = run_script("implementation_session.py", extra_args)
    elif args.command == "review-status":
        extra_args = ["review-status", "--record", args.record]
        if args.require_passed:
            extra_args.append("--require-passed")
        code = run_script("implementation_session.py", extra_args)
    elif args.command == "test-run":
        extra_args = [
            "test-run",
            "--record",
            args.record,
            "--round",
            args.round,
            "--scenario",
            args.scenario,
            "--environment",
            args.environment,
            "--effect",
            args.effect,
            "--timeout-seconds",
            str(args.timeout_seconds),
        ]
        if args.cwd:
            extra_args.extend(["--cwd", args.cwd])
        if args.effect_authorization:
            extra_args.extend(
                ["--effect-authorization", args.effect_authorization]
            )
        extra_args.append("--")
        extra_args.extend(
            args.test_command[1:]
            if args.test_command[:1] == ["--"]
            else args.test_command
        )
        code = run_script("implementation_session.py", extra_args)
    elif args.command == "test-mark":
        code = run_script(
            "implementation_session.py",
            ["test-mark", "--record", args.record, "--result", args.result],
        )
    elif args.command == "test-status":
        extra_args = ["test-status", "--record", args.record]
        if args.require_passed:
            extra_args.append("--require-passed")
        code = run_script("implementation_session.py", extra_args)
    elif args.command == "scan-design-inputs":
        extra_args = [
            "--scope-root", args.scope_root,
            "--max-files", str(args.max_files),
            "--max-depth", str(args.max_depth),
            "--limit", str(args.limit),
        ]
        code = run_script("scan_design_inputs.py", extra_args)
    elif args.command == "to-design":
        extra_args = ["--feature-dir", args.feature_dir, "--to-phase", "技术方案"]
        if args.create_schema:
            extra_args.append("--create-schema")
        if args.business_model_confirmed:
            extra_args.append("--business-model-confirmed")
        if args.upstream_contract_confirmed:
            extra_args.append("--upstream-contract-confirmed")
        code = run_script("advance_feature_phase.py", extra_args)
    elif args.command == "to-tasks":
        extra_args = ["--feature-dir", args.feature_dir, "--to-phase", "任务拆分"]
        if args.design_confirmed:
            extra_args.append("--design-confirmed")
        code = run_script("advance_feature_phase.py", extra_args)
    elif args.command == "to-implementation":
        extra_args = ["--feature-dir", args.feature_dir, "--to-phase", "编码实现"]
        if args.tasks_confirmed:
            extra_args.append("--tasks-confirmed")
        code = run_script("advance_feature_phase.py", extra_args)
    elif args.command == "to-review":
        extra_args = ["--feature-dir", args.feature_dir, "--to-phase", "代码检查"]
        if args.implementation_completed:
            extra_args.append("--implementation-completed")
        code = run_script("advance_feature_phase.py", extra_args)
    elif args.command == "to-test":
        extra_args = ["--feature-dir", args.feature_dir, "--to-phase", "测试验证"]
        if args.review_passed:
            extra_args.append("--review-passed")
        code = run_script("advance_feature_phase.py", extra_args)
    elif args.command == "complete":
        if not args.test_passed:
            raise SystemExit("兼容 complete 命令必须显式传入 --test-passed")
        code = run_script(
            "implementation_session.py",
            [
                "test-mark",
                "--record",
                str(Path(args.feature_dir).resolve() / "05-implementation-log.md"),
                "--result",
                "passed",
            ],
        )
    elif args.command == "sync-clarification":
        extra_args = ["--feature-dir", args.feature_dir, "--impact", *args.impact, "--summary", args.summary]
        if args.source:
            extra_args.extend(["--source", args.source])
        if args.business_model_changed:
            extra_args.append("--business-model-changed")
        if args.upstream_contract_changed:
            extra_args.append("--upstream-contract-changed")
        code = run_script("sync_clarification_impact.py", extra_args)
    elif args.command == "status":
        code = run_script("status_feature.py", ["--feature-dir", args.feature_dir])
    elif args.command == "reset":
        code = run_script("reset_feature_phase.py", ["--feature-dir", args.feature_dir, "--to-phase", args.to_phase])
    else:
        raise SystemExit(f"未知命令: {args.command}")

    raise SystemExit(code)


if __name__ == "__main__":
    main()
