#!/usr/bin/env python3
"""查看需求当前状态看板。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workflow_validation as validator


def file_status(path: Path) -> str:
    if not path.exists():
        return "未开始"
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return "空文件"
    if len(text) < 100:
        return "模板占位"
    return "OK"


def dir_status(path: Path) -> str:
    if not path.exists():
        return "未创建"
    if not path.is_dir():
        return "异常(非目录)"
    files = list(path.glob("*.md"))
    return f"{len(files)} 个文档" if files else "空目录"


def gate_label(value: bool) -> str:
    return "通过" if value else "未确认"


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="查看需求当前状态看板")
    parser.add_argument("--feature-dir", required=True, help="需求目录")
    args = parser.parse_args()

    feature_dir = Path(args.feature_dir).resolve()
    meta_path = feature_dir / "meta.json"
    if not meta_path.exists():
        print("[FAIL] 缺少 meta.json")
        raise SystemExit(1)

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    gates = meta.get("gates", {})
    review_flags = meta.get("review_flags", {})
    clarification = meta.get("clarification", {})

    print(f"[需求] {meta.get('feature_name', '未知')}")
    print(f"[阶段] {meta.get('current_phase', '未知')}")
    print(f"[状态] {meta.get('current_status', '未知')}")
    print(f"[主项目] {meta.get('primary_project', '未设置')}")
    research_path = feature_dir / "01-research.md"
    unresolved = validator.unresolved_research_questions(research_path.read_text(encoding="utf-8")) if research_path.exists() else 0
    if (feature_dir / "01-blocking-issues.md").exists():
        unresolved += 1
    print(f"[阻塞] {unresolved} 个未解决（从唯一疑问账本实时计算）")
    print(f"[门禁] clarification={gate_label(gates.get('clarification_confirmed', False))} | "
          f"alignment={gate_label(gates.get('alignment_completed', False))} | "
          f"design={gate_label(gates.get('design_confirmed', False))} | "
          f"tasks={gate_label(gates.get('tasks_confirmed', False))} | "
          f"implementation={gate_label(gates.get('implementation_completed', False))} | "
          f"review={gate_label(gates.get('review_passed', False))} | "
          f"test={gate_label(gates.get('test_passed', False))} | "
          f"business_model={gate_label(gates.get('business_model_confirmed', False))} | "
          f"upstream_contract={gate_label(gates.get('upstream_contract_confirmed', False))}")
    print(f"[SQL确认] {gate_label(gates.get('schema_confirmed', False))} | "
          f"来源={meta.get('schema_confirmation', {}).get('confirmation_source', '') or '无'} | "
          f"时间={meta.get('schema_confirmation', {}).get('confirmed_at', '') or '无'}")

    baseline = file_status(feature_dir / "00-baseline.md")
    research = file_status(feature_dir / "01-research.md")
    design = file_status(feature_dir / "02-design.md")
    tasks = file_status(feature_dir / "03-tasks.md")
    schema = file_status(feature_dir / "04-schema.sql")
    implementation_log = file_status(feature_dir / "05-implementation-log.md")
    code_review = file_status(feature_dir / "06-code-review.md")
    test_report = file_status(feature_dir / "07-test-report.md")
    interface_details = dir_status(feature_dir / "interface-details")
    print(f"[文档] baseline={baseline} | research={research} | design={design} | "
          f"tasks={tasks} | schema={schema} | implementation-log={implementation_log} | "
          f"code-review={code_review} | test-report={test_report} | interface-details={interface_details}")

    needs_review = []
    if review_flags.get("alignment_needs_review"):
        needs_review.append("alignment")
    if review_flags.get("design_needs_review"):
        needs_review.append("design")
    if review_flags.get("tasks_needs_review"):
        needs_review.append("tasks")
    if needs_review:
        print(f"[待重审] {', '.join(needs_review)}")

    count = clarification.get("count", 0)
    if count > 0:
        last_summary = clarification.get("last_summary", "")
        last_time = clarification.get("last_updated_at", "")
        last_impacts = clarification.get("last_impacts", [])
        print(f"[澄清] {count} 次，最近：{last_time} \"{last_summary}\"，影响：{', '.join(last_impacts)}")
    else:
        print("[澄清] 无")


if __name__ == "__main__":
    main()
