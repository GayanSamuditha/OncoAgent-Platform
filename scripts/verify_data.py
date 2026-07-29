#!/usr/bin/env python3
"""Verify bounded synthetic dataset availability without exposing clinical data."""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

from app.db.session import SessionLocal
from app.models.ingestion import Dataset, Patient
from sqlalchemy import func, select


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-id")
    parser.add_argument("--dataset-name")
    parser.add_argument("--min-patients", type=int, default=1)
    args = parser.parse_args()
    with SessionLocal() as session:
        query = select(Dataset)
        if args.dataset_id:
            query = query.where(Dataset.id == args.dataset_id)
        if args.dataset_name:
            query = query.where(Dataset.name == args.dataset_name)
        datasets = list(session.scalars(query))
        if not datasets:
            print("no matching synthetic dataset")
            return 1
        for dataset in datasets:
            count = session.scalar(select(func.count()).select_from(Patient).where(Patient.dataset_id == dataset.id)) or 0
            print(f"dataset={dataset.id} name={dataset.name!r} patients={count} status={dataset.status}")
            if count < args.min_patients:
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
