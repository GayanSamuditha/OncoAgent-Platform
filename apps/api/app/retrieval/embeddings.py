from dataclasses import dataclass
from typing import Any, Protocol, cast

import numpy as np

POOLING_CLS = "cls"
POOLING_MEAN = "attention_mask_mean"
NORMALIZATION_L2 = "l2"


@dataclass(frozen=True)
class ProviderMetadata:
    provider_id: str
    query_model_name: str
    document_model_name: str
    query_model_revision: str
    document_model_revision: str
    embedding_dimension: int
    device: str
    pooling_strategy: str
    normalization_strategy: str
    query_max_length: int
    document_max_length: int


class DenseRetrievalProvider(Protocol):
    metadata: ProviderMetadata
    tokenizer: Any

    def load(self) -> None: ...

    def encode_queries(self, texts: list[str]) -> list[list[float]]: ...
    def encode_documents(self, documents: list[tuple[str, str]]) -> list[list[float]]: ...
    def health(self) -> dict[str, Any]: ...


def select_device(override: str = "auto") -> str:
    try:
        import torch

        if override == "cpu":
            return "cpu"
        if override in {"auto", "mps"} and torch.backends.mps.is_available():
            return "mps"
    except (ImportError, AttributeError):
        pass
    return "cpu"


def cls_pool(last_hidden_state: Any) -> Any:
    return last_hidden_state[:, 0, :]


def mean_pool(last_hidden_state: Any, attention_mask: Any) -> Any:
    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    return (last_hidden_state * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)


def normalize_vectors(vectors: Any) -> Any:
    import torch

    return torch.nn.functional.normalize(vectors, p=2, dim=1)


class _TransformerProvider:
    def __init__(self, metadata: ProviderMetadata) -> None:
        self.metadata = metadata
        self.tokenizer: Any = None
        self.model: Any = None
        self.error: str | None = None

    def _load_model(self, name: str, revision: str) -> tuple[Any, Any]:
        from transformers import AutoModel, AutoTokenizer

        tokenizer = cast(Any, AutoTokenizer).from_pretrained(
            name, revision=revision, trust_remote_code=False
        )
        try:
            model = AutoModel.from_pretrained(  # nosec B615
                name, revision=revision, trust_remote_code=False, use_safetensors=True
            )
        except OSError:
            model = AutoModel.from_pretrained(name, revision=revision, trust_remote_code=False)  # nosec B615
        model.eval()
        model.to(self.metadata.device)
        return tokenizer, model

    def _encode(
        self, texts: list[str], tokenizer: Any, model: Any, max_length: int, pooling: str
    ) -> list[list[float]]:
        import torch

        encoded = tokenizer(
            texts, padding=True, truncation=True, max_length=max_length, return_tensors="pt"
        )
        encoded = {key: value.to(self.metadata.device) for key, value in encoded.items()}
        with torch.inference_mode():
            output = model(**encoded)
            pooled = (
                cls_pool(output.last_hidden_state)
                if pooling == POOLING_CLS
                else mean_pool(output.last_hidden_state, encoded["attention_mask"])
            )
            vectors = normalize_vectors(pooled)
        return cast(list[list[float]], vectors.detach().cpu().tolist())

    def health(self) -> dict[str, Any]:
        return {
            "configured": True,
            "loaded": self.model is not None,
            "available": self.model is not None and self.error is None,
            "error": self.error,
            **self.metadata.__dict__,
        }


class MedCPTDualEncoderProvider(_TransformerProvider):
    def __init__(
        self,
        query_name: str,
        document_name: str,
        query_revision: str,
        document_revision: str,
        device: str,
        query_max_length: int = 64,
        document_max_length: int = 512,
    ) -> None:
        super().__init__(
            ProviderMetadata(
                "medcpt",
                query_name,
                document_name,
                query_revision,
                document_revision,
                768,
                select_device(device),
                POOLING_CLS,
                NORMALIZATION_L2,
                query_max_length,
                document_max_length,
            )
        )
        self.query_tokenizer: Any = None
        self.query_model: Any = None
        self.document_model: Any = None

    def load(self) -> None:
        if self.query_model is not None and self.document_model is not None:
            return
        try:
            self.query_tokenizer, self.query_model = self._load_model(
                self.metadata.query_model_name, self.metadata.query_model_revision
            )
            self.tokenizer, self.document_model = self._load_model(
                self.metadata.document_model_name, self.metadata.document_model_revision
            )
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            raise RuntimeError(self.error) from exc

    def encode_queries(self, texts: list[str]) -> list[list[float]]:
        self.load()
        return self._encode(
            texts,
            self.query_tokenizer,
            self.query_model,
            self.metadata.query_max_length,
            POOLING_CLS,
        )

    def encode_documents(self, documents: list[tuple[str, str]]) -> list[list[float]]:
        self.load()
        texts = [f"{title}\n{body}" for title, body in documents]
        return self._encode(
            texts,
            self.tokenizer,
            self.document_model,
            self.metadata.document_max_length,
            POOLING_CLS,
        )


class BioClinicalBERTProvider(_TransformerProvider):
    """Comparison provider retained from Phase 2; it uses one encoder and mean pooling."""

    def __init__(self, model_name: str, revision: str, device: str, max_length: int = 256) -> None:
        super().__init__(
            ProviderMetadata(
                "bioclinicalbert",
                model_name,
                model_name,
                revision,
                revision,
                768,
                select_device(device),
                POOLING_MEAN,
                NORMALIZATION_L2,
                max_length,
                max_length,
            )
        )

    def load(self) -> None:
        if self.model is not None:
            return
        try:
            self.tokenizer, self.model = self._load_model(
                self.metadata.document_model_name, self.metadata.document_model_revision
            )
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            raise RuntimeError(self.error) from exc

    def encode_queries(self, texts: list[str]) -> list[list[float]]:
        self.load()
        return self._encode(
            texts, self.tokenizer, self.model, self.metadata.query_max_length, POOLING_MEAN
        )

    def encode_documents(self, documents: list[tuple[str, str]]) -> list[list[float]]:
        self.load()
        return self._encode(
            [f"{title}\n{body}" for title, body in documents],
            self.tokenizer,
            self.model,
            self.metadata.document_max_length,
            POOLING_MEAN,
        )


class DeterministicFakeProvider:
    def __init__(self, provider_id: str | int = "fake", dimension: int = 768) -> None:
        if isinstance(provider_id, int):
            dimension, provider_id = provider_id, "fake"
        self.metadata = ProviderMetadata(
            provider_id,
            "fake-query",
            "fake-document",
            "test",
            "test",
            dimension,
            "cpu",
            POOLING_CLS,
            NORMALIZATION_L2,
            64,
            512,
        )
        self.tokenizer = None

    def _vectors(self, texts: list[str]) -> list[list[float]]:
        result: list[list[float]] = []
        for text in texts:
            values = np.zeros(self.metadata.embedding_dimension, dtype=np.float32)
            for token in text.lower().split():
                values[hash(token) % self.metadata.embedding_dimension] += 1
            norm = np.linalg.norm(values)
            result.append((values / norm if norm else values).tolist())
        return result

    def encode_queries(self, texts: list[str]) -> list[list[float]]:
        return self._vectors(texts)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.encode_queries(texts)

    def encode_documents(self, documents: list[tuple[str, str]]) -> list[list[float]]:
        return self._vectors([f"{title} {body}" for title, body in documents])

    def health(self) -> dict[str, Any]:
        return {"configured": True, "loaded": True, "available": True, **self.metadata.__dict__}


FakeEmbeddingProvider = DeterministicFakeProvider
