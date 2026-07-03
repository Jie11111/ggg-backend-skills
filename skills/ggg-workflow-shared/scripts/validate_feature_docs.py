#!/usr/bin/env python3
"""按当前阶段校验需求目录下关键文档的最小完整性。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from workflow_validation import validate_feature_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="校验需求文档目录")
    parser.add_argument("--feature-dir", required=True, help="需求目录")
    args = parser.parse_args()

    feature_dir = Path(args.feature_dir).resolve()
    errors = validate_feature_dir(feature_dir)
    if errors:
        print("[FAIL] 文档校验未通过")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    print("[OK] 文档校验通过")


if __name__ == "__main__":
    main()
