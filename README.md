# Document extraction

## Run

1. Copy the example settings and fill in your provider (any OpenAI-compatible
   endpoint with a vision model):

   ```
   cp .env.example .env
   ```

   Set `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL`. `.env` is never committed
   and never copied into the image.

2. Start the API. It stays up and serves on `http://localhost:8000`:

   ```
   docker compose up -d
   ```

3. Run the evaluation against it:

   ```
   docker compose run --rm eval
   ```

   Each run writes `outputs/runs/<run_id>/` on the host: one file per document
   with the full API response, and `scorecard.json`. Responses are cached in
   `.cache/`, so a repeat run on the same documents and prompt makes no
   provider calls.
