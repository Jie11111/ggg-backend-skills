#!/usr/bin/env python3
"""test-run 机器证据与高风险门禁回归。"""

from __future__ import annotations

import argparse
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
import workflow_validation as validator


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

### 5.1 Quick Review 两门复核

| Gate | 检查面 | 结论 | 独立证据或 CRxx |
|---|---|---|---|

### 5.2 Quick 测试场景

| 场景ID | 来源依据 | 业务场景 | 级别 | 前置条件 | 操作与测试数据 | 预期结果 | Effect | 结果 | 证据或原因 |
|---|---|---|---|---|---|---|---|---|---|
| TS1 | 边界目标；Review | 重复提交保持幂等 | 关键 | 本地 Python 可用 | 运行断言脚本 | 进程退出 0 且参数未被 shell 解释 | read-only | 未执行 |  |

### 5.3 Quick 命令证据

| 执行ID | 场景ID | 时间 | 命令 / cwd / 环境 | Effect | 机器证据 | SHA-256 | 结论 |
|---|---|---|---|---|---|---|---|
| Exx | TSxx |  |  | read-only |  |  | PASS / FAIL / BLOCKED |
"""


class TestRunMachineEvidenceTests(unittest.TestCase):
    def test_test_run_redacts_argv_and_output_secrets(self) -> None:
        argv = implementation_session.redact_test_argv(
            [
                "curl",
                "--token",
                "top-secret",
                "--password=hunter2",
                "Authorization: Bearer abc.def",
                "Cookie: session=raw-cookie; theme=dark",
                "Authorization: Basic dXNlcjpwYXNz",
                "https://example.test/?token=query-secret&x=1",
            ]
        )
        rendered = " ".join(argv)
        self.assertNotIn("top-secret", rendered)
        self.assertNotIn("hunter2", rendered)
        self.assertNotIn("abc.def", rendered)
        self.assertNotIn("raw-cookie", rendered)
        self.assertNotIn("dXNlcjpwYXNz", rendered)
        self.assertNotIn("query-secret", rendered)
        output = implementation_session.redact_test_output(
            b"token=top-secret password=hunter2 Authorization: Basic dXNlcjpwYXNz\n"
            b"Cookie: session=raw-cookie; theme=dark\n"
            b'{"token": "json-secret", "authorization": "Basic json-basic"}'
        )
        self.assertNotIn("top-secret", output["summary"])
        self.assertNotIn("hunter2", output["summary"])
        self.assertNotIn("dXNlcjpwYXNz", output["summary"])
        self.assertNotIn("raw-cookie", output["summary"])
        self.assertNotIn("json-secret", output["summary"])
        self.assertNotIn("json-basic", output["summary"])
        echoed = implementation_session.redact_test_output(
            b"['--token', 'argv-secret']",
            sensitive_values={"argv-secret"},
        )
        self.assertNotIn("argv-secret", echoed["summary"])

    def test_test_run_executes_argv_without_shell_and_records_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            record = root / "quick.md"
            record.write_text(quick_record(), encoding="utf-8")
            state = {
                "schema_version": 8,
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
            sentinel = root / "should-not-exist"
            injected = f"; touch {sentinel}"
            args = argparse.Namespace(
                record=str(record),
                round="quick",
                scenario="TS1",
                cwd=str(repo),
                environment="local-python",
                effect="read-only",
                effect_authorization=None,
                timeout_seconds=30,
                test_command=[
                    sys.executable,
                    "-c",
                    "import sys; print(sys.argv[1])",
                    injected,
                ],
            )
            current = {
                "fingerprint": "a" * 64,
                "repositories": [],
            }
            with (
                mock.patch.object(
                    implementation_session,
                    "load_state",
                    return_value=state,
                ),
                mock.patch.object(
                    implementation_session,
                    "save_state",
                ),
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
            ):
                implementation_session.command_test_run(args)

            self.assertFalse(sentinel.exists())
            self.assertEqual(1, len(state["test_runs"]))
            run = state["test_runs"][0]
            evidence = record.parent / run["evidence_path"]
            self.assertTrue(evidence.is_file())
            self.assertEqual(run["evidence_sha256"], implementation_session.file_digest(evidence))
            self.assertEqual(
                [],
                implementation_session.machine_test_run_errors(
                    record,
                    state,
                    current,
                ),
            )
            self.assertIn("| E1 | TS1 |", record.read_text(encoding="utf-8"))

    def test_tampered_machine_evidence_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            record = root / "quick.md"
            record.write_text(quick_record(), encoding="utf-8")
            evidence = root / "reports" / "test-evidence" / "quick-E1.json"
            evidence.parent.mkdir(parents=True)
            evidence.write_text("{}\n", encoding="utf-8")
            digest = implementation_session.file_digest(evidence)
            text = record.read_text(encoding="utf-8").replace(
                "| Exx | TSxx |  |  | read-only |  |  | PASS / FAIL / BLOCKED |",
                f"| E1 | TS1 | now | command | read-only | `{evidence.relative_to(root)}` | {digest} | PASS |",
            )
            record.write_text(text, encoding="utf-8")
            _, plan = implementation_session.test_scenario_plan(record, record, "TS1")
            state = {
                "round": "I1",
                "review": {
                    "review_round": "quick",
                    "input_fingerprint": "b" * 64,
                    "artifact_fingerprint": "c" * 64,
                },
                "test_runs": [{
                    "execution_id": "E1",
                    "test_round": "quick",
                    "scenario_id": "TS1",
                    "scenario_plan_fingerprint": plan,
                    "implementation_round": "I1",
                    "implementation_fingerprint": "a" * 64,
                    "review_round": "quick",
                    "review_input_fingerprint": "b" * 64,
                    "review_artifact_fingerprint": "c" * 64,
                    "effect": "read-only",
                    "evidence_path": evidence.relative_to(root).as_posix(),
                    "evidence_sha256": digest,
                    "result": "passed",
                }],
            }
            evidence.write_text('{"tampered": true}\n', encoding="utf-8")
            errors = implementation_session.machine_test_run_errors(
                record,
                state,
                {"fingerprint": "a" * 64},
            )
            self.assertIn("机器证据文件已被修改", "\n".join(errors))

    def test_evidence_json_must_match_machine_state_even_when_hash_is_synced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = root / "quick.md"
            record.write_text(quick_record(), encoding="utf-8")
            evidence = root / "reports" / "test-evidence" / "quick-E1.json"
            evidence.parent.mkdir(parents=True)
            _, plan = implementation_session.test_scenario_plan(record, record, "TS1")
            run = {
                "execution_id": "E1",
                "test_round": "quick",
                "scenario_id": "TS1",
                "scenario_plan_fingerprint": plan,
                "implementation_round": "I1",
                "implementation_fingerprint": "a" * 64,
                "review_round": "quick",
                "review_input_fingerprint": "b" * 64,
                "review_artifact_fingerprint": "c" * 64,
                "effect": "read-only",
                "evidence_path": evidence.relative_to(root).as_posix(),
                "exit_code": 0,
                "result": "passed",
            }
            evidence.write_text(
                json.dumps(run, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            digest = implementation_session.file_digest(evidence)
            run["evidence_sha256"] = digest
            record.write_text(
                record.read_text(encoding="utf-8").replace(
                    "| Exx | TSxx |  |  | read-only |  |  | PASS / FAIL / BLOCKED |",
                    f"| E1 | TS1 | now | command | read-only | "
                    f"`{evidence.relative_to(root)}` | {digest} | PASS |",
                ),
                encoding="utf-8",
            )
            state = {
                "round": "I1",
                "review": {
                    "review_round": "quick",
                    "input_fingerprint": "b" * 64,
                    "artifact_fingerprint": "c" * 64,
                },
                "test_runs": [run],
            }
            self.assertEqual(
                [],
                implementation_session.machine_test_run_errors(
                    record,
                    state,
                    {"fingerprint": "a" * 64},
                ),
            )

            tampered = {
                key: value
                for key, value in run.items()
                if key != "evidence_sha256"
            }
            tampered["exit_code"] = 99
            evidence.write_text(
                json.dumps(tampered, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            tampered_digest = implementation_session.file_digest(evidence)
            run["evidence_sha256"] = tampered_digest
            record.write_text(
                record.read_text(encoding="utf-8").replace(
                    digest,
                    tampered_digest,
                ),
                encoding="utf-8",
            )
            errors = implementation_session.machine_test_run_errors(
                record,
                state,
                {"fingerprint": "a" * 64},
            )
            self.assertIn("机器证据内容与状态不一致", "\n".join(errors))

    def test_evidence_path_rejects_symlinked_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            feature = root / "feature"
            outside = root / "outside"
            feature.mkdir()
            outside.mkdir()
            (feature / "reports").symlink_to(outside, target_is_directory=True)
            candidate = feature / "reports" / "test-evidence" / "quick-E1.json"
            with self.assertRaisesRegex(SystemExit, "符号链接"):
                implementation_session.ensure_evidence_path_safe(
                    feature,
                    candidate,
                )

    def test_formal_execution_requires_typed_prefix_but_allows_api_and_observation(self) -> None:
        def round_text(method: str) -> str:
            return f"""## 4. 测试场景清单

| 场景ID | 来源依据 | 业务场景 | 级别 | 前置条件 | 操作与测试数据 | 预期结果 | Effect | 结果 | 证据或原因 |
|---|---|---|---|---|---|---|---|---|---|
| TS1 | TB1 | 验证行为 | 关键 | 环境可用 | 执行验证 | 返回正确 | read-only | 未执行 | 待执行 |

## 5. 执行记录

| 执行ID | 场景ID | 时间 | cwd / 环境 / 版本 | 命令/接口/观察点 | 退出码/协议结果 | 实际结果摘要 | Effect | 原始证据 | 证据 SHA-256 | 结论 |
|---|---|---|---|---|---|---|---|---|---|---|
| E1 | TS1 | now | local / test | {method} | HTTP 200 | 返回正确 | read-only | 无法保存原始日志，脱敏摘要足以复查 | 无法保存：临时环境仅提供终端摘要 | PASS |
"""

        errors = validator.validate_test_execution_records(
            round_text("pytest -q"),
            {"TS1"},
            "test-r01.md",
        )
        self.assertIn("必须以 command:、api: 或 observation: 开头", "\n".join(errors))
        for method in ("api: GET /health", "observation: 查询只读日志"):
            with self.subTest(method=method):
                errors = validator.validate_test_execution_records(
                    round_text(method),
                    {"TS1"},
                    "test-r01.md",
                )
                self.assertNotIn(
                    "必须以 command:、api: 或 observation: 开头",
                    "\n".join(errors),
                )

    def test_high_risk_basis_must_be_mandatory_and_cannot_be_waived(self) -> None:
        round_text = """## 3. 测试依据覆盖

| 依据ID | 来源类型 | 来源定位 | 要证明的业务结果或风险 | 风险 | 必测 | Effect | 覆盖场景 | 覆盖结论 | 不适用/豁免事实与授权 |
|---|---|---|---|---|---|---|---|---|---|
| TB1 | 规则 | B1 | 权限不能越权 | 高 | 否 | read-only | TS1 | 不适用 | 用户说以后再测 |

## 4. 测试场景清单

| 场景ID | 来源依据 | 业务场景 | 级别 | 前置条件 | 操作与测试数据 | 预期结果 | Effect | 结果 | 证据或原因 |
|---|---|---|---|---|---|---|---|---|---|
| TS1 | TB1 | 越权访问 | 一般 | 有账号 | 请求接口 | 拒绝 | read-only | 不适用 | 暂不执行 |
"""
        _, scenario_ids = validator.validate_test_scenario_table(
            validator.extract_section(round_text, "## 4. 测试场景清单"),
            "test-r01.md",
            require_passed=False,
        )
        errors = validator.validate_test_basis_coverage(
            round_text,
            scenario_ids,
            "test-r01.md",
        )
        joined = "\n".join(errors)
        self.assertIn("必须标记为必测", joined)
        self.assertIn("不能标记为不适用", joined)

    def test_current_feature_reports_do_not_change_implementation_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
            (repo / "App.java").write_text("class App {}\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "App.java"], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True, capture_output=True)
            feature = repo / "ggg" / "features" / "demo"
            feature.mkdir(parents=True)
            record = feature / "quick.md"
            record.write_text("# quick\n", encoding="utf-8")
            evidence = feature / "reports" / "test-evidence" / "E1.json"
            evidence.parent.mkdir(parents=True)
            evidence.write_text("{}\n", encoding="utf-8")
            (repo / "App.java").write_text("class App { int changed; }\n", encoding="utf-8")
            business_report = repo / "business" / "reports" / "result.json"
            business_report.parent.mkdir(parents=True)
            business_report.write_text("{}\n", encoding="utf-8")
            state = {
                "schema_version": 7,
                "record": str(record),
                "repositories": [{
                    "root": str(repo),
                    "label": "repo",
                    "base_head": subprocess.check_output(
                        ["git", "-C", str(repo), "rev-parse", "HEAD"],
                        text=True,
                    ).strip(),
                    "initial_dirty": {},
                    "adopted_existing": [],
                }],
            }
            paths = {
                item["path"]
                for repository in implementation_session.current_snapshot(state)["repositories"]
                for item in repository["files"]
            }
            self.assertIn("App.java", paths)
            self.assertIn("business/reports/result.json", paths)
            self.assertNotIn("ggg/features/demo/reports/test-evidence/E1.json", paths)


if __name__ == "__main__":
    unittest.main()
