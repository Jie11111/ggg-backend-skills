#!/usr/bin/env python3
"""在统一 features 目录初始化 quick 小需求记录，不创建 full 状态文件。"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import subprocess
from pathlib import Path


SCHEMA_TEMPLATE = """-- GGG_SQL_SCHEMA_VERSION: 3
-- 变更目标:
-- 来源Cxx:
-- 来源Dxx:
-- SQL参考表:
-- SQL参考证据:
-- 最小变更结论:
-- 现有结构复用评估:
-- 核心写入:
-- 核心查询:
-- 索引/约束依据:
-- 数据规模与DDL风险:
-- 执行前备份:
-- 回滚方式:
-- 验证SQL:

-- 每条结构 DDL 前保留一条 GGG_DDL_OBJECT；members 必须完整列出真实字段、索引和约束。
-- GGG_DDL_OBJECT: {"object":"","operation":"","members":[],"risk":"","risk_reason":"","claims":[],"designs":[]}

"""


def slugify(text: str) -> str:
    cleaned = re.sub(r"\s+", "-", text.strip())
    cleaned = re.sub(r"[\\\\/:*?\"<>|]+", "-", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or "quick-task"


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


def require_single_line(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise SystemExit(f"{label} 不能为空")
    if "\n" in normalized or "\r" in normalized:
        raise SystemExit(f"{label} 必须是单行文本")
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description="在统一 features 目录初始化 quick 小需求记录，不创建 full 状态文件")
    parser.add_argument("--repo-root", help="项目根目录；默认当前 Git 仓库根目录，非 Git 目录时使用当前目录")
    parser.add_argument("--quick-name", required=True, help="quick 小需求名称")
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
        help="用户最终选择 quick 或授权 AI 决定的消息定位",
    )
    parser.add_argument("--date", help="目录日期，默认今天，格式 YYYYMMDD")
    parser.add_argument("--create-schema", action="store_true", help="按需创建与 full 同名的 04-schema.sql")
    parser.add_argument("--interface-name", action="append", default=[], help="按需创建接口明细；可重复传入")
    args = parser.parse_args()

    quick_name = require_single_line(args.quick_name, "--quick-name")
    recommendation_reason = require_single_line(
        args.recommendation_reason,
        "--recommendation-reason",
    )
    selection_source = require_single_line(args.selection_source, "--selection-source")
    if selection_source in {"用户消息", "用户选择", "AI决定", "已授权"}:
        raise SystemExit("--selection-source 必须包含可回查的用户选择或授权定位")
    repo_root = detect_repo_root(args.repo_root)
    date_str = args.date or dt.date.today().strftime("%Y%m%d")
    quick_dir = repo_root / "ggg" / "features" / f"{date_str}-{slugify(quick_name)}"
    quick_dir.mkdir(parents=True, exist_ok=True)

    template_path = Path(__file__).resolve().parent.parent / "assets" / "workflow" / "templates" / "quick-record-template.md"
    target_path = quick_dir / "quick.md"
    if not target_path.exists():
        template = template_path.read_text(encoding="utf-8")
        replacements = {
            "{{quick_name}}": quick_name,
            "{{recommended_mode}}": args.recommended_mode,
            "{{recommendation_reason}}": recommendation_reason,
            "{{selection_source}}": selection_source,
        }
        for placeholder, value in replacements.items():
            template = template.replace(placeholder, value)
        target_path.write_text(template, encoding="utf-8")
        print(f"[OK] 已创建 quick 小需求记录: {target_path}")
    else:
        print(f"[OK] quick 小需求记录已存在，未覆盖: {target_path}")

    if args.create_schema:
        schema_path = quick_dir / "04-schema.sql"
        if not schema_path.exists():
            schema_path.write_text(SCHEMA_TEMPLATE, encoding="utf-8")
            print(f"[OK] 已创建 quick SQL 产物: {schema_path}")
        else:
            print(f"[OK] quick SQL 产物已存在，未覆盖: {schema_path}")

    if args.interface_name:
        interface_dir = quick_dir / "interface-details"
        interface_dir.mkdir(exist_ok=True)
        template_path = template_path.parent / "interface-detail-template.md"
        existing_numbers = []
        for existing in interface_dir.glob("02-interface-*.md"):
            match = re.match(r"02-interface-(\d{2})-", existing.name)
            if match:
                existing_numbers.append(int(match.group(1)))
        next_number = max(existing_numbers, default=0) + 1
        for interface_name in args.interface_name:
            interface_slug = slugify(interface_name)
            existing_paths = sorted(interface_dir.glob(f"02-interface-*-{interface_slug}.md"))
            if existing_paths:
                print(f"[OK] quick 接口明细已存在，未重复创建: {existing_paths[0]}")
                continue
            interface_path = interface_dir / f"02-interface-{next_number:02d}-{interface_slug}.md"
            shutil.copyfile(template_path, interface_path)
            print(f"[OK] 已创建 quick 接口明细: {interface_path}")
            next_number += 1

    print("[OK] quick 与 full 统一落在 ggg/features；quick 不创建 meta.json，不进入 full 需求状态机")


if __name__ == "__main__":
    main()
