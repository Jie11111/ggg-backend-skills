#!/usr/bin/env python3
"""验证 full/quick 编码实现的任务、代码质量和验证证据。"""

from __future__ import annotations

import argparse
from pathlib import Path

import workflow_validation as validator


def main() -> None:
    parser = argparse.ArgumentParser(description="验证编码实现质量门禁")
    parser.add_argument("--record", required=True, help="05-implementation-log.md 或 quick.md 路径")
    args = parser.parse_args()

    record = Path(args.record).resolve()
    if record.name == "05-implementation-log.md":
        errors = validator.validate_implementation_completion(record)
    elif record.name == "quick.md":
        errors = validator.validate_quick_implementation_completion(record)
    else:
        raise SystemExit("--record 只支持 05-implementation-log.md 或 quick.md")

    if errors:
        print("[FAIL] 代码质量门禁未通过：")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)
    print("[OK] 编码实现质量门禁已通过")


if __name__ == "__main__":
    main()
