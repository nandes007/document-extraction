# Task 2: POST /extract

**Build order item:** 2
**Status:** todo

## Goal

A running API with one endpoint: accept an image upload, make one vision-model
call with structured output, validate against `ExpenseDocument`, return it as
JSON. One retry when the model returns something the schema rejects.

## Files

- `app/extractor.py` — new. Prompt, the model call, the retry.
- `app/main.py` — new. FastAPI app, `POST /extract`, `GET /health`.
- `tests/test_extractor.py` — new. Retry path with a stubbed client.

## Steps

1. Read `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` from the environment with
   `os.environ`. No config class, no default for the key. Construct the
   `openai.OpenAI` client with `base_url` and `api_key` so any
   OpenAI-compatible endpoint works.
2. In `extractor.py`: base64 the image bytes into an `image_url` content part,
   send one chat completion with a prompt that states the field meanings and
   the three statuses. Request JSON matching
   `ExpenseDocument.model_json_schema()`.
3. Validate the reply with `ExpenseDocument.model_validate_json`. On
   `ValidationError`, retry once with the error text appended to the prompt.
   Second failure raises; the endpoint turns it into HTTP 422 with the
   validation error.
4. In `main.py`: `POST /extract` takes `UploadFile`, rejects anything whose
   content type is not an image, calls the extractor, returns the model dump.
   `GET /health` returns `{"status": "ok"}` without touching the provider.
5. Prompt rules to state explicitly, because the eval scores them:
   - Never output a value that is not written on the document.
   - `not_present` when the field is absent, `unreadable` when present but
     illegible. `value` is null for both.
   - `evidence` is the text as written, copied, not normalised.
   - Amounts are integer rupiah, dates are `YYYY-MM-DD`.
6. `tests/test_extractor.py`: inject a fake client that returns invalid JSON
   first and valid JSON second. Assert one retry happens and the result
   validates. No network in tests.

## Done when

- [ ] `uv run uvicorn app.main:app` serves and `GET /health` returns 200.
- [ ] `curl -F file=@data/documents/food_receipts01.jpeg localhost:8000/extract`
      returns a body that `ExpenseDocument` validates.
- [ ] `uv run pytest` passes without network access.
- [ ] A missing `LLM_API_KEY` produces a clear error, not a traceback.
- [ ] No API key appears in any committed file.

## Out of scope

- Batch, concurrency, caching, cost and latency logging — tasks 11-13.
- Image downscaling — task 14, where its impact gets measured.
- Arithmetic validation and confidence calibration — tasks 5-6. Pass the
  model's stated confidence through unchanged for now.
