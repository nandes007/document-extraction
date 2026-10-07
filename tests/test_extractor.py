import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from openai import APIError, APITimeoutError, RateLimitError
from pydantic import ValidationError

from app.extractor import ProviderError, extract
from app.main import app
from tests.test_schema import VALID_DOCUMENT

VALID_JSON = json.dumps(VALID_DOCUMENT)
# status "not_present" with a value: rejected by the schema, so it drives the retry.
INVALID_JSON = json.dumps(
    VALID_DOCUMENT | {"discount": {"value": 5000, "status": "not_present",
                                   "confidence": 0.5, "evidence": None}}
)


REQUEST = httpx.Request("POST", "http://provider.invalid")


def _response(status: int) -> httpx.Response:
    return httpx.Response(status, request=REQUEST)


class FakeClient:
    """Stands in for openai.OpenAI. Returns the queued replies in order."""

    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.replies.pop(0)
        message = SimpleNamespace(content=content)
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=180)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


@pytest.fixture(autouse=True)
def temp_cache(tmp_path, monkeypatch):
    """Every test gets its own cache dir; none touches the real one."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("LLM_CACHE", "1")


def test_valid_first_reply_is_not_retried():
    client = FakeClient(VALID_JSON)
    document, _ = extract(b"fake image", "image/jpeg", client=client, model="m")
    assert document.total.value == 161700
    assert len(client.calls) == 1


def test_invalid_reply_is_retried_once_with_the_error():
    client = FakeClient(INVALID_JSON, VALID_JSON)
    document, _ = extract(b"fake image", "image/jpeg", client=client, model="m")

    assert document.discount.value is None
    assert len(client.calls) == 2
    # The second call must carry the rejected answer and why it was rejected.
    retry_messages = client.calls[1]["messages"]
    assert retry_messages[-2]["content"] == INVALID_JSON
    assert "failed validation" in retry_messages[-1]["content"]


def test_two_invalid_replies_raise():
    client = FakeClient(INVALID_JSON, INVALID_JSON)
    with pytest.raises(ValidationError):
        extract(b"fake image", "image/jpeg", client=client, model="m")
    assert len(client.calls) == 2


def test_image_is_sent_as_a_data_url():
    client = FakeClient(VALID_JSON)
    extract(b"fake image", "image/png", client=client, model="m")
    parts = client.calls[0]["messages"][-1]["content"]
    assert parts[0]["image_url"]["url"].startswith("data:image/png;base64,")


def test_pdf_pages_go_in_one_call_with_a_page_note():
    from tests.test_pages import make_pdf

    client = FakeClient(VALID_JSON)
    extract(make_pdf(2), "application/pdf", client=client, model="m")
    assert len(client.calls) == 1
    parts = client.calls[0]["messages"][-1]["content"]
    assert parts[0] == {"type": "text", "text": "The document has 2 pages, in order."}
    assert [p["type"] for p in parts[1:]] == ["image_url", "image_url"]
    assert all(p["image_url"]["url"].startswith("data:image/png;base64,") for p in parts[1:])


def test_single_image_has_one_part_and_no_note():
    client = FakeClient(VALID_JSON)
    extract(b"fake image", "image/jpeg", client=client, model="m")
    parts = client.calls[0]["messages"][-1]["content"]
    assert [p["type"] for p in parts] == ["image_url"]


def test_usage_and_attempts_are_summed_across_a_retry():
    client = FakeClient(INVALID_JSON, VALID_JSON)
    _, meta = extract(b"fake image", "image/jpeg", client=client, model="m")
    assert meta["attempts"] == 2
    # total_tokens is summed as reported, not recomputed (180 != 100 + 50).
    assert meta["usage"] == {
        "prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 360,
    }
    assert meta["cached"] is False
    assert meta["model"] == "m" and meta["prompt_version"]


# --- the API surface, no provider involved -------------------------------

client = TestClient(app)


def test_health_does_not_need_configuration():
    assert client.get("/health").json() == {"status": "ok"}


def test_non_image_upload_is_rejected():
    response = client.post("/extract", files={"file": ("notes.txt", b"hi", "text/plain")})
    assert response.status_code == 415


@pytest.mark.parametrize(
    "error, status",
    [
        (RateLimitError("slow down", response=_response(429), body=None), 429),
        (APITimeoutError(request=REQUEST), 504),
        (APIError("boom", REQUEST, body=None), 502),
        (ProviderError("no choices"), 502),
    ],
)
def test_provider_errors_map_to_status_codes(monkeypatch, error, status):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr("app.main.extract", fail)
    response = client.post("/extract", files={"file": ("a.jpg", b"x", "image/jpeg")})
    assert response.status_code == status


def test_response_is_a_document_and_meta_envelope(monkeypatch):
    fake = FakeClient(VALID_JSON)
    monkeypatch.setattr(
        "app.main.extract",
        lambda image, content_type: extract(image, content_type, client=fake, model="m"),
    )
    body = client.post(
        "/extract", files={"file": ("a.jpg", b"x", "image/jpeg")}
    ).json()
    assert body["document"]["total"]["value"] == 161700
    assert body["meta"]["cached"] is False
