"""Verify the configured local Ollama endpoint and exact model tag."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse


def endpoint() -> str:
    return os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434").rstrip("/")


def model() -> str:
    return os.getenv("LOCAL_LLM_MODEL", "qwen3:8b")


def check() -> tuple[int, dict[str, object]]:
    base = endpoint()
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return 3, {"status": "error", "reason": "LOCAL_LLM_BASE_URL is not a valid HTTP(S) URL"}
    try:
        request = urllib.request.Request(f"{base}/api/tags", headers={"User-Agent": "oncoagent-ollama-check/1"})
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError):
        return 2, {"status": "not_evaluable", "endpoint": base, "reason": "Ollama endpoint unavailable"}
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return 3, {"status": "error", "endpoint": base, "reason": "Ollama returned malformed JSON"}
    tags = payload.get("models") if isinstance(payload, dict) else None
    names = {item.get("name") for item in tags if isinstance(item, dict)} if isinstance(tags, list) else set()
    configured = model()
    if configured not in names:
        return 2, {
            "status": "not_evaluable",
            "endpoint": base,
            "configured_model": configured,
            "reason": "configured Ollama model is not installed",
        }
    return 0, {"status": "passed", "endpoint": base, "configured_model": configured}


def prepare() -> int:
    executable = shutil.which("ollama")
    if executable is None:
        print(json.dumps({"status": "not_evaluable", "reason": "ollama executable unavailable"}))
        return 2
    code, result = check()
    if code == 2 and result.get("reason") == "Ollama endpoint unavailable":
        subprocess.Popen([executable, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(20):
            time.sleep(0.5)
            code, result = check()
            if code != 2:
                break
    if code == 2 and result.get("reason") == "configured Ollama model is not installed":
        completed = subprocess.run([executable, "pull", model()], capture_output=True, text=True, timeout=1800, check=False)
        if completed.returncode != 0:
            print(json.dumps({"status": "error", "reason": "ollama model download failed"}))
            return 3
        code, result = check()
    print(json.dumps(result, sort_keys=True))
    return code


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        return prepare()
    code, result = check()
    print(json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
