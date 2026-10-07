"""One vision-model call per document, validated, with one retry.

No agent loop: the schema is fixed, so the only thing a loop could add is cost
and variance. When the model returns something the schema rejects, we hand the
validation error back once and take the second answer or fail.
"""

import base64
import hashlib
import json
import os
import time
from functools import lru_cache

from openai import OpenAI
from pydantic import ValidationError

from app import cache
from app.pages import to_images
from app.schema import ExpenseDocument

PROMPT = """You read Indonesian receipts and invoices for an expense-claim system.

Return one JSON object describing the document in the image. Rules:

- Never output a value that is not written on the document. Do not calculate,
  infer or complete anything. If the document does not say it, it is not there.
- Every field carries a status:
  - "present": the value is on the document and you can read it.
  - "not_present": the field is absent from the document.
  - "unreadable": the field is on the document but you cannot read it with
    confidence.
  "value" must be null for "not_present" and "unreadable". Abstaining is
  correct behaviour and is scored as such; guessing is not.
- "evidence" is the text as written on the document, copied character for
  character, not normalised. Null when the status is not "present".
- "confidence" is 0.0 to 1.0 for your own reading of that field.
- Amounts are integers in rupiah, no separators and no decimals. Indonesian
  receipts write whole rupiah as both "161,700" and "39.695"; both are
  integers, 161700 and 39695.
- Dates are "YYYY-MM-DD". Day comes before month unless the year is clearly
  first, so "03-10-2026" is 2026-10-03 and "15-Sep-25" is 2025-09-15.
- A printed zero is a value: "Diskon: 0" is status "present" with value 0.
- Two total-like lines: the first is subtotal, the last is total. One line
  only: that is total, and subtotal is "not_present".
- line_items holds the rows as printed. Repeated rows stay separate. Modifiers
  such as "LESS SWEET" are not items. Use null for a quantity, unit price or
  amount the row does not show. For fuel, quantity is litres.
- document_type is one of: food, fuel, vehicle_service, retail.
"""

# Bump whenever PROMPT or RESPONSE_FORMAT changes. The cache key also hashes
# their text, so forgetting is safe for the cache but not for reading scorecards.
PROMPT_VERSION = "v1"

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "expense_document",
        "schema": ExpenseDocument.model_json_schema(),
    },
}


# The SDK defaults are a 600 second read timeout and 2 retries. The eval harness
# waits 180 seconds, so the API must give up first and return a clear error.
TIMEOUT = 150.0
MAX_RETRIES = 1


class ProviderError(Exception):
    """The provider replied, but not with a completion."""


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set. Copy .env.example to .env and fill it in."
        )
    return value


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    return OpenAI(
        base_url=_require("LLM_BASE_URL"),
        api_key=_require("LLM_API_KEY"),
        timeout=TIMEOUT,
        max_retries=MAX_RETRIES,
    )


def _fingerprint() -> str:
    text = PROMPT + json.dumps(RESPONSE_FORMAT, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()


def extract(
    image_bytes: bytes,
    content_type: str = "image/jpeg",
    *,
    client: OpenAI | None = None,
    model: str | None = None,
) -> tuple[ExpenseDocument, dict]:
    """Read one document (an image or a PDF). Returns it with metadata; raises
    ValidationError if both attempts fail, NotAPdf or TooManyPages for bad PDFs."""
    # Rendered before anything else, so a bad PDF is rejected even unconfigured.
    pages = to_images(image_bytes, content_type)
    model = model or _require("LLM_MODEL")
    # Keyed on the uploaded bytes, not the rendered pages.
    key = cache.make_key(image_bytes, model, PROMPT_VERSION, _fingerprint())
    hit = cache.read(key)
    if hit:
        # Stored latency and usage describe the original call.
        return ExpenseDocument.model_validate(hit["document"]), hit["meta"] | {
            "cached": True
        }

    client = client or _client()
    # All pages in one call, so a total on page 2 is read with the items on page 1.
    parts: list[dict] = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:{ctype};base64,{base64.b64encode(data).decode()}"},
        }
        for data, ctype in pages
    ]
    if len(pages) > 1:
        parts.insert(
            0, {"type": "text", "text": f"The document has {len(pages)} pages, in order."}
        )

    messages = [
        {"role": "system", "content": PROMPT},
        {"role": "user", "content": parts},
    ]

    error: ValidationError | None = None
    latency = 0.0
    usage: dict[str, int] | None = None
    for attempt in (1, 2):
        started = time.perf_counter()
        reply = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format=RESPONSE_FORMAT,
            temperature=0,
        )
        latency += time.perf_counter() - started
        if not reply.choices:
            # Some providers answer 200 with an error body (rate limit, bad
            # model name, no vision or json_schema support). The SDK doesn't raise.
            raise ProviderError(f"provider returned no choices: {reply.model_extra}")
        if reply.usage:
            # As reported. total_tokens is not recomputed: some models count
            # reasoning tokens that are in neither of the other two.
            usage = {
                name: (usage or {}).get(name, 0) + (getattr(reply.usage, name) or 0)
                for name in ("prompt_tokens", "completion_tokens", "total_tokens")
            }
        content = reply.choices[0].message.content or ""
        try:
            document = ExpenseDocument.model_validate_json(content)
        except ValidationError as exc:
            error = exc
            messages += [
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        f"That JSON failed validation:\n{exc}\n"
                        "Return the corrected JSON object only."
                    ),
                },
            ]
            continue
        meta = {
            "model": model,
            "prompt_version": PROMPT_VERSION,
            "attempts": attempt,
            "latency_seconds": round(latency, 2),
            "usage": usage,
            "cached": False,
        }
        cache.write(key, {"document": document.model_dump(mode="json"), "meta": meta})
        return document, meta
    raise error
