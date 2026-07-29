#!/usr/bin/env python3
"""Run the existing bounded Synthea importer; never downloads or invents data."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", default=os.getenv("SYNTHEA_ARCHIVE"))
    parser.add_argument("--dataset-name", default=os.getenv("SYNTHEA_DATASET_NAME", "synthea-eval-100"))
    parser.add_argument("--patient-limit", type=int, default=int(os.getenv("SYNTHEA_PATIENT_LIMIT", "100")))
    args = parser.parse_args()
    if not args.archive:
        print("SYNTHEA_ARCHIVE or --archive is required; no data was loaded")
        return 2
    return subprocess.call([
        sys.executable,
        os.path.join(os.path.dirname(__file__), "import_synthea_sample.py"),
        "--archive", args.archive,
        "--dataset-name", args.dataset_name,
        "--patient-limit", str(args.patient_limit),
    ])


if __name__ == "__main__":
    raise SystemExit(main())
