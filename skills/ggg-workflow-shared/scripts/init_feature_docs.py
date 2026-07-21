#!/usr/bin/env python3
"""初始化需求目录。第一阶段只生成 meta.json 和 00-baseline.md。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from workflow_contracts import PUBLIC_PHASES


def slugify(text: str) -> str:
    cleaned = re.sub(r"\s+", "-", text.strip())
    cleaned = re.sub(r"[\\\\/:*?\"<>|]+", "-", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or "new-feature"


def detect_repo_root(explicit_repo_root: str | None) -> Path:
    if explicit_repo_root:
        return Path(explicit_repo_root).resolve()
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=Path.cwd(),
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return Path.cwd().resolve()
    if completed.returncode == 0 and completed.stdout.strip():
        return Path(completed.stdout.strip()).resolve()
    return Path.cwd().resolve()


def detect_workflow_root(repo_root: Path) -> Path | None:
    for relative in [Path("ggg/workflow"), Path("ggg/tech-workflow")]:
        candidate = repo_root / relative
        if (candidate / "templates").exists():
            return candidate
    return None


def copy_file(src: Path, dst: Path, overwrite: bool) -> bool:
    if dst.exists() and not overwrite:
        return False
    shutil.copyfile(src, dst)
    return True


def sync_workflow_assets(repo_root: Path, overwrite: bool) -> tuple[Path, int, int]:
    skill_root = Path(__file__).resolve().parent.parent
    asset_root = skill_root / "assets" / "workflow"
    workflow_root = repo_root / "ggg" / "workflow"
    templates_src = asset_root / "templates"
    templates_dst = workflow_root / "templates"

    workflow_root.mkdir(parents=True, exist_ok=True)
    templates_dst.mkdir(parents=True, exist_ok=True)

    readme_src = asset_root / "README.md"
    copied = 0
    skipped = 0
    if readme_src.exists():
        if copy_file(readme_src, workflow_root / "README.md", overwrite):
            copied += 1
        else:
            skipped += 1

    for pattern in ("*.md", "*.sql"):
        for src in templates_src.glob(pattern):
            dst = templates_dst / src.name
            if copy_file(src, dst, overwrite):
                copied += 1
            else:
                skipped += 1

    return workflow_root, copied, skipped


def require_single_line(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise SystemExit(f"{label} 不能为空")
    if "\n" in normalized or "\r" in normalized:
        raise SystemExit(f"{label} 必须是单行文本")
    return normalized


def render_baseline(
    template: str,
    feature_name: str,
    recommended_mode: str,
    recommendation_reason: str,
    selection_source: str,
) -> str:
    replacements = {
        "{{feature_name}}": feature_name,
        "{{recommended_mode}}": recommended_mode,
        "{{recommendation_reason}}": recommendation_reason,
        "{{selection_source}}": selection_source,
    }
    rendered = template
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)
    return rendered


def write_meta_json(
    target_dir: Path,
    feature_name: str,
    recommended_mode: str,
    recommendation_reason: str,
    selection_source: str,
) -> None:
    payload = {
        "workflow_schema_version": 5,
        "feature_name": feature_name,
        "mode_selection": {
            "recommended_mode": recommended_mode,
            "recommendation_reason": recommendation_reason,
            "selected_mode": "full",
            "selection_source": selection_source,
        },
        "current_phase": "需求受理",
        "current_status": "待澄清",
        "primary_project": "",
        "gates": {
            "clarification_required": True,
            "clarification_confirmed": False,
            "alignment_completed": False,
            "design_confirmed": False,
            "tasks_confirmed": False,
            "implementation_completed": False,
            "test_passed": False,
            "release_ready": False,
            "business_model_confirmed": False,
            "upstream_contract_confirmed": False,
            "schema_confirmed": False,
            "sql_confirmed": False,
        },
        "review_flags": {
            "alignment_needs_review": False,
            "design_needs_review": False,
            "tasks_needs_review": False,
        },
        "review_status": "not_run",
        "clarification": {
            "count": 0,
            "last_source": "",
            "last_summary": "",
            "last_updated_at": "",
            "last_impacts": [],
            "confirmed_baseline_sha256": "",
            "baseline_confirmation_source": "",
            "baseline_confirmed_at": "",
        },
        "schema_confirmation": {
            "confirmed_schema_sha256": "",
            "confirmation_source": "",
            "confirmed_at": "",
        },
        "sql_confirmation": {
            "impact_type": "",
            "research_semantic_fingerprint": "",
            "draft_semantic_fingerprint": "",
            "semantic_fingerprint": "",
            "confirmation_source": "",
            "confirmed_at": "",
        },
        "documents": {
            "baseline": "00-baseline.md",
            "research": "01-research.md",
            "design": "02-design.md",
            "interface_details": "interface-details/",
            "tasks": "03-tasks.md",
            "sql_draft": "sql-draft.sql",
            "schema": "04-schema.sql",
            "implementation_log": "05-implementation-log.md",
            "code_review": "06-code-review.md",
            "test_report": "07-test-report.md",
        },
    }
    (target_dir / "meta.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化需求文档目录")
    parser.add_argument("--repo-root", help="项目根目录；默认当前 Git 仓库根目录，非 Git 目录时使用当前目录")
    parser.add_argument("--feature-name", required=True, help="需求名称")
    parser.add_argument(
        "--recommended-mode",
        required=True,
        choices=["quick", "full"],
        help="AI 推荐模式；只记录推荐，不替代用户最终选择",
    )
    parser.add_argument("--recommendation-reason", required=True, help="推荐 quick/full 的具体依据")
    parser.add_argument(
        "--selection-source",
        required=True,
        help="用户最终选择 full 或授权 AI 决定的消息定位",
    )
    parser.add_argument("--date", help="目录日期，默认今天，格式 YYYYMMDD")
    parser.add_argument("--refresh-workflow-assets", action="store_true", help="覆盖同步 ggg/workflow 下的共享 README 和模板")
    args = parser.parse_args()

    feature_name = require_single_line(args.feature_name, "--feature-name")
    recommendation_reason = require_single_line(
        args.recommendation_reason,
        "--recommendation-reason",
    )
    selection_source = require_single_line(args.selection_source, "--selection-source")
    if selection_source in {"用户消息", "用户选择", "AI决定", "已授权"}:
        raise SystemExit("--selection-source 必须包含可回查的用户选择或授权定位")
    repo_root = detect_repo_root(args.repo_root)
    workflow_root, copied_count, skipped_count = sync_workflow_assets(repo_root, overwrite=args.refresh_workflow_assets)
    # 新需求固定使用当前 Skill 自带的最新 schema 模板，避免项目内旧模板与新版 meta 门禁不兼容。
    templates_dir = Path(__file__).resolve().parent.parent / "assets" / "workflow" / "templates"
    features_dir = repo_root / "ggg" / "features"
    date_str = args.date or dt.date.today().strftime("%Y%m%d")
    target_dir = features_dir / f"{date_str}-{slugify(feature_name)}"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "assets").mkdir(exist_ok=True)

    baseline_path = target_dir / "00-baseline.md"
    meta_path = target_dir / "meta.json"
    if not baseline_path.exists():
        template = (templates_dir / "baseline-template.md").read_text(encoding="utf-8")
        baseline_path.write_text(
            render_baseline(
                template,
                feature_name,
                args.recommended_mode,
                recommendation_reason,
                selection_source,
            ),
            encoding="utf-8",
        )
    if not meta_path.exists():
        write_meta_json(
            target_dir,
            feature_name,
            args.recommended_mode,
            recommendation_reason,
            selection_source,
        )

    print(f"[OK] 已初始化需求目录: {target_dir}")
    if args.refresh_workflow_assets:
        print(f"[OK] 已覆盖同步工作流模板目录: {workflow_root}，共更新 {copied_count} 个文件")
    else:
        print(f"[OK] 已同步工作流模板目录: {workflow_root}，新增/缺失补齐 {copied_count} 个文件，保留现有文件 {skipped_count} 个")
    if baseline_path.exists() and meta_path.exists():
        print("[OK] 当前阶段仅确保存在 meta.json 与 00-baseline.md，不覆盖已有需求内容")
    print(f"[OK] 当前 dist 公开流程支持：{' / '.join(PUBLIC_PHASES)}")


if __name__ == "__main__":
    main()
