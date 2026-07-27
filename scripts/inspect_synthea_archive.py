#!/usr/bin/env python3
"""Inspect Synthea archive metadata without extracting members."""

import argparse
import os
import tarfile
from collections import Counter
from pathlib import Path


def inspect_archive(path: Path) -> None:
    if not path.is_file() or path.suffixes[-2:] != [".tar", ".gz"]:
        raise ValueError("archive must be an existing .tar.gz file")
    categories: Counter[str] = Counter()
    representative: list[str] = []
    member_count = 0
    fhir_json_count = 0
    with tarfile.open(path, mode="r|gz") as archive:
        for member in archive:
            member_count += 1
            category = (
                member.name.split("/", 2)[1] if "/" in member.name else member.name
            )
            categories[category] += 1
            if (
                member.isfile()
                and "/fhir/" in member.name
                and member.name.endswith(".json")
            ):
                fhir_json_count += 1
                if len(representative) < 10:
                    representative.append(member.name)
    print(f"archive_filename: {path.name}")
    print(f"compressed_size_bytes: {os.path.getsize(path)}")
    print(f"member_count: {member_count}")
    print(f"fhir_json_member_count: {fhir_json_count}")
    print("detected_export_categories:")
    for category, count in sorted(categories.items()):
        print(f"  - {category}: {count}")
    print("representative_fhir_json_members:")
    for member in representative:
        print(f"  - {member}")
    print("extracted: false")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    args = parser.parse_args()
    try:
        inspect_archive(args.archive)
    except (OSError, tarfile.TarError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
