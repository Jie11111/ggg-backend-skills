#!/usr/bin/env python3
"""覆盖实现完成豁免与任务到实现交接的硬伤回归。"""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path
from unittest import mock


SHARED_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SHARED_DIR / "scripts"
SKILLS_ROOT = SHARED_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import implementation_session


class HardfixRegressionTests(unittest.TestCase):
    def test_task_breakdown_contains_authorized_to_implementation_handoff(self) -> None:
        content = (SKILLS_ROOT / "ggg-task-breakdown" / "SKILL.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("to-implementation", content)
        self.assertIn("--tasks-confirmed", content)
        self.assertIn("用户已经授权连续编码", content)
        self.assertIn("用户尚未授权编码时", content)

    def test_verification_waiver_cannot_override_known_failure_or_stale_run(self) -> None:
        for result in ("failed", "stale"):
            with self.subTest(result=result):
                state = {
                    "status": "in_progress",
                    "round": "I1",
                    "risk_profile": "normal",
                    "selected_tasks": ["T1"],
                    "precheck": {
                        "result": "passed",
                        "implementation_round": "I1",
                        "record_fingerprint": "precheck-fingerprint",
                    },
                    "verification_runs": [
                        {
                            "id": "V1",
                            "implementation_round": "I1",
                            "after_snapshot_fingerprint": "current-snapshot",
                            "label": "unit",
                            "command": ["mvn", "test"],
                            "result": result,
                        },
                        {
                            "id": "V2",
                            "implementation_round": "I1",
                            "after_snapshot_fingerprint": "current-snapshot",
                            "label": "unit",
                            "command": ["mvn", "test"],
                            "result": "environment_blocked",
                        }
                    ],
                }
                args = argparse.Namespace(
                    record="/tmp/05-implementation-log.md",
                    verification_waiver="测试环境不可用",
                )

                with (
                    mock.patch.object(
                        implementation_session,
                        "require_quick_boundary_ready",
                    ),
                    mock.patch.object(
                        implementation_session,
                        "load_state",
                        return_value=state,
                    ),
                    mock.patch.object(
                        implementation_session,
                        "current_snapshot",
                        return_value={"fingerprint": "current-snapshot"},
                    ),
                    mock.patch.object(
                        implementation_session.validator,
                        "validate_implementation_precheck",
                        return_value=[],
                    ),
                    mock.patch.object(
                        implementation_session.validator,
                        "implementation_precheck_fingerprint",
                        return_value="precheck-fingerprint",
                    ),
                ):
                    with self.assertRaisesRegex(
                        SystemExit,
                        "不能覆盖已知失败",
                    ):
                        implementation_session.command_complete(args)

    def test_verification_waiver_accepts_environment_blocked_attempt(self) -> None:
        state = {
            "status": "in_progress",
            "round": "I1",
            "risk_profile": "normal",
            "selected_tasks": ["T1"],
            "completed_task_ids": [],
            "repositories": [{"label": "demo"}],
            "precheck": {
                "result": "passed",
                "implementation_round": "I1",
                "record_fingerprint": "precheck-fingerprint",
            },
            "verification_runs": [
                {
                    "id": "V1",
                    "implementation_round": "I1",
                    "after_snapshot_fingerprint": "current-snapshot",
                    "label": "unit",
                    "command": ["missing-build-tool", "test"],
                    "result": "environment_blocked",
                }
            ],
        }
        args = argparse.Namespace(
            record="/tmp/05-implementation-log.md",
            verification_waiver="构建工具未安装；保留静态检查证据并待环境恢复后复跑",
        )

        with (
            mock.patch.object(
                implementation_session,
                "require_quick_boundary_ready",
            ),
            mock.patch.object(
                implementation_session,
                "load_state",
                return_value=state,
            ),
            mock.patch.object(
                implementation_session,
                "current_snapshot",
                return_value={"fingerprint": "current-snapshot"},
            ),
            mock.patch.object(
                implementation_session.validator,
                "validate_implementation_precheck",
                return_value=[],
            ),
            mock.patch.object(
                implementation_session.validator,
                "implementation_precheck_fingerprint",
                return_value="precheck-fingerprint",
            ),
            mock.patch.object(
                implementation_session,
                "record_verification_waiver",
            ),
            mock.patch.object(
                implementation_session,
                "collect_changes",
                return_value=({"src/Demo.java"}, {"demo": ["src/Demo.java"]}),
            ),
            mock.patch.object(
                implementation_session,
                "current_round_paths",
                return_value={"src/Demo.java"},
            ),
            mock.patch.object(
                implementation_session,
                "validate_record",
                return_value=[],
            ),
            mock.patch.object(
                implementation_session,
                "save_state",
            ),
            mock.patch.object(
                implementation_session,
                "update_record_line",
            ),
        ):
            implementation_session.command_complete(args)

        self.assertEqual("completed", state["status"])
        self.assertIn("构建工具未安装", state["verification_waiver"]["reason"])


if __name__ == "__main__":
    unittest.main()
