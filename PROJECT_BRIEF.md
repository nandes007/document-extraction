# Project brief: document extraction take-home

Context for the coding agent. Read this before any task file.

## What we are building

A take-home test for an AI Engineer role. Two deliverables in one repo:

1. **Extraction API.** Takes a receipt or invoice image (later: multi-page PDF) and returns typed, validated JSON. Every field carries a status and a confidence. The system abstains instead of guessing.
2. **Evaluation harness.** A separate one-shot command that sends the sample documents to the running API over HTTP, compares the results with hand-labelled ground truth, and writes a scorecard.

Evaluation is weighted at least as heavily as extraction. No UI and no chat interface.

## Hard requirements from the test document

- Python. Provider must be configurable through an OpenAI-compatible endpoint (base URL, API key, model name from environment variables).
- `docker compose up` brings up the extraction API and leaves it serving.
- `docker compose run --rm eval` runs the harness against that API and writes the scorecard to a mounted output directory.
- Sample documents and ground truth are shipped in the repo so the eval runs out of the box.
- The scorecard and per-document results from a real run are committed.
- No secrets committed. Provide `.env.example`.
- Extraction logic and eval harness are our own code, not hidden inside a framework. The author must be able to explain every file and change it live.
- Output must not contain values that are not on the document.
- Handle more than one document at a time; make cost and latency visible; apply one optimization and report its measured impact.
- Ship one custom coding-agent extension that was actually used.
- Commit frequently with meaningful messages.

## Decisions already made

- **Scenario:** a client automating expense claims from receipts and invoices.
- **Document types:** `food`, `fuel`, `vehicle_service`, `retail`.
- **Architecture:** one vision-model call per document with structured output, then validation in plain code, with one retry on invalid output. No agent loop: the schema is fixed, so an agent would add cost and variance without adding accuracy. This choice must be justified in the README.
- **Amounts** are integers in rupiah. **Dates** are ISO `YYYY-MM-DD`.

## Schema

```python
from datetime import date
from typing import Generic, Literal, TypeVar
from pydantic import BaseModel

T = TypeVar("T")
Status = Literal["present", "not_present", "unreadable"]
PaymentMethod = Literal["cash", "debit", "credit", "card", "qris", "ewallet", "transfer", "other"]

class Extracted(BaseModel, Generic[T]):
    value: T | None          # None unless status is "present"
    status: Status
    confidence: float        # 0.0 to 1.0
    evidence: str | None     # the text as written on the document

class LineItem(BaseModel):
    description: str
    quantity: float | None   # litres for fuel, kg for weighed goods
    unit_price: int | None
    amount: int | None

class ExpenseDocument(BaseModel):
    document_type: Literal["food", "fuel", "vehicle_service", "retail"]
    merchant_name: Extracted[str]
    transaction_date: Extracted[date]
    line_items: list[LineItem]
    subtotal: Extracted[int]
    discount: Extracted[int]
    service_charge: Extracted[int]
    tax: Extracted[int]
    total: Extracted[int]
    payment_method: Extracted[PaymentMethod]
```

Status meanings:

- `present`: the value is on the document and readable.
- `not_present`: the field is not on the document. Returning a value here is a hallucination.
- `unreadable`: the field is on the document but cannot be read with confidence. This is abstention.

## Ground truth format

One JSON file per document in `data/ground_truth/`, with the same base name as the image in `data/documents/`. Same shape as the schema, without `confidence` and `evidence`, plus:

- `file`: image file name.
- `split`: `dev` (used while tuning prompts) or `test` (held back for the reported score).
- `tags`: document properties used to slice results, for example `handwritten`, `printed`, `stamp_overlap`, `tax_inclusive`, `ambiguous_handwriting`.
- `merchant_name.accept`: optional list of other spellings the scorer counts as correct.

Example:

```json
{
  "file": "food_receipts01.jpeg",
  "split": "dev",
  "tags": ["printed", "faint_print", "service_charge", "tax_added"],
  "document_type": "food",
  "merchant_name": {"value": "Rumah Kecil Talenta", "status": "present", "accept": ["Rumah Kecil Talenta M Bloc", "Talenta"]},
  "transaction_date": {"value": "2026-10-03", "status": "present"},
  "line_items": [
    {"description": "MISOA AYAM JAMUR", "quantity": 1, "unit_price": 48000, "amount": 48000}
  ],
  "subtotal": {"value": 140000, "status": "present"},
  "discount": {"value": null, "status": "not_present"},
  "service_charge": {"value": 7000, "status": "present"},
  "tax": {"value": 14700, "status": "present"},
  "total": {"value": 161700, "status": "present"},
  "payment_method": {"value": "qris", "status": "present"}
}
```

Six documents are labelled so far: three food, two fuel, one handwritten retail note. Ground truth is written and verified by a human. The agent must never edit files in `data/ground_truth/` to make a score improve.

## Labelling rules

1. Label from the image, never from a model's output alone.
2. Merchant name is the brand without the branch.
3. A printed zero (`Diskon: 0`) is `present` with value 0.
4. The full and current rules are in `docs/labeling-guide.md`. Where they differ, that file wins.
5. Repeated rows stay as separate line items. Modifiers such as "LESS SWEET" are not items.
6. When tax is included in the price, record the stated tax; `total` is the amount paid.
7. Expand shorthand only when the document makes it unambiguous.

## Things the code must handle

- Fuel receipts round the litres, so `quantity * unit_price` can differ from `amount` (3.96 x 12,610 = 49,935.6, printed 50,000). Arithmetic checks need a tolerance.
- Indonesian number formats: both `161,700` and `39.695` mean whole rupiah.
- Dates appear as `03-10-2026`, `15-Sep-25`, `2026-03-06` and handwritten `29.11.20`. Day comes first unless the year is clearly first.
- Columns can run together (`BPULTIMATE3.07012.930`).
- Handwritten notes often have no item amounts, no date, or no merchant.

## Repo layout

```
app/
  main.py          # FastAPI: POST /extract
  schema.py        # the Pydantic models above
  extractor.py     # the vision-model call and retry
evals/
  run_eval.py      # call the API, compare, write the scorecard
data/
  documents/
  ground_truth/
outputs/           # scorecards, committed
docs/labeling-guide.md
tasks/             # one task file per step
docker-compose.yml
Dockerfile
.env.example
README.md
```

## Build order

**Step 1, thin slice (do this first):**

1. `app/schema.py`.
2. `POST /extract`: accept a file, send the image to the model, validate with Pydantic, return JSON.
3. `evals/run_eval.py`, minimal: send every document to the API, compare `total` only, write `outputs/scorecard.json`.
4. Docker Compose with an `api` service and a one-shot `eval` service.

**Step 2, quality and evaluation:**

5. Validation layer: number and date parsing, arithmetic checks (line items sum to subtotal; subtotal minus discount plus service charge and tax equals total, with tax-inclusive receipts handled).
6. Confidence: combine the model's stated confidence with the arithmetic checks. Choose the abstain threshold from eval data.
7. Scoring for every field, with each result classified as correct, wrong value, missed (system abstained or said `not_present` when a value exists), or hallucinated (system gave a value where ground truth is `not_present` or `unreadable`).
8. Line items: match rows, then report row-level precision and recall.
9. Results sliced by field, document type and tag.
10. `compare` command: diff two scorecards, list documents that flipped from correct to wrong, exit non-zero on regression. Run the same version twice to measure run-to-run noise.

**Step 3, production:**

11. Batch endpoint with limited concurrency and retry with backoff.
12. Tokens, cost and latency logged per document; report median and 95th percentile.
13. Response cache keyed by file hash and prompt version (free tiers are rate limited).
14. One optimization measured before and after, for example image downscaling: cost saved and accuracy change.
15. README.

## Working rules for the agent

- One task file per step. Small commits with clear messages.
- Keep the code small and readable. No orchestration framework for the extraction logic or the harness.
- Do not add a UI, a database, or an agent loop.
- Never write a real API key into any file. Read configuration from environment variables.
- Do not change the schema or the labelling rules without asking.

## Stack

- Python 3.12, managed with `uv` (`pyproject.toml` + `uv.lock`). Run things with `uv run`.
- FastAPI + uvicorn, `python-multipart` for uploads.
- Pydantic v2 for schema and validation.
- `openai` SDK as the client for any OpenAI-compatible endpoint.
- `httpx` for the eval harness calling the API.
- Pillow for image handling, `pypdfium2` for PDF pages, `rapidfuzz` for name matching.
- `pytest` for tests.
- No LangChain or other orchestration framework, no database, no Redis.
  The response cache is JSON files on disk.
- The Dockerfile installs with `uv sync --frozen`.