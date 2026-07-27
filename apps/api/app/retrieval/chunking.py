from dataclasses import dataclass
from typing import Any, Protocol

CHUNKING_VERSION = "token-window-v1"


class Tokenizer(Protocol):
    def encode(self, text: str, add_special_tokens: bool = ...) -> list[int]: ...
    def decode(self, token_ids: list[int], skip_special_tokens: bool = ..., **kwargs: Any) -> str: ...


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    token_start: int
    token_end: int
    token_count: int


def chunk_text(text: str, tokenizer: Tokenizer, max_length: int = 256, overlap: int = 32) -> list[TextChunk]:
    if max_length < 8 or overlap < 0 or overlap >= max_length:
        raise ValueError("max_length must be >= 8 and overlap must be smaller than max_length")
    ids = tokenizer.encode(text, add_special_tokens=False)
    window = max_length - 2
    if not ids:
        return []
    chunks: list[TextChunk] = []
    start = 0
    while start < len(ids):
        end = min(start + window, len(ids))
        decoded = tokenizer.decode(ids[start:end], skip_special_tokens=True, clean_up_tokenization_spaces=True).strip()
        chunks.append(TextChunk(len(chunks), decoded, start, end, end - start))
        if end == len(ids):
            break
        start = end - min(overlap, window - 1)
    return chunks
