import argparse
import sys
import time

sys.path.insert(0, "apps/api")
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.retrieval.indexing import index_documents
from app.retrieval.model_registry import provider_for


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--retrieval-provider", choices=["medcpt", "bioclinicalbert"], default="medcpt")
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    settings = get_settings()
    provider = provider_for(settings, args.retrieval_provider)
    provider.load()
    batch_size = args.batch_size or (settings.embedding_batch_size_mps if provider.metadata.device == "mps" else settings.embedding_batch_size_cpu)
    started = time.perf_counter()
    with SessionLocal() as session:
        run = index_documents(session, provider, args.dataset_id, settings.embedding_max_sequence_length, settings.embedding_token_overlap, batch_size, args.limit)
        print(f"Indexing run {run.id}: {run.status}; embeddings created={run.created_embedding_count}, skipped={run.skipped_embedding_count}.")
    print(f"Duration: {time.perf_counter() - started:.2f}s; device={provider.metadata.device}; provider={provider.metadata.provider_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
