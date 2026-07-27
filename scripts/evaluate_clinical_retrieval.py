import argparse
import json
import sys

sys.path.insert(0, "apps/api")
from app.retrieval.evaluation import summarize


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--evaluation-file", required=True)
    args = parser.parse_args()
    with open(args.evaluation_file, encoding="utf-8") as handle:
        cases = json.load(handle)["cases"]
    if not cases:
        print(json.dumps({"dataset_id": args.dataset_id, "status": "no_cases", "synthetic_development_evaluation": True}))
        return 0
    print(json.dumps({"dataset_id": args.dataset_id, "metrics": summarize([]), "case_count": len(cases)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
