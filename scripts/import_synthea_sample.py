#!/usr/bin/env python3
"""Import a bounded Synthea FHIR sample into PostgreSQL."""

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.ingestion.service import (
    DEFAULT_PATIENT_LIMIT,
    HARD_PATIENT_LIMIT,
    import_synthea_sample,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--patient-limit", type=int, default=DEFAULT_PATIENT_LIMIT)
    parser.add_argument("--dataset-name", required=True)
    parser.add_argument("--unsafe-override", action="store_true")
    args = parser.parse_args()
    if args.patient_limit > HARD_PATIENT_LIMIT and args.unsafe_override:
        print(
            f"WARNING: unsafe override enabled for patient limit {args.patient_limit}; archive remains streamed.",
            file=sys.stderr,
        )
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL must be set")
    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        with Session(engine) as session:
            summary = import_synthea_sample(
                session,
                args.archive,
                args.dataset_name,
                args.patient_limit,
                args.unsafe_override,
            )
        print(f"dataset_id: {summary.dataset_id}")
        print(f"ingestion_run_id: {summary.ingestion_run_id}")
        print(f"status: {summary.status}")
        print(f"processed_bundle_count: {summary.processed_bundle_count}")
        print(f"imported_patient_count: {summary.imported_patient_count}")
        print(f"imported_resource_count: {summary.imported_resource_count}")
        print(f"skipped_resource_count: {summary.skipped_resource_count}")
        print(f"error_count: {summary.error_count}")
        print("resource_counts:")
        for resource_type, count in sorted(summary.resource_counts.items()):
            print(f"  - {resource_type}: {count}")
    except (OSError, ValueError) as exc:
        print(f"ingestion failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
