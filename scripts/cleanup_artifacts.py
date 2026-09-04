"""Safely preview or remove repository-generated development artifacts."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = (
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "apps/api/.pytest_cache",
    "apps/api/.mypy_cache",
    "apps/api/.ruff_cache",
    "apps/api/__pycache__",
    "apps/api/alembic/__pycache__",
    "apps/api/alembic/versions/__pycache__",
    "apps/api/app/__pycache__",
    "apps/api/app/api/__pycache__",
    "apps/api/app/core/__pycache__",
    "apps/api/app/cross_framework/__pycache__",
    "apps/api/app/db/__pycache__",
    "apps/api/app/governance/__pycache__",
    "apps/api/app/identity/__pycache__",
    "apps/api/app/ingestion/__pycache__",
    "apps/api/app/models/__pycache__",
    "apps/api/app/observability/__pycache__",
    "apps/api/app/performance/__pycache__",
    "apps/api/app/repositories/__pycache__",
    "apps/api/app/release_evaluation/__pycache__",
    "apps/api/app/resilience/__pycache__",
    "apps/api/app/retrieval/__pycache__",
    "apps/api/app/schemas/__pycache__",
    "apps/api/app/security/__pycache__",
    "apps/api/app/services/__pycache__",
    "apps/api/app/temporal/__pycache__",
    "apps/api/app/workflow/__pycache__",
    "apps/api/tests/__pycache__",
    "apps/api/tests/core/__pycache__",
    "apps/api/tests/crewai/__pycache__",
    "apps/api/tests/identity/__pycache__",
    "apps/api/tests/ingestion/__pycache__",
    "apps/api/tests/mcp/__pycache__",
    "apps/api/tests/observability/__pycache__",
    "apps/api/tests/performance/__pycache__",
    "apps/api/tests/release_evaluation/__pycache__",
    "apps/api/tests/resilience/__pycache__",
    "apps/api/tests/retrieval/__pycache__",
    "apps/api/tests/security/__pycache__",
    "apps/api/tests/services/__pycache__",
    "apps/api/tests/temporal/__pycache__",
    "apps/api/tests/workflow/__pycache__",
    "apps/crewai_client/.ruff_cache",
    "apps/crewai_client/__pycache__",
    "apps/mcp_server/__pycache__",
    "apps/web/.next",
    "apps/web/playwright-report",
    "apps/web/test-results",
    "apps/web/tsconfig.tsbuildinfo",
    "demo_outputs",
    "evaluation_outputs",
    "loadtest_outputs",
    "performance_outputs",
    "scripts/__pycache__",
    "loadtests/__pycache__",
    "loadtests/tests/__pycache__",
)
PROTECTED_PREFIXES = (
    ".env",
    "backups",
    "generated_fhir",
    "synthea_",
    "ollama_models",
    "model_cache",
    "model_caches",
    "model_weights",
    "uploads",
    "temporal-data",
    "prometheus-data",
    "tempo-data",
    "grafana-data",
)


class CleanupError(RuntimeError):
    """A cleanup target is unsafe or outside the explicit allowlist."""


def expand_allowlist() -> list[Path]:
    paths: list[Path] = []
    for entry in ALLOWLIST:
        paths.append(ROOT / entry)
    return paths


def validate_target(path: Path) -> None:
    relative = path.relative_to(ROOT).as_posix()
    if any(relative == prefix or relative.startswith(prefix + "/") for prefix in PROTECTED_PREFIXES):
        raise CleanupError(f"protected path is not cleanable: {relative}")
    resolved = path.resolve(strict=False)
    if resolved != ROOT and ROOT not in resolved.parents:
        raise CleanupError(f"path escapes repository: {relative}")
    if path.is_symlink():
        raise CleanupError(f"symlink traversal refused: {relative}")
    if path.is_dir():
        for directory, names, files in os.walk(path, followlinks=False):
            for name in [*names, *files]:
                child = Path(directory) / name
                if child.is_symlink():
                    raise CleanupError(f"symlink traversal refused: {child.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.dry_run == args.apply:
        print("Choose exactly one of --dry-run or --apply.", file=sys.stderr)
        return 2
    try:
        targets = expand_allowlist()
        for target in targets:
            validate_target(target)
        existing = [path for path in targets if path.exists()]
        for path in existing:
            action = "would remove" if args.dry_run else "removing"
            print(f"{action} {path.relative_to(ROOT)}")
        if args.apply:
            for path in existing:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
        print(f"{'previewed' if args.dry_run else 'removed'} {len(existing)} artifact path(s)")
        return 0
    except (CleanupError, OSError) as exc:
        print(f"artifact cleanup refused: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
