"""One vision-model call per document, validated, with one retry.

No agent loop: the schema is fixed, so the only thing a loop could add is cost
and variance. When the model returns something the schema rejects, we hand the
validation error back once and take the second answer or fail.
"""

import base64
import os
from functools import lru_cache

from openai import OpenAI
from pydantic import ValidationError

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

RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "expense_document",
        "schema": ExpenseDocument.model_json_schema(),
    },
}


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
        base_url=_require("LLM_BASE_URL"), api_key=_require("LLM_API_KEY")
    )


def extract(
    image_bytes: bytes,
    content_type: str = "image/jpeg",
    *,
    client: OpenAI | None = None,
    model: str | None = None,
) -> ExpenseDocument:
    """Read one document. Raises ValidationError if both attempts fail."""
    client = client or _client()
    model = model or _require("LLM_MODEL")
    image_url = f"data:{content_type};base64,{base64.b64encode(image_bytes).decode()}"

    messages = [
        {"role": "system", "content": PROMPT},
        {
            "role": "user",
            "content": [{"type": "image_url", "image_url": {"url": image_url}}],
        },
    ]

    error: ValidationError | None = None
    for _ in range(2):
        reply = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format=RESPONSE_FORMAT,
            temperature=0,
        )
        if not reply.choices:
            # Some providers answer 200 with an error body (rate limit, bad
            # model name, no vision or json_schema support). The SDK doesn't raise.
            raise ProviderError(f"provider returned no choices: {reply.model_extra}")
        content = reply.choices[0].message.content or ""
        try:
            return ExpenseDocument.model_validate_json(content)
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
    raise error
