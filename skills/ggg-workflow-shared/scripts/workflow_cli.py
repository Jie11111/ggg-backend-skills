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
    init_parser.add_argument("--repo-root", help="仓库根目录，默认当前目录")
    init_parser.add_argument("--feature-name", required=True, help="需求名称")
    init_parser.add_argument("--date", help="目录日期，格式 YYYYMMDD")
    init_parser.add_argument("--refresh-workflow-assets", action="store_true", help="覆盖同步 ggg/workflow 下的共享 README 和模板")

    quick_parser = subparsers.add_parser("init-quick", help="初始化 quick 小需求记录，不创建 full 需求目录")
    quick_parser.add_argument("--repo-root", help="仓库根目录，默认当前目录")
    quick_parser.add_argument("--quick-name", required=True, help="quick 小需求名称")
    quick_parser.add_argument("--date", help="目录日期，格式 YYYYMMDD")

    align_parser = subparsers.add_parser("to-alignment", help="推进到需求对齐阶段，解锁 01-research.md")
    align_parser.add_argument("--feature-dir", required=True, help="需求目录")

    sync_parser = subparsers.add_parser("sync-meta", help="根据当前文档同步 meta.json")
    sync_parser.add_argument("--feature-dir", required=True, help="需求目录")

    validate_parser = subparsers.add_parser("validate", help="按当前阶段校验需求目录")
    validate_parser.add_argument("--feature-dir", required=True, help="需求目录")

    scan_parser = subparsers.add_parser("scan-design-inputs", help="轻量扫描仓库中的模块、入口和依赖信号")
    scan_target_group = scan_parser.add_mutually_exclusive_group(required=True)
    scan_target_group.add_argument("--feature-dir", help="需求目录")
    scan_target_group.add_argument("--repo-root", help="仓库根目录")
    scan_parser.add_argument("--limit", type=int, default=20, help="每类结果最多输出多少行")

    design_parser = subparsers.add_parser("to-design", help="推进到技术方案阶段，解锁 02-design.md 和 04-schema.sql")
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

    complete_parser = subparsers.add_parser("complete", help="推进到交付完成阶段")
    complete_parser.add_argument("--feature-dir", required=True, help="需求目录")
    complete_parser.add_argument("--test-passed", action="store_true", help="确认测试验证已通过")

    clarify_parser = subparsers.add_parser("sync-clarification", help="同步新增澄清的影响到 meta.json")
    clarify_parser.add_argument("--feature-dir", required=True, help="需求目录")
    clarify_parser.add_argument("--impact", nargs="+", required=True,
                                choices=["baseline", "research", "blocking", "design", "schema", "tasks"],
                                help="本次澄清影响范围，可多选")
    clarify_parser.add_argument("--source", default="用户澄清", help="澄清来源")
    clarify_parser.add_argument("--summary", required=True, help="澄清摘要")
    clarify_parser.add_argument("--mark-blockers-unresolved", action="store_true", help="标记本次澄清会重新打开阻塞问题")
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
        code = run_script("init_quick_record.py", extra_args)
    elif args.command == "to-alignment":
        code = run_script("advance_feature_phase.py", ["--feature-dir", args.feature_dir, "--to-phase", "需求对齐"])
    elif args.command == "sync-meta":
        code = run_script("sync_feature_meta.py", ["--feature-dir", args.feature_dir])
    elif args.command == "validate":
        code = run_script("validate_feature_docs.py", ["--feature-dir", args.feature_dir])
    elif args.command == "scan-design-inputs":
        extra_args = ["--limit", str(args.limit)]
        if args.feature_dir:
            extra_args = ["--feature-dir", args.feature_dir, *extra_args]
        if args.repo_root:
            extra_args = ["--repo-root", args.repo_root, *extra_args]
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
        extra_args = ["--feature-dir", args.feature_dir, "--to-phase", "交付完成"]
        if args.test_passed:
            extra_args.append("--test-passed")
        code = run_script("advance_feature_phase.py", extra_args)
    elif args.command == "sync-clarification":
        extra_args = ["--feature-dir", args.feature_dir, "--impact", *args.impact, "--summary", args.summary]
        if args.source:
            extra_args.extend(["--source", args.source])
        if args.mark_blockers_unresolved:
            extra_args.append("--mark-blockers-unresolved")
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
