from functools import lru_cache

from app.core.config import Settings
from app.retrieval.embeddings import BioClinicalBERTProvider


@lru_cache
def get_embedding_provider(model_name: str, revision: str, device: str, max_length: int) -> BioClinicalBERTProvider:
    return BioClinicalBERTProvider(model_name, revision, device, max_length)


def provider_for(settings: Settings) -> BioClinicalBERTProvider:
    return get_embedding_provider(settings.clinical_embedding_model, settings.clinical_embedding_model_revision, settings.embedding_device, settings.embedding_max_sequence_length)
