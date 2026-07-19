#!/usr/bin/env python3
"""阶段推进必须复用当前 Review 的完整绑定上下文。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SHARED_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SHARED_DIR / "scripts"
TESTS_DIR = SHARED_DIR / "tests"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(TESTS_DIR))

import advance_feature_phase
import workflow_validation as validator
from test_workflow_consistency import (
    build_completed_review_index,
    build_completed_review_round,
)


class TransitionBindingTests(unittest.TestCase):
    def test_review_structure_validation_without_snapshot_does_not_reject_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "06-code-review.md"
            index.write_text(build_completed_review_index(), encoding="utf-8")
            rounds = root / "review-rounds"
            rounds.mkdir()
            (rounds / "review-r01.md").write_text(
                build_completed_review_round(),
                encoding="utf-8",
            )
            errors = validator.validate_code_review_completion(index, rounds)
        self.assertNotIn(
            "覆盖了不属于当前实现快照的文件",
            "\n".join(errors),
        )

    def test_to_test_passes_real_snapshot_and_all_review_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feature = Path(tmp)
            (feature / "meta.json").write_text(
                json.dumps(
                    {
                        "workflow_schema_version": 5,
                        "current_phase": "代码检查",
                        "current_status": "检查中",
                        "gates": {},
                        "review_flags": {},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (feature / "05-implementation-log.md").write_text("# implementation\n", encoding="utf-8")
            (feature / "06-code-review.md").write_text("# review\n", encoding="utf-8")
            (feature / "review-rounds").mkdir()
            state = {
                "round": "I2",
                "review": {
                    "result": "passed",
                    "review_round": "R3",
                    "input_fingerprint": "b" * 64,
                },
            }
            current = {
                "fingerprint": "a" * 64,
                "repositories": [{
                    "label": "repo",
                    "files": [{"path": "src/App.java", "digest": "c" * 64}],
                }],
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
                        "--review-passed",
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
                    return_value=current,
                ),
                mock.patch.object(
                    advance_feature_phase.implementation_session,
                    "current_review_binding_errors",
                    return_value=[],
                ),
                mock.patch.object(
                    advance_feature_phase.validator,
                    "validate_code_review_completion",
                    return_value=[],
                ) as completion,
                mock.patch.object(
                    advance_feature_phase.validator,
                    "validate_feature_dir",
                    return_value=[],
                ),
            ):
                advance_feature_phase.main()

            kwargs = completion.call_args.kwargs
            self.assertEqual({"src/App.java"}, kwargs["actual_paths"])
            self.assertEqual("I2", kwargs["expected_implementation_round"])
            self.assertEqual("a" * 64, kwargs["expected_fingerprint"])
            self.assertEqual("b" * 64, kwargs["expected_input_fingerprint"])

    def test_to_test_rejects_stale_review_before_report_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            feature = Path(tmp)
            (feature / "meta.json").write_text(
                json.dumps({
                    "workflow_schema_version": 5,
                    "current_phase": "代码检查",
                    "gates": {},
                    "review_flags": {},
                }),
                encoding="utf-8",
            )
            (feature / "05-implementation-log.md").write_text("# implementation\n", encoding="utf-8")
            (feature / "06-code-review.md").write_text("# review\n", encoding="utf-8")
            state = {"round": "I1", "review": {"result": "passed"}}
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
                        "--review-passed",
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
                    return_value={"fingerprint": "a" * 64, "repositories": []},
                ),
                mock.patch.object(
                    advance_feature_phase.implementation_session,
                    "current_review_binding_errors",
                    return_value=["Review 输入基线已变化"],
                ),
            ):
                with self.assertRaises(SystemExit):
                    advance_feature_phase.main()


if __name__ == "__main__":
    unittest.main()
