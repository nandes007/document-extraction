import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.extractor import extract
from app.main import app
from tests.test_schema import VALID_DOCUMENT

VALID_JSON = json.dumps(VALID_DOCUMENT)
# status "not_present" with a value: rejected by the schema, so it drives the retry.
INVALID_JSON = json.dumps(
    VALID_DOCUMENT | {"discount": {"value": 5000, "status": "not_present",
                                   "confidence": 0.5, "evidence": None}}
)


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
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_valid_first_reply_is_not_retried():
    client = FakeClient(VALID_JSON)
    document = extract(b"fake image", "image/jpeg", client=client, model="m")
    assert document.total.value == 161700
    assert len(client.calls) == 1


def test_invalid_reply_is_retried_once_with_the_error():
    client = FakeClient(INVALID_JSON, VALID_JSON)
    document = extract(b"fake image", "image/jpeg", client=client, model="m")

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


# --- the API surface, no provider involved -------------------------------

client = TestClient(app)


def test_health_does_not_need_configuration():
    assert client.get("/health").json() == {"status": "ok"}


def test_non_image_upload_is_rejected():
    response = client.post("/extract", files={"file": ("notes.txt", b"hi", "text/plain")})
    assert response.status_code == 415
