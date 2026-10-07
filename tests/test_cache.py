import pytest
from pydantic import ValidationError

import app.extractor as extractor
from app.extractor import extract
from tests.test_extractor import INVALID_JSON, VALID_JSON, FakeClient, temp_cache  # noqa: F401


def test_second_call_for_same_image_is_served_from_disk():
    client = FakeClient(VALID_JSON)
    first, first_meta = extract(b"img", client=client, model="m")
    second, second_meta = extract(b"img", client=client, model="m")

    assert len(client.calls) == 1
    assert second == first
    assert first_meta["cached"] is False and second_meta["cached"] is True
    # Latency and usage describe the original call.
    assert second_meta["usage"] == first_meta["usage"]
    assert second_meta["latency_seconds"] == first_meta["latency_seconds"]


def test_different_model_misses_the_cache():
    client = FakeClient(VALID_JSON, VALID_JSON)
    extract(b"img", client=client, model="a")
    extract(b"img", client=client, model="b")
    assert len(client.calls) == 2


def test_different_image_misses_the_cache():
    client = FakeClient(VALID_JSON, VALID_JSON)
    extract(b"one", client=client, model="m")
    extract(b"two", client=client, model="m")
    assert len(client.calls) == 2


def test_changed_prompt_misses_the_cache(monkeypatch):
    client = FakeClient(VALID_JSON, VALID_JSON)
    extract(b"img", client=client, model="m")
    # Edited without bumping PROMPT_VERSION: the prompt hash must still miss.
    monkeypatch.setattr(extractor, "PROMPT", extractor.PROMPT + " Be careful.")
    extract(b"img", client=client, model="m")
    assert len(client.calls) == 2


def test_cache_off_bypasses_read_and_write(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_CACHE", "0")
    client = FakeClient(VALID_JSON, VALID_JSON)
    extract(b"img", client=client, model="m")
    extract(b"img", client=client, model="m")
    assert len(client.calls) == 2
    assert not (tmp_path / "cache").exists()


def test_failed_extraction_leaves_nothing_in_the_cache(tmp_path):
    client = FakeClient(INVALID_JSON, INVALID_JSON)
    with pytest.raises(ValidationError):
        extract(b"img", client=client, model="m")
    assert not list((tmp_path / "cache").glob("*.json"))
