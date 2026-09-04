from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from scripts import cleanup_artifacts, ollama_check  # noqa: E402


def test_ollama_exact_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "qwen3:8b")

    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"models": [{"name": "qwen3:8b"}]}).encode()

    monkeypatch.setattr(ollama_check.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    code, result = ollama_check.check()
    assert code == 0
    assert result["configured_model"] == "qwen3:8b"


def test_ollama_missing_model_is_not_evaluable(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"models": []}'

    monkeypatch.setattr(ollama_check.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    code, result = ollama_check.check()
    assert code == 2
    assert result["status"] == "not_evaluable"


def test_ollama_malformed_response_is_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"not-json"

    monkeypatch.setattr(ollama_check.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    code, result = ollama_check.check()
    assert code == 3
    assert result["status"] == "error"


def test_cleanup_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "artifact"
    target.symlink_to(tmp_path / "outside", target_is_directory=True)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(cleanup_artifacts, "ROOT", tmp_path)
    monkeypatch.setattr(cleanup_artifacts, "ALLOWLIST", ("artifact",))
    try:
        with pytest.raises(cleanup_artifacts.CleanupError):
            cleanup_artifacts.validate_target(target)
    finally:
        monkeypatch.undo()
