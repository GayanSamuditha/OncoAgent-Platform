import argparse
import sys

sys.path.insert(0, "apps/api")
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.retrieval.documents import build_documents
from transformers import AutoTokenizer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--document-type", choices=["encounter"], default="encounter")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    settings = get_settings()
    tokenizer = AutoTokenizer.from_pretrained(settings.clinical_embedding_model, revision=settings.clinical_embedding_model_revision)
    with SessionLocal() as session:
        count = build_documents(session, args.dataset_id, args.document_type, args.limit, tokenizer)
    print(f"Built or verified {count} clinical documents for dataset {args.dataset_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
