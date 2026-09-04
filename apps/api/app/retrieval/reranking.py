from dataclasses import dataclass
from typing import Any, Protocol, cast

from app.retrieval.embeddings import select_device


@dataclass(frozen=True)
class RerankerMetadata:
    provider_id: str
    model_name: str
    model_revision: str
    device: str
    batch_size: int


class RerankerProvider(Protocol):
    metadata: RerankerMetadata

    def load(self) -> None: ...
    def rerank(self, query: str, candidates: list[dict[str, Any]]) -> list[float]: ...
    def health(self) -> dict[str, Any]: ...


class MedCPTRerankerProvider:
    def __init__(self, model_name: str, revision: str, device: str, batch_size: int = 4) -> None:
        self.metadata = RerankerMetadata(
            "medcpt_cross_encoder", model_name, revision, select_device(device), batch_size
        )
        self.tokenizer: Any = None
        self.model: Any = None
        self.error: str | None = None

    def load(self) -> None:
        if self.model is not None:
            return
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            self.tokenizer = cast(Any, AutoTokenizer).from_pretrained(
                self.metadata.model_name,
                revision=self.metadata.model_revision,
                trust_remote_code=False,
            )
            try:
                self.model = AutoModelForSequenceClassification.from_pretrained(  # nosec B615
                    self.metadata.model_name,
                    revision=self.metadata.model_revision,
                    trust_remote_code=False,
                    use_safetensors=True,
                )
            except OSError:
                self.model = AutoModelForSequenceClassification.from_pretrained(  # nosec B615
                    self.metadata.model_name,
                    revision=self.metadata.model_revision,
                    trust_remote_code=False,
                )
            self.model.eval()
            self.model.to(self.metadata.device)
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            raise RuntimeError(self.error) from exc

    def rerank(self, query: str, candidates: list[dict[str, Any]]) -> list[float]:
        self.load()
        import torch

        scores: list[float] = []
        start = 0
        batch_size = max(1, self.metadata.batch_size)
        while start < len(candidates):
            end = min(len(candidates), start + batch_size)
            texts = [str(item.get("text_excerpt", "")) for item in candidates[start:end]]
            try:
                encoded = self.tokenizer(
                    [query] * len(texts),
                    texts,
                    padding=True,
                    truncation=True,
                    max_length=512,
                    return_tensors="pt",
                )
                encoded = {key: value.to(self.metadata.device) for key, value in encoded.items()}
                with torch.inference_mode():
                    logits = self.model(**encoded).logits
                scores.extend(float(value) for value in logits.reshape(-1).detach().cpu().tolist())
                start = end
            except RuntimeError as exc:
                is_memory_error = "out of memory" in str(exc).lower() or "mps" in str(exc).lower()
                if not is_memory_error or batch_size == 1:
                    raise
                batch_size = max(1, batch_size // 2)
                if hasattr(self.metadata, "batch_size"):
                    self.metadata = RerankerMetadata(
                        self.metadata.provider_id,
                        self.metadata.model_name,
                        self.metadata.model_revision,
                        self.metadata.device,
                        batch_size,
                    )
                if hasattr(torch, "mps") and torch.backends.mps.is_available():
                    torch.mps.empty_cache()
        return scores

    def health(self) -> dict[str, Any]:
        return {
            "configured": True,
            "loaded": self.model is not None,
            "available": self.model is not None and self.error is None,
            "error": self.error,
            **self.metadata.__dict__,
        }


class DeterministicFakeReranker:
    def __init__(self) -> None:
        self.metadata = RerankerMetadata("fake_reranker", "fake-reranker", "test", "cpu", 4)

    def load(self) -> None:
        return None

    def rerank(self, query: str, candidates: list[dict[str, Any]]) -> list[float]:
        terms = set(query.lower().split())
        return [
            float(len(terms & set(str(item.get("text_excerpt", "")).lower().split())))
            for item in candidates
        ]

    def health(self) -> dict[str, Any]:
        return {"configured": True, "loaded": True, "available": True, **self.metadata.__dict__}
