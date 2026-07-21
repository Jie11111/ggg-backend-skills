#!/usr/bin/env python3
"""阶段推进只依赖当前实现，Review 是用户选择的可选分支。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SHARED_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SHARED_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import advance_feature_phase
import workflow_validation as validator


class TransitionBindingTests(unittest.TestCase):
    def write_meta(self, feature: Path, current_phase: str, review_status: str = "not_run") -> None:
        (feature / "meta.json").write_text(
            json.dumps(
                {
                    "workflow_schema_version": 5,
                    "current_phase": current_phase,
                    "current_status": "编码中" if current_phase == "编码实现" else "检查中",
                    "gates": {"implementation_completed": True},
                    "review_flags": {},
                    "review_status": review_status,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def run_to_test(
        self,
        feature: Path,
        *,
        completed_fingerprint: str = "a" * 64,
        current_fingerprint: str = "a" * 64,
    ) -> tuple[mock.Mock, mock.Mock]:
        state = {
            "status": "completed",
            "round": "I2",
            "completion_snapshot": {"fingerprint": completed_fingerprint},
        }
        with (
            mock.patch.object(
                sys,
                "argv",
                [
                    "advance_feature_phase.py",
                    "--feature-dir",
                    str(feature),
                    "--to-phase",
                    "测试验证",
                ],
            ),
            mock.patch.object(
                advance_feature_phase,
                "detect_repo_root",
                return_value=feature,
            ),
            mock.patch.object(
                advance_feature_phase,
                "detect_workflow_root",
                return_value=SHARED_DIR / "assets" / "workflow",
            ),
            mock.patch.object(
                advance_feature_phase.implementation_session,
                "load_state",
                return_value=state,
            ),
            mock.patch.object(
                advance_feature_phase.implementation_session,
                "current_snapshot",
                return_value={"fingerprint": current_fingerprint, "repositories": []},
            ),
            mock.patch.object(
                advance_feature_phase.implementation_session,
                "current_review_binding_errors",
                return_value=["Review 输入基线已变化"],
            ) as review_bindings,
            mock.patch.object(
                advance_feature_phase.validator,
                "validate_code_review_completion",
                return_value=["Review 未通过"],
            ) as review_completion,
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
        ):
            advance_feature_phase.main()
        return review_bindings, review_completion

    def test_simple_review_artifact_has_only_the_two_optional_checks(self) -> None:
        template = (
            SHARED_DIR / "assets" / "workflow" / "templates" / "code-review-index-template.md"
        ).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "06-code-review.md"
            index.write_text(template, encoding="utf-8")
            errors = validator.validate_code_review_artifacts(index, root / "review-rounds")

        self.assertEqual([], errors)
        self.assertIn("代码与需求是否有偏差", template)
        self.assertIn("代码质量与格式", template)
        self.assertNotIn("Gate A", template)
        self.assertNotIn("Gate B", template)

    def test_to_test_can_start_directly_after_completed_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feature = Path(tmp)
            self.write_meta(feature, "编码实现")
            (feature / "05-implementation-log.md").write_text(
                "# implementation\n",
                encoding="utf-8",
            )

            review_bindings, review_completion = self.run_to_test(feature)

            meta = json.loads((feature / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual("测试验证", meta["current_phase"])
            self.assertEqual("not_run", meta["review_status"])
            self.assertTrue((feature / "07-test-report.md").exists())
            self.assertNotIn("review_passed", meta["gates"])
            self.assertNotIn("review_gate_satisfied", meta["gates"])
            review_bindings.assert_not_called()
            review_completion.assert_not_called()

    def test_explicit_review_result_does_not_become_a_test_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feature = Path(tmp)
            self.write_meta(feature, "代码检查", review_status="needs_changes")
            (feature / "05-implementation-log.md").write_text(
                "# implementation\n",
                encoding="utf-8",
            )
            (feature / "06-code-review.md").write_text(
                "# review\n- 结论：需修改\n",
                encoding="utf-8",
            )

            review_bindings, review_completion = self.run_to_test(feature)

            meta = json.loads((feature / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual("测试验证", meta["current_phase"])
            self.assertEqual("needs_changes", meta["review_status"])
            review_bindings.assert_not_called()
            review_completion.assert_not_called()

    def test_to_test_still_rejects_changes_after_implementation_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feature = Path(tmp)
            self.write_meta(feature, "编码实现")
            (feature / "05-implementation-log.md").write_text(
                "# implementation\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(SystemExit, "实现完成后代码又发生变化"):
                self.run_to_test(
                    feature,
                    completed_fingerprint="a" * 64,
                    current_fingerprint="b" * 64,
                )


if __name__ == "__main__":
    unittest.main()
