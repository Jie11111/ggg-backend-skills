#!/usr/bin/env python3
"""一次性验证/测试进程回收的回归测试。"""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SHARED_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SHARED_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import implementation_session
import workflow_cli


def quick_record() -> str:
    return """# Quick

## 5. Review / 测试结论

- Review 结论：通过
- Review 方式：fresh-review
- Self-review 原因：不适用
- Review 对应实现轮次：I1
- Review 对应差异指纹：aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
- Review Gate A：通过
- Review Gate B：通过
- Review 未关闭阻塞/必须修问题：无
- Review 剩余风险：无

### 5.2 Quick 测试场景

| 场景ID | 来源依据 | 业务场景 | 级别 | 前置条件 | 操作与测试数据 | 预期结果 | Effect | 结果 | 证据或原因 |
|---|---|---|---|---|---|---|---|---|---|
| TS1 | 边界目标；Review | 进程回收失败不得误报通过 | 关键 | 本地 Python 可用 | 运行断言脚本 | 回收失败时阻塞 | read-only | 未执行 |  |

### 5.3 Quick 命令证据

| 执行ID | 场景ID | 时间 | 命令 / cwd / 环境 | Effect | 机器证据 | SHA-256 | 结论 |
|---|---|---|---|---|---|---|---|
| Exx | TSxx |  |  | read-only |  |  | PASS / FAIL / BLOCKED |
"""


class ProcessCleanupRegressionTests(unittest.TestCase):
    def test_workflow_cli_implementation_verify_forwards_default_timeout_60(self) -> None:
        with (
            mock.patch.object(
                sys,
                "argv",
                [
                    "workflow_cli.py",
                    "implementation-verify",
                    "--record",
                    "/tmp/implementation.md",
                    "--",
                    sys.executable,
                    "-c",
                    "print('ok')",
                ],
            ),
            mock.patch.object(workflow_cli, "run_script", return_value=0) as run_script,
            self.assertRaises(SystemExit) as raised,
        ):
            workflow_cli.main()

        self.assertEqual(0, raised.exception.code)
        run_script.assert_called_once_with(
            "implementation_session.py",
            [
                "verify",
                "--record",
                "/tmp/implementation.md",
                "--timeout-seconds",
                "60",
                "--",
                sys.executable,
                "-c",
                "print('ok')",
            ],
        )

    def test_shared_runner_is_non_pty_and_starts_a_new_session(self) -> None:
        process = mock.Mock()
        process.pid = 12345
        process.returncode = 0
        process.communicate.return_value = (b"ok\n", b"")

        with (
            mock.patch.object(
                implementation_session.subprocess,
                "Popen",
                return_value=process,
            ) as popen,
            mock.patch.object(
                implementation_session,
                "process_group_exists",
                return_value=False,
            ),
        ):
            result = implementation_session.run_test_command_once(
                ["example-command", "--flag"],
                Path("/tmp"),
                60,
            )

        self.assertEqual((0, b"ok\n", b"", False, False, False, False, False), result)
        popen.assert_called_once_with(
            ["example-command", "--flag"],
            cwd=Path("/tmp"),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        self.assertNotIn("shell", popen.call_args.kwargs)

    def test_stubborn_parent_and_child_are_killed_without_residual_processes(self) -> None:
        parent_code = """import signal, subprocess, sys, time
child_code = (
    "import signal,time; "
    "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
    "time.sleep(60)"
)
subprocess.Popen(
    [sys.executable, "-c", child_code],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
signal.signal(signal.SIGTERM, signal.SIG_IGN)
print("ready", flush=True)
time.sleep(60)
"""
        terminate_process_group = implementation_session.terminate_process_group

        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(
                implementation_session,
                "terminate_process_group",
                side_effect=lambda process: terminate_process_group(
                    process,
                    grace_seconds=0.3,
                ),
            ),
        ):
            result = implementation_session.run_test_command_once(
                [sys.executable, "-c", parent_code],
                Path(tmp),
                0.2,
            )

        (
            exit_code,
            stdout,
            stderr,
            timed_out,
            residual_detected,
            term_sent,
            kill_sent,
            residual_after_cleanup,
        ) = result
        self.assertEqual(124, exit_code)
        self.assertIn(b"ready", stdout)
        self.assertEqual(b"", stderr)
        self.assertTrue(timed_out)
        self.assertTrue(residual_detected)
        self.assertTrue(term_sent)
        self.assertTrue(kill_sent)
        self.assertFalse(residual_after_cleanup)

    def test_test_run_blocks_and_persists_evidence_when_cleanup_has_residuals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            record = root / "quick.md"
            record.write_text(quick_record(), encoding="utf-8")
            state = {
                "schema_version": 10,
                "record": str(record),
                "round": "I1",
                "status": "completed",
                "repositories": [{"root": str(repo), "label": "repo"}],
                "completion_snapshot": {"fingerprint": "a" * 64},
                "review": {
                    "result": "passed",
                    "review_round": "quick",
                    "input_fingerprint": "b" * 64,
                    "artifact_fingerprint": "c" * 64,
                },
                "test_runs": [],
            }
            current = {"fingerprint": "a" * 64, "repositories": []}
            args = argparse.Namespace(
                record=str(record),
                round="quick",
                scenario="TS1",
                cwd=str(repo),
                environment="local-python",
                effect="read-only",
                effect_authorization=None,
                timeout_seconds=60,
                test_command=[sys.executable, "-c", "print('ok')"],
            )
            runner_result = (
                0,
                b"ok\n",
                b"",
                False,
                True,
                True,
                True,
                True,
            )

            with (
                mock.patch.object(
                    implementation_session,
                    "load_state",
                    return_value=state,
                ),
                mock.patch.object(implementation_session, "save_state") as save_state,
                mock.patch.object(
                    implementation_session,
                    "current_snapshot",
                    return_value=current,
                ),
                mock.patch.object(
                    implementation_session,
                    "current_review_binding_errors",
                    return_value=[],
                ),
                mock.patch.object(
                    implementation_session,
                    "run_test_command_once",
                    return_value=runner_result,
                ),
                self.assertRaises(SystemExit) as raised,
            ):
                implementation_session.command_test_run(args)

            self.assertEqual(1, raised.exception.code)
            save_state.assert_called_once()
            self.assertEqual(record.resolve(), save_state.call_args.args[0])
            self.assertIs(state, save_state.call_args.args[1])
            self.assertEqual(1, len(state["test_runs"]))
            run = state["test_runs"][0]
            self.assertEqual("blocked", run["result"])
            self.assertFalse(run["timed_out"])
            self.assertTrue(run["residual_processes_detected"])
            self.assertTrue(run["process_group_term_sent"])
            self.assertTrue(run["process_group_kill_sent"])
            self.assertTrue(run["residual_processes_after_cleanup"])

            evidence = record.parent / run["evidence_path"]
            evidence_payload = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual("blocked", evidence_payload["result"])
            self.assertTrue(evidence_payload["residual_processes_after_cleanup"])
            self.assertEqual(
                run["evidence_sha256"],
                implementation_session.file_digest(evidence),
            )
            self.assertIn("BLOCKED", record.read_text(encoding="utf-8"))

    def test_implementation_verify_persists_cleanup_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            record = root / "quick.md"
            record.write_text(
                """# Quick

- 验证命令 / 方式：
- 验证结果：
- stdout 摘要：
- stderr 摘要：
- 未验证项：
- 阻塞原因：
- 进程回收：
""",
                encoding="utf-8",
            )
            state = {
                "record": str(record),
                "round": "I1",
                "status": "in_progress",
                "repositories": [{"root": str(repo), "label": "repo"}],
                "precheck": {
                    "result": "passed",
                    "implementation_round": "I1",
                },
                "verification_runs": [],
            }
            snapshot = {"fingerprint": "a" * 64, "repositories": []}
            secret = "verify-secret-must-not-leak"
            args = argparse.Namespace(
                record=str(record),
                cwd=str(repo),
                label="cleanup-regression",
                timeout_seconds=60,
                verification_command=[
                    sys.executable,
                    "-c",
                    "print('ok')",
                    "--token",
                    secret,
                ],
            )
            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()

            with (
                mock.patch.object(
                    implementation_session,
                    "load_state",
                    return_value=state,
                ),
                mock.patch.object(implementation_session, "save_state") as save_state,
                mock.patch.object(
                    implementation_session,
                    "current_snapshot",
                    return_value=snapshot,
                ),
                mock.patch.object(
                    implementation_session,
                    "run_test_command_once",
                    return_value=(
                        0,
                        f"stdout token={secret}\n".encode(),
                        f"stderr password={secret}\n".encode(),
                        False,
                        True,
                        True,
                        False,
                        False,
                    ),
                ),
                mock.patch.object(sys, "stdout", stdout_capture),
                mock.patch.object(sys, "stderr", stderr_capture),
            ):
                implementation_session.command_verify(args)

            save_state.assert_called_once()
            self.assertEqual(record.resolve(), save_state.call_args.args[0])
            self.assertIs(state, save_state.call_args.args[1])
            run = state["verification_runs"][0]
            self.assertEqual("passed", run["result"])
            self.assertEqual("one-shot non-PTY", run["execution_mode"])
            self.assertEqual(60, run["timeout_seconds"])
            self.assertTrue(run["residual_processes_detected"])
            self.assertTrue(run["process_group_term_sent"])
            self.assertFalse(run["process_group_kill_sent"])
            self.assertFalse(run["residual_processes_after_cleanup"])
            persisted_surfaces = "\n".join(
                [
                    json.dumps(state, ensure_ascii=False),
                    record.read_text(encoding="utf-8"),
                    stdout_capture.getvalue(),
                    stderr_capture.getvalue(),
                ]
            )
            self.assertNotIn(secret, persisted_surfaces)
            self.assertIn("<redacted>", " ".join(run["command"]))


if __name__ == "__main__":
    unittest.main()
