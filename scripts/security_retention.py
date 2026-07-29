"""Print a dry-run retention report; destructive deletion is intentionally absent."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


def main() -> None:
    from app.security.retention import dry_run_retention

    print(json.dumps(dry_run_retention(), indent=2))


if __name__ == "__main__":
    main()
