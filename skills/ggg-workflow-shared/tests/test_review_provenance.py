#!/usr/bin/env python3
"""Review fresh/self 来源披露回归。"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SHARED_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SHARED_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import implementation_session
import workflow_validation as validator


class ReviewProvenanceTests(unittest.TestCase):
    def test_legacy_review_mark_falls_back_to_disclosed_self_review(self) -> None:
        mode, reason = implementation_session.validate_reviewer_mode(None, "")
        self.assertEqual("self-review", mode)
        self.assertEqual(implementation_session.LEGACY_REVIEWER_REASON, reason)

    def test_fresh_review_rejects_self_review_reason(self) -> None:
        with self.assertRaisesRegex(SystemExit, "不得传入"):
            implementation_session.validate_reviewer_mode(
                "fresh-review",
                "subagent 启动失败",
            )

    def test_self_review_requires_specific_reason(self) -> None:
        for reason in ("", "无", "不可用", "工具不可用"):
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(SystemExit, "具体原因"):
                    implementation_session.validate_reviewer_mode(
                        "self-review",
                        reason,
                    )

    def test_review_provenance_rejects_mode_mismatch(self) -> None:
        text = (
            "- Review 方式：self-review\n"
            "- Self-review 原因：当前运行环境没有可用的 subagent 能力\n"
        )
        errors = validator.validate_review_provenance(
            text,
            "review-r01.md",
            expected_mode="fresh-review",
            expected_self_review_reason="",
        )
        self.assertIn("Review 方式与登记命令不一致", "\n".join(errors))

    def test_review_mark_cannot_overwrite_existing_reviewer_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "quick.md"
            record.write_text(
                "- Review 结论：通过\n"
                "- Review 方式：self-review\n"
                "- Self-review 原因：当前运行环境没有可用的 subagent 能力\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SystemExit, "不能由 review-mark 改写"):
                implementation_session.reject_conflicting_review_provenance(
                    record,
                    "fresh-review",
                    "不适用",
                )
            self.assertIn(
                "- Review 方式：self-review",
                record.read_text(encoding="utf-8"),
            )

    def test_quick_review_fingerprint_includes_mode_and_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "quick.md"
            record.write_text(
                "## 5. Review / 测试结论\n\n"
                "- Review 结论：通过\n"
                "- Review 方式：fresh-review\n"
                "- Self-review 原因：不适用\n"
                "- Review 对应实现轮次：I1\n"
                "- Review 对应差异指纹：abc\n"
                "- Review Gate A：通过\n"
                "- Review Gate B：通过\n"
                "- Review 未关闭阻塞/必须修问题：无\n"
                "- Review 剩余风险：无\n\n"
                "### 5.1 Quick Review 两门复核\n\n"
                "| Gate | 检查面 | 结论 | 独立证据或 CRxx |\n"
                "|---|---|---|---|\n",
                encoding="utf-8",
            )
            fresh = implementation_session.review_artifact_fingerprint(record)
            record.write_text(
                record.read_text(encoding="utf-8")
                .replace("fresh-review", "self-review")
                .replace("不适用", "当前运行环境没有可用的 subagent 能力"),
                encoding="utf-8",
            )
            self.assertNotEqual(
                fresh,
                implementation_session.review_artifact_fingerprint(record),
            )

    def test_review_status_discloses_self_review(self) -> None:
        state = {
            "round": "I1",
            "schema_version": 8,
            "review": {
                "review_round": "quick",
                "implementation_round": "I1",
                "result": "passed",
                "fingerprint": "a" * 64,
                "input_fingerprint": "b" * 64,
                "artifact_fingerprint": "c" * 64,
                "reviewer_mode": "self-review",
                "self_review_reason": "当前运行环境没有可用的 subagent 能力",
            },
        }
        args = argparse.Namespace(record="/tmp/quick.md", require_passed=True)
        output = io.StringIO()
        with (
            mock.patch.object(
                implementation_session,
                "load_state",
                return_value=state,
            ),
            mock.patch.object(
                implementation_session,
                "current_snapshot",
                return_value={"fingerprint": "a" * 64},
            ),
            mock.patch.object(
                implementation_session,
                "current_review_binding_errors",
                return_value=[],
            ),
            contextlib.redirect_stdout(output),
        ):
            implementation_session.command_review_status(args)
        self.assertIn("[SELF-REVIEW]", output.getvalue())
        self.assertIn("当前运行环境没有可用的 subagent 能力", output.getvalue())


if __name__ == "__main__":
    unittest.main()
