"""Response cache: one JSON file per (image, model, prompt) on disk.

Read at call time, not import time, so tests and `LLM_CACHE=0` runs can change
the settings without reloading the module.
"""

import hashlib
import json
import os
from pathlib import Path


def enabled() -> bool:
    return os.environ.get("LLM_CACHE", "1") != "0"


def _path(key: str) -> Path:
    return Path(os.environ.get("CACHE_DIR", ".cache/responses")) / f"{key}.json"


def make_key(
    image_bytes: bytes, model: str, prompt_version: str, prompt_fingerprint: str,
    reasoning_effort: str | None = None,
) -> str:
    """Hashing the prompt text too means an edit misses even without a version bump.

    The reasoning effort joins the key only when set, so entries made without
    it stay valid.
    """
    parts = [hashlib.sha256(image_bytes).hexdigest(), model, prompt_version,
             prompt_fingerprint]
    if reasoning_effort:
        parts.append(f"reasoning_effort={reasoning_effort}")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def read(key: str) -> dict | None:
    if not enabled():
        return None
    try:
        return json.loads(_path(key).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None  # a half-written file is a miss, not a crash


def write(key: str, entry: dict) -> None:
    if not enabled():
        return
    path = _path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(entry))
    tmp.replace(path)  # atomic, so a reader never sees a partial file
