from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

POOLING_METHOD = "attention_mask_mean_l2_normalized"


def mean_pool(last_hidden_state: Any, attention_mask: Any) -> Any:
    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    return (last_hidden_state * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)


def normalize_vectors(vectors: Any) -> Any:
    import torch
    return torch.nn.functional.normalize(vectors, p=2, dim=1)


@dataclass(frozen=True)
class EmbeddingInfo:
    model_name: str
    model_revision: str
    device: str
    dimension: int


class EmbeddingProvider(Protocol):
    info: EmbeddingInfo
    tokenizer: object
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbeddingProvider:
    def __init__(self, dimension: int = 768) -> None:
        self.info = EmbeddingInfo("fake-clinical-encoder", "test", "cpu", dimension)
        self.tokenizer = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        result: list[list[float]] = []
        for text in texts:
            values = np.zeros(self.info.dimension, dtype=np.float32)
            for token in text.lower().split():
                values[hash(token) % self.info.dimension] += 1.0
            norm = np.linalg.norm(values)
            result.append((values / norm if norm else values).tolist())
        return result


def select_device(override: str = "auto") -> str:
    try:
        import torch
        if override == "cpu":
            return "cpu"
        if override == "mps" and torch.backends.mps.is_available():
            return "mps"
        if override == "auto" and torch.backends.mps.is_available():
            return "mps"
    except (ImportError, AttributeError):
        pass
    return "cpu"


class BioClinicalBERTProvider:
    def __init__(self, model_name: str, revision: str, device_override: str, max_length: int) -> None:
        self.info = EmbeddingInfo(model_name, revision, select_device(device_override), 768)
        self.max_length = max_length
        self.tokenizer: Any = None
        self.model: Any = None
        self.error: str | None = None

    def load(self) -> None:
        if self.model is not None:
            return
        try:
            from transformers import AutoModel, AutoTokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(self.info.model_name, revision=self.info.model_revision)
            self.model = AutoModel.from_pretrained(self.info.model_name, revision=self.info.model_revision)
            self.model.eval()
            self.model.to(self.info.device)
        except Exception as exc:  # model availability must not prevent API startup
            self.error = f"{type(exc).__name__}: {exc}"
            raise RuntimeError(self.error) from exc

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.load()
        import torch
        assert self.tokenizer is not None and self.model is not None
        encoded = self.tokenizer(texts, padding=True, truncation=True, max_length=self.max_length, return_tensors="pt")
        encoded = {key: value.to(self.info.device) for key, value in encoded.items()}
        with torch.inference_mode():
            output = self.model(**encoded)
            vectors = normalize_vectors(mean_pool(output.last_hidden_state, encoded["attention_mask"]))
        return vectors.detach().cpu().tolist()
