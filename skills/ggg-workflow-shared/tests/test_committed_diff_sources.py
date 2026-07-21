#!/usr/bin/env python3
"""Committed implementation diff source regressions."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SHARED_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SHARED_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import implementation_session


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args],
        text=True,
    ).strip()


def commit_file(repo: Path, relative: str, content: str, message: str) -> str:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", relative], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", message],
        check=True,
        capture_output=True,
    )
    return git(repo, "rev-parse", "HEAD")


def init_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "GGG Test"], check=True)
    commit_file(repo, "README.md", "base\n", "base")
    return repo


class CommittedDiffSourceTests(unittest.TestCase):
    def test_diff_range_binds_paths_and_ignores_unrelated_later_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = init_repo(root)
            base = git(repo, "rev-parse", "HEAD")
            target = commit_file(repo, "src/App.java", "class App {}\n", "feature")
            repo_state = {
                "root": str(repo),
                "label": "repo",
                "base_head": target,
                "initial_dirty": {},
            }
            implementation_session.resolve_committed_diff_sources(
                [repo_state],
                [f"{base}..{target}"],
                [],
            )
            record = root / "quick.md"
            record.write_text("# quick\n", encoding="utf-8")
            state = {
                "schema_version": implementation_session.STATE_SCHEMA_VERSION,
                "record": str(record),
                "repositories": [repo_state],
            }

            bound = implementation_session.current_snapshot(state)
            state["start_snapshot"] = bound
            source = repo_state["diff_source"]
            self.assertEqual("diff-range", source["type"])
            self.assertEqual(base, source["base"])
            self.assertEqual(target, source["target"])
            self.assertEqual(["src/App.java"], repo_state["committed_diff_paths"])
            self.assertEqual(
                {"repo/src/App.java"},
                implementation_session.current_round_paths(state, bound),
            )

            commit_file(repo, "docs/notes.md", "unrelated\n", "unrelated")
            after_unrelated_commit = implementation_session.current_snapshot(state)
            self.assertEqual(bound["fingerprint"], after_unrelated_commit["fingerprint"])

            (repo / "src" / "App.java").write_text(
                "class App { int changed; }\n",
                encoding="utf-8",
            )
            after_bound_file_change = implementation_session.current_snapshot(state)
            self.assertNotEqual(
                bound["fingerprint"],
                after_bound_file_change["fingerprint"],
            )

    def test_adopt_commit_uses_parent_range_and_counts_as_round_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = init_repo(root)
            base = git(repo, "rev-parse", "HEAD")
            target = commit_file(repo, "src/Feature.java", "class Feature {}\n", "feature")
            repo_state = {
                "root": str(repo),
                "label": "repo",
                "base_head": target,
                "initial_dirty": {},
            }
            implementation_session.resolve_committed_diff_sources(
                [repo_state],
                [],
                [target],
            )
            record = root / "quick.md"
            record.write_text("# quick\n", encoding="utf-8")
            state = {
                "schema_version": implementation_session.STATE_SCHEMA_VERSION,
                "record": str(record),
                "repositories": [repo_state],
            }
            snapshot = implementation_session.current_snapshot(state)
            state["start_snapshot"] = snapshot

            self.assertEqual(
                {
                    "type": "adopt-commit",
                    "base": base,
                    "target": target,
                    "requested": target,
                },
                repo_state["diff_source"],
            )
            self.assertEqual(
                {"repo/src/Feature.java"},
                implementation_session.current_round_paths(state, snapshot),
            )

    def test_committed_source_rejects_mixed_and_three_dot_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = init_repo(root)
            base = git(repo, "rev-parse", "HEAD")
            target = commit_file(repo, "src/App.java", "class App {}\n", "feature")

            def repo_state() -> dict:
                return {
                    "root": str(repo),
                    "label": "repo",
                    "base_head": target,
                    "initial_dirty": {},
                }

            with self.assertRaisesRegex(SystemExit, "不能在同一实现轮次混用"):
                implementation_session.resolve_committed_diff_sources(
                    [repo_state()],
                    [f"{base}..{target}"],
                    [target],
                )
            with self.assertRaisesRegex(SystemExit, "不支持三点范围"):
                implementation_session.resolve_committed_diff_sources(
                    [repo_state()],
                    [f"{base}...{target}"],
                    [],
                )


if __name__ == "__main__":
    unittest.main()
