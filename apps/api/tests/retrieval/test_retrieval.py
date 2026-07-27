import math

import pytest

from app.retrieval.chunking import chunk_text
from app.retrieval.embeddings import FakeEmbeddingProvider


class FakeTokenizer:
    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        return list(range(len(text.split())))

    def decode(self, token_ids: list[int], **_: object) -> str:
        return " ".join(f"token-{item}" for item in token_ids)


def test_short_document_is_one_chunk() -> None:
    chunks = chunk_text("one two three", FakeTokenizer(), max_length=16, overlap=2)
    assert len(chunks) == 1
    assert chunks[0].token_start == 0


def test_long_document_has_bounded_overlap() -> None:
    chunks = chunk_text(" ".join(str(i) for i in range(30)), FakeTokenizer(), max_length=12, overlap=3)
    assert len(chunks) > 1
    assert chunks[1].token_start == chunks[0].token_end - 3
    assert all(item.token_count <= 10 for item in chunks)


def test_fake_embeddings_are_normalized_and_deterministic() -> None:
    provider = FakeEmbeddingProvider(16)
    first = provider.embed(["hypertension elevated blood pressure"])[0]
    second = provider.embed(["hypertension elevated blood pressure"])[0]
    assert first == second
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0, rel_tol=1e-6)


def test_invalid_chunk_configuration_is_rejected() -> None:
    with pytest.raises(ValueError):
        chunk_text("a b", FakeTokenizer(), max_length=8, overlap=8)
