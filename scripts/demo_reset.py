"""CLI for a dry-run-by-default, exact-correlation demo reset."""

import argparse
import json
import sys

from app.db.session import SessionLocal
from app.services.demo_reset import (
    demo_scope_counts,
    reset_demo_records,
    sanitized_counts,
    validate_demo_id,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo-id", required=True)
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()
    try:
        demo_id = validate_demo_id(args.demo_id)
    except ValueError as exc:
        print(f"demo reset rejected: {exc}", file=sys.stderr)
        return 2

    try:
        with SessionLocal.begin() as session:
            if args.confirm:
                counts = reset_demo_records(session, demo_id)
                mode = "deleted"
            else:
                counts = demo_scope_counts(session, demo_id)
                mode = "dry_run"
    except Exception as exc:
        print(f"demo reset rolled back: {type(exc).__name__}", file=sys.stderr)
        return 1

    print(json.dumps({"demo_id": demo_id, "mode": mode, "record_counts": sanitized_counts(counts)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
