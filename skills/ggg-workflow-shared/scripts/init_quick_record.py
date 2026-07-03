#!/usr/bin/env python3
"""初始化 quick 小需求记录，不创建 full 需求目录。"""

from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path


def slugify(text: str) -> str:
    cleaned = re.sub(r"\s+", "-", text.strip())
    cleaned = re.sub(r"[\\\\/:*?\"<>|]+", "-", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or "quick-task"


def detect_repo_root(explicit_repo_root: str | None) -> Path:
    return Path(explicit_repo_root).resolve() if explicit_repo_root else Path.cwd().resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化 quick 小需求记录，不创建 full 需求目录")
    parser.add_argument("--repo-root", help="仓库根目录，默认当前目录")
    parser.add_argument("--quick-name", required=True, help="quick 小需求名称")
    parser.add_argument("--date", help="目录日期，默认今天，格式 YYYYMMDD")
    args = parser.parse_args()

    repo_root = detect_repo_root(args.repo_root)
    date_str = args.date or dt.date.today().strftime("%Y%m%d")
    quick_dir = repo_root / "ggg" / "quick" / f"{date_str}-{slugify(args.quick_name)}"
    quick_dir.mkdir(parents=True, exist_ok=True)

    template_path = Path(__file__).resolve().parent.parent / "assets" / "workflow" / "templates" / "quick-record-template.md"
    target_path = quick_dir / "quick.md"
    if not target_path.exists():
        template = template_path.read_text(encoding="utf-8")
        target_path.write_text(template.replace("{{quick_name}}", args.quick_name), encoding="utf-8")
        print(f"[OK] 已创建 quick 小需求记录: {target_path}")
    else:
        print(f"[OK] quick 小需求记录已存在，未覆盖: {target_path}")

    print("[OK] quick 记录不创建 meta.json，不进入 full 需求状态机")


if __name__ == "__main__":
    main()
