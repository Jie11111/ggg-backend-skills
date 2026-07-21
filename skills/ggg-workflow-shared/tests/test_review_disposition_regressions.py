#!/usr/bin/env python3
"""可选 Review、直接测试和旧状态读取兼容回归。"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TEST_DIR = Path(__file__).resolve().parent
SHARED_DIR = TEST_DIR.parent
SCRIPTS_DIR = SHARED_DIR / "scripts"
TEMPLATES_DIR = SHARED_DIR / "assets" / "workflow" / "templates"
sys.path.insert(0, str(TEST_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

import advance_feature_phase
import implementation_session
import workflow_validation as validator
from test_workflow_consistency import (
    build_completed_implementation_log,
    build_completed_quick_record,
)


CODE_FINGERPRINT = "a" * 64


def completed_state(review: dict | None = None) -> tuple[dict, dict]:
    snapshot = {
        "fingerprint": CODE_FINGERPRINT,
        "repositories": [],
    }
    state = {
        "schema_version": implementation_session.STATE_SCHEMA_VERSION,
        "round": "I1",
        "status": "completed",
        "completion_snapshot": dict(snapshot),
        "review": review,
        "test": None,
    }
    return state, snapshot


def fill_quick_review(record: Path, result: str) -> None:
    text = record.read_text(encoding="utf-8")
    if result == "passed":
        first = "| 代码与需求是否有偏差 | 通过 | 无 |"
        second = "| 代码质量与格式 | 通过 | 无 |"
        unresolved = "无"
    elif result == "needs_changes":
        first = (
            "| 代码与需求是否有偏差 | 有问题 | "
            "`src/ReportController.java:24` 与已确认幂等口径不一致，影响重复提交结果 |"
        )
        second = "| 代码质量与格式 | 通过 | 无 |"
        unresolved = "需修正重复提交时返回新记录的问题"
    else:
        first = "| 代码与需求是否有偏差 | 通过 | 无 |"
        second = (
            "| 代码质量与格式 | 阻塞 | "
            "`src/ReportController.java:24` 依赖代码缺失，当前无法完成质量判断 |"
        )
        unresolved = "依赖代码缺失，补齐后才能完成检查"

    text = text.replace(
        "| 代码与需求是否有偏差 | 通过 / 有问题 / 阻塞 | "
        "无 / `文件:行号`＋问题、影响和建议 |",
        first,
    ).replace(
        "| 代码质量与格式 | 通过 / 有问题 / 阻塞 | "
        "无 / `文件:行号`＋问题、影响和建议 |",
        second,
    ).replace(
        "- Review 未解决问题：无 / 具体问题",
        f"- Review 未解决问题：{unresolved}",
    )
    record.write_text(text, encoding="utf-8")


def run_transition_to_test(
    root: Path,
    state: dict,
    snapshot: dict,
    review_status: str,
) -> dict:
    feature_dir = root / "ggg" / "features" / f"review-{review_status}"
    feature_dir.mkdir(parents=True)
    record = feature_dir / "05-implementation-log.md"
    record.write_text(build_completed_implementation_log(), encoding="utf-8")
    (feature_dir / "meta.json").write_text(
        json.dumps(
            {
                "workflow_schema_version": 5,
                "current_phase": "编码实现",
                "current_status": "实现完成",
                "review_status": review_status,
                "gates": {},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    argv = [
        "advance_feature_phase.py",
        "--feature-dir",
        str(feature_dir),
        "--to-phase",
        "测试验证",
    ]

    with (
        mock.patch.object(sys, "argv", argv),
        mock.patch.object(advance_feature_phase, "detect_repo_root", return_value=root),
        mock.patch.object(
            advance_feature_phase,
            "detect_workflow_root",
            return_value=root / "ggg" / "workflow",
        ),
        mock.patch.object(
            advance_feature_phase.implementation_session,
            "load_state",
            return_value=state,
        ),
        mock.patch.object(
            advance_feature_phase.implementation_session,
            "current_snapshot",
            return_value=snapshot,
        ),
        mock.patch.object(
            advance_feature_phase.validator,
            "validate_implementation_completion",
            return_value=[],
        ),
        mock.patch.object(
            advance_feature_phase.validator,
            "validate_feature_dir",
            return_value=[],
        ),
        contextlib.redirect_stdout(io.StringIO()),
    ):
        advance_feature_phase.main()

    meta = json.loads((feature_dir / "meta.json").read_text(encoding="utf-8"))
    meta["_test_report_exists"] = (feature_dir / "07-test-report.md").exists()
    return meta


class OptionalReviewRegressionTests(unittest.TestCase):
    def test_review_templates_have_exactly_two_checks_and_no_modes_or_gates(self) -> None:
        review_text = (TEMPLATES_DIR / "code-review-index-template.md").read_text(
            encoding="utf-8"
        )
        headers, rows = validator.extract_first_table(
            validator.extract_section(review_text, "## 2. 两项检查")
        )
        self.assertEqual(
            ["代码与需求是否有偏差", "代码质量与格式"],
            [validator.table_cell(headers, row, "检查项") for row in rows],
        )
        for obsolete in [
            "Review disposition",
            "Gate A",
            "Gate B",
            "Review 门禁",
            "review-rounds",
            "light",
            "formal",
            "skipped",
        ]:
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, review_text)

    def test_quick_optional_review_records_each_result_without_gate(self) -> None:
        expected_labels = {
            "passed": "通过",
            "needs_changes": "需修改",
            "blocked": "阻塞",
        }
        for result, expected_label in expected_labels.items():
            with self.subTest(result=result), tempfile.TemporaryDirectory() as tmp:
                record = Path(tmp) / "quick.md"
                record.write_text(build_completed_quick_record(), encoding="utf-8")
                fill_quick_review(record, result)
                state, snapshot = completed_state()

                with (
                    mock.patch.object(implementation_session, "load_state", return_value=state),
                    mock.patch.object(
                        implementation_session,
                        "current_snapshot",
                        return_value=snapshot,
                    ),
                    mock.patch.object(implementation_session, "save_state") as save_state,
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    implementation_session.command_review_mark(
                        argparse.Namespace(record=str(record), result=result)
                    )

                review = state["review"]
                self.assertEqual("optional", review["model"])
                self.assertEqual(result, review["result"])
                self.assertNotIn("disposition", review)
                self.assertNotIn("gate_satisfied", review)
                self.assertNotIn("review_round", review)
                save_state.assert_called_once_with(record.resolve(), state)
                text = record.read_text(encoding="utf-8")
                self.assertIn("- Review 状态：已执行", text)
                self.assertIn(f"- Review 结论：{expected_label}", text)

    def test_optional_review_rejects_any_third_check_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "quick.md"
            record.write_text(build_completed_quick_record(), encoding="utf-8")
            fill_quick_review(record, "passed")
            text = record.read_text(encoding="utf-8").replace(
                "| 代码质量与格式 | 通过 | 无 |",
                "| 代码质量与格式 | 通过 | 无 |\n| 额外检查项 | 通过 | 无 |",
            )
            record.write_text(text, encoding="utf-8")

            errors = validator.validate_optional_review(
                record,
                "passed",
                "I1",
                CODE_FINGERPRINT,
            )

        self.assertIn("只允许两项检查", "\n".join(errors))

    def test_no_review_goes_directly_from_implementation_to_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state, snapshot = completed_state()
            meta = run_transition_to_test(Path(tmp), state, snapshot, "not_run")

        self.assertEqual("测试验证", meta["current_phase"])
        self.assertEqual("not_run", meta["review_status"])
        self.assertTrue(meta["gates"]["implementation_completed"])
        self.assertNotIn("review_gate_satisfied", meta["gates"])
        self.assertNotIn("review_passed", meta["gates"])
        self.assertNotIn("review_disposition", meta)
        self.assertTrue(meta["_test_report_exists"])

    def test_non_passing_optional_review_does_not_block_test(self) -> None:
        for result in ["needs_changes", "blocked"]:
            with self.subTest(result=result), tempfile.TemporaryDirectory() as tmp:
                review = {
                    "model": "optional",
                    "result": result,
                    "implementation_round": "I1",
                    "fingerprint": CODE_FINGERPRINT,
                    "subject_fingerprint": "recorded-subject",
                }
                state, snapshot = completed_state(review)
                meta = run_transition_to_test(Path(tmp), state, snapshot, result)

                self.assertEqual("测试验证", meta["current_phase"])
                self.assertEqual(result, meta["review_status"])
                self.assertNotIn("review_gate_satisfied", meta["gates"])
                self.assertNotIn("review_passed", meta["gates"])

    def test_optional_review_binding_does_not_create_a_report_package_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feature_dir = Path(tmp)
            record = feature_dir / "05-implementation-log.md"
            record.write_text(build_completed_implementation_log(), encoding="utf-8")
            report = feature_dir / "06-code-review.md"
            report.write_text(
                (TEMPLATES_DIR / "code-review-index-template.md").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )
            state, snapshot = completed_state()
            state["review"] = {
                "model": "optional",
                "result": "passed",
                "implementation_round": "I1",
                "fingerprint": CODE_FINGERPRINT,
                "subject_fingerprint": implementation_session.optional_review_subject_fingerprint(
                    record,
                    CODE_FINGERPRINT,
                ),
            }

            report.write_text(
                report.read_text(encoding="utf-8").replace("- 说明：", "- 说明：补充文字"),
                encoding="utf-8",
            )

            self.assertEqual(
                [],
                implementation_session.current_review_binding_errors(
                    record,
                    state,
                    snapshot,
                ),
            )

    def test_legacy_skipped_review_decision_binding_remains_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feature_dir = Path(tmp)
            record = feature_dir / "05-implementation-log.md"
            record.write_text(
                """<!-- GGG_IMPLEMENTATION_SCHEMA_VERSION: 2 -->
# 实现记录

- Review 结论：已跳过（未评审）
- Review disposition：skipped
- Review 门禁是否满足：是
- Review 跳过原因：用户历史决定
- Review 对应实现轮次：I1
- Review 对应差异指纹：aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
""",
                encoding="utf-8",
            )
            state, snapshot = completed_state()
            state["review"] = {
                "implementation_round": "I1",
                "fingerprint": CODE_FINGERPRINT,
                "disposition": "skipped",
                "result": "skipped",
                "decision_fingerprint": implementation_session.review_skip_decision_fingerprint(
                    record
                ),
            }

            record.write_text(
                record.read_text(encoding="utf-8").replace(
                    "- Review 跳过原因：用户历史决定",
                    "- Review 跳过原因：登记后被修改",
                ),
                encoding="utf-8",
            )

            self.assertIn(
                "Review 跳过决定在登记后发生变化",
                implementation_session.current_review_binding_errors(
                    record,
                    state,
                    snapshot,
                ),
            )


if __name__ == "__main__":
    unittest.main()
