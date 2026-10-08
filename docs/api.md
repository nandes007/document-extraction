# API reference

Base URL: `http://localhost:8000` (from `docker compose up -d`). FastAPI also
serves interactive docs at `/docs` and the OpenAPI schema at `/openapi.json`.

## `GET /health`

Liveness only. Never calls the provider.

```
curl http://localhost:8000/health
```

```json
{"status": "ok"}
```

## `POST /extract`

Reads one receipt or invoice and returns the extracted document plus metadata.

### Request

`multipart/form-data` with one field:

| Field | Type | Notes |
|---|---|---|
| `file` | file | An image (`image/*`, e.g. JPEG or PNG) or a PDF (`application/pdf`, at most 5 pages). |

The content type of the upload part decides how it is read. A PDF is rendered
page by page and all pages go to the model in one call; any text layer is
ignored.

```
curl -F "file=@data/documents/fuel_receipts01.jpg;type=image/jpeg" \
  http://localhost:8000/extract
```

### Response `200`

```json
{
  "document": { ... },
  "meta": { ... }
}
```

#### `document`

An `ExpenseDocument` (see `app/schema.py`):

| Field | Type |
|---|---|
| `document_type` | `"food"`, `"fuel"`, `"vehicle_service"` or `"retail"` |
| `merchant_name` | `Extracted[str]` |
| `transaction_date` | `Extracted[date]`, ISO `YYYY-MM-DD` |
| `line_items` | list of `{description, quantity, unit_price, amount}` |
| `subtotal`, `discount`, `service_charge`, `tax`, `total` | `Extracted[int]`, whole rupiah |
| `payment_method` | `Extracted` of `cash`, `debit`, `credit`, `card`, `qris`, `ewallet`, `transfer`, `other` |

Line item fields: `description` (string), `quantity` (float or null; litres
for fuel, kg for weighed goods), `unit_price` and `amount` (integer rupiah or
null).

Every `Extracted` field has this shape:

| Key | Type | Meaning |
|---|---|---|
| `value` | value or `null` | `null` unless `status` is `present`. |
| `status` | `present`, `not_present`, `unreadable` | `not_present`: not on the document. `unreadable`: on the document but not read with confidence (the system abstained). |
| `confidence` | float 0.0 to 1.0 | The model's stated confidence. |
| `evidence` | string or `null` | The text as written on the document. |

A `present` field is turned into `unreadable` (value and evidence cleared)
when its confidence is below 0.9 or when an arithmetic check that involves it
fails. `meta.abstained` records the original value.

#### `meta`

| Key | Type | Meaning |
|---|---|---|
| `model` | string | Model that produced the document. |
| `prompt_version` | string | Prompt version, part of the cache key. |
| `reasoning_effort` | string or `null` | Value of `LLM_REASONING_EFFORT` sent to the provider. |
| `attempts` | int | `1`, or `2` if the first output failed validation and was retried. |
| `latency_seconds` | float | Provider time across attempts. |
| `usage` | object or `null` | `prompt_tokens`, `completion_tokens`, `total_tokens`, `reasoning_tokens` (null if the provider does not report it), summed across attempts. |
| `cached` | bool | `true` if served from the on-disk cache. Latency and usage then describe the original call. |
| `checks` | list | Arithmetic checks: `{name, result, fields, detail}`, `result` is `pass`, `fail` or `skipped`. Names: `line_items_sum`, `totals`, `line_arithmetic`. |
| `abstained` | list | Fields turned `unreadable`: `{field, reason, value, confidence}`. `reason` holds `low_confidence` and/or `check:<name>`. |

Example (trimmed; the `meta` numbers are illustrative):

```json
{
  "document": {
    "document_type": "fuel",
    "merchant_name": {"value": "Vivo Cipondoh", "status": "present", "confidence": 0.99, "evidence": "VIVO CIPONDOKH"},
    "transaction_date": {"value": "2025-09-15", "status": "present", "confidence": 0.99, "evidence": "Date: 15-Sep-25/06:40 AM"},
    "line_items": [{"description": "Revvo 92", "quantity": 3.96, "unit_price": 12610, "amount": 50000}],
    "subtotal": {"value": null, "status": "not_present", "confidence": 1.0, "evidence": null},
    "total": {"value": 50000, "status": "present", "confidence": 0.99, "evidence": "TOTAL: Rp. 50,000"},
    "payment_method": {"value": "cash", "status": "present", "confidence": 0.99, "evidence": "Mode Pembayaran: Cash"}
  },
  "meta": {
    "model": "google/gemini-2.5-flash",
    "prompt_version": "v2",
    "reasoning_effort": null,
    "attempts": 1,
    "latency_seconds": 4.1,
    "usage": {"prompt_tokens": 1933, "completion_tokens": 410, "total_tokens": 2343, "reasoning_tokens": null},
    "cached": false,
    "checks": [
      {"name": "line_items_sum", "result": "pass", "fields": ["total"], "detail": "items sum to 50000, total is 50000"},
      {"name": "totals", "result": "skipped", "fields": [], "detail": "needs both subtotal and total"},
      {"name": "line_arithmetic", "result": "pass", "fields": [], "detail": "1 row(s) within 1%"}
    ],
    "abstained": []
  }
}
```

### Errors

All errors return `{"detail": "<message>"}`.

| Status | When |
|---|---|
| `413` | PDF has more than 5 pages. |
| `415` | Upload is not an image or PDF, or claims to be a PDF but cannot be opened. |
| `422` | No `file` field, or the model output failed schema validation on both attempts. |
| `429` | Provider rate limit. |
| `500` | Missing configuration (e.g. `LLM_MODEL` not set). |
| `502` | Provider error (down, bad key, empty reply). |
| `504` | Provider timed out. |
