#!/usr/bin/env python3
"""Validate service configuration without printing secret values."""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

from app.core.config import get_settings
from app.core.runtime_config import validate_runtime_settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", choices=("api", "mcp", "worker"), default="api")
    args = parser.parse_args()
    issues = validate_runtime_settings(get_settings(), service=args.service)
    if issues:
        for issue in issues:
            print(f"INVALID {issue.field}: {issue.reason}")
        return 1
    print(f"configuration valid for {args.service}; secret values were not printed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
