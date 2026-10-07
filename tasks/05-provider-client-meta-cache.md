# Task 5: Provider client settings, response metadata, response cache

**Build order item:** 12 (tokens and latency, API side) and 13 (cache), pulled forward
**Status:** todo

## Goal

Every `/extract` response says which model and prompt produced it, how long the
provider took and how many tokens it used. Repeating a request for the same
image, model and prompt is answered from disk without calling the provider.
The provider client has explicit timeout and retry settings instead of SDK
defaults.

Why now: one eval run costs about 9 minutes and six requests of a small daily
quota. Without a cache, every rerun pays that again.

## Files

- `app/extractor.py` — changed. Client settings, `PROMPT_VERSION`, returns
  document plus metadata, uses the cache.
- `app/cache.py` — new. Disk cache: build key, read, write. Plain JSON files.
- `app/main.py` — changed. Response envelope and error mapping.
- `evals/run_eval.py` — changed, one line: read the document from the new
  envelope so the harness keeps working. Nothing else here; see task 6.
- `tests/test_extractor.py`, `tests/test_cache.py` — changed / new.
- `.gitignore` — add `.cache/`.
- `.env.example` — add `LLM_CACHE=1`.

## Steps

1. **Client settings.** Create the client with `timeout=150.0` and
   `max_retries=1`, as named constants with a comment: the SDK defaults are a
   600 second read timeout and 2 retries, and the eval harness waits 180
   seconds, so the API must give up first and return a clear error.
2. **Prompt version.** Add `PROMPT_VERSION = "v1"` next to `PROMPT`, with a
   comment that it is bumped whenever `PROMPT` or `RESPONSE_FORMAT` changes.
3. **Metadata.** `extract()` returns the document together with:
   - `model` and `prompt_version`
   - `attempts`: 1 or 2
   - `latency_seconds`: time spent in provider calls, summed over attempts
   - `usage`: `prompt_tokens`, `completion_tokens`, `total_tokens`, summed over
     attempts, taken from the provider reply as reported. `null` when the
     provider reports none. Do not recompute `total_tokens`: some models count
     reasoning tokens that are in neither of the other two numbers.
   - `cached`: `false` for a fresh call
4. **Cache.** In `app/cache.py`:
   - Key: SHA-256 over the image bytes, the model name, `PROMPT_VERSION` and a
     hash of `PROMPT` plus the JSON schema. Hashing the prompt text means an
     edited prompt misses the cache even if the version was not bumped.
   - Location: `CACHE_DIR` from the environment, default `.cache/responses`,
     one file `<key>.json` holding the document and its metadata.
   - On a hit, return the stored document and stored metadata with
     `cached: true`. Stored latency and usage describe the original call and
     stay as they were.
   - Store only results that passed validation. Never cache an error.
   - `LLM_CACHE=0` turns off both reading and writing. This is needed later to
     run the same version twice and measure run-to-run noise.
5. **Response envelope.** `/extract` returns
   `{"document": {...}, "meta": {...}}`. `ExpenseDocument` itself is unchanged.
6. **Error mapping** in `app/main.py`, most specific exception first:
   provider rate limit → 429, provider timeout → 504, any other provider
   error or `ProviderError` → 502, validation failure → 422 (unchanged).
7. **Tests**, all with the existing `FakeClient`, no network:
   - usage and attempts are summed across a retry
   - a second call for the same image does not reach the client and returns
     `cached: true`
   - a different model or a changed prompt misses the cache
   - `LLM_CACHE=0` bypasses the cache
   - a failed extraction leaves nothing in the cache
   - rate limit, timeout and other provider errors map to 429, 504 and 502
   - tests use a temporary `CACHE_DIR`, never the real one

## Done when

- [ ] `uv run pytest` passes and no test opens a network connection.
- [ ] `git status` shows nothing under `.cache/`.
- [ ] `data/ground_truth/` and `app/schema.py` are unchanged.
- [ ] Checked by the user, not the agent: with the API running, sending the
      same document twice gives `cached: false` with token counts the first
      time, and `cached: true` in under a second the second time.

## Out of scope

- Calling the real provider. The agent verifies with fakes only; real runs are
  started by the user.
- Everything else in the eval harness: run folders, saved responses, timeout
  handling — task 6.
- Cost in rupiah or dollars. That needs a price table — task 12.
- Telling "daily quota exhausted" apart from a short rate limit. Both are 429.
- Batch endpoint and concurrency — task 11. Image downscaling — task 14.