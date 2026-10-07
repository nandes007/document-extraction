# Task 6: Eval run records and failure handling

**Build order item:** 3 (hardening) and 12 (tokens and latency, eval side)
**Status:** todo
**Depends on:** task 5

## Goal

Each eval run gets its own folder holding the full API response for every
document and the scorecard built from them. A scorecard can be rebuilt from a
saved run without calling the API. One slow or failed document no longer ends
the run.

Why now: the harness currently keeps only `total`, overwrites the previous
scorecard, and exits on the first timeout, discarding every result so far.
Scoring more fields (task 7) and comparing versions (task 10) both need saved
runs.

## Files

- `evals/run_eval.py` — changed. Split into collecting and scoring.
- `tests/test_run_eval.py` — new. `tests/test_scoring.py` stays as it is.
- `outputs/runs/<run_id>/` — generated: `scorecard.json` and
  `documents/<stem>.json`. Committed.
- `outputs/scorecard.json` — moved to
  `outputs/runs/baseline-total-only/scorecard.json`.
- `tasks/04-docker-compose.md` — wording only: it names
  `outputs/scorecard.json`; point it at `outputs/runs/`.

## Steps

1. **Preflight.** Call `GET /health` before the first document. If the API is
   unreachable, print one "cannot reach API at <url>" message and exit without
   creating a run folder.
2. **Run folder.** `outputs/runs/<run_id>/`, where `run_id` is `RUN_ID` from
   the environment or the UTC time as `YYYYMMDD-HHMMSS`. Refuse to write into
   a folder that already exists.
3. **Collect.** For every document, save
   `documents/<stem>.json` with: file name, HTTP status, wall-clock seconds,
   and the response body (the full envelope on 200, the error text otherwise).
4. **One document failing does not stop the run.** A timeout or transport
   error on a document is saved with the exception name in place of a
   response, and the run continues. The document is scored as `error`.
5. **Score from files.** Scoring reads only the saved `documents/*.json` and
   `data/ground_truth/`. It does not call the API. Still `total` only; the
   `classify` function is unchanged.
6. **Rescore.** `uv run python evals/run_eval.py --rescore outputs/runs/<id>`
   rebuilds `scorecard.json` for an existing run from its saved documents.
7. **Run block.** Record `run_id`, `api_url`, start and finish time, and the
   git commit (short hash, `"unknown"` when git is not available). Take
   `model` and `prompt_version` from the API metadata in the saved responses,
   not from the environment. If the documents disagree, record `"mixed"`.
   Remove `load_dotenv` and the `LLM_MODEL` lookup from the harness.
8. **Per document** in the scorecard, add: wall-clock seconds, provider
   latency, attempts, token usage and `cached`.
9. **Summary**, add: total tokens, number of cached documents, and median and
   maximum provider latency over the documents that were not cached.
10. **Exit code.** Unchanged: non-zero when any document is an `error`.
11. **Tests**, no network:
    - scoring a small run folder built in a temp directory gives the expected
      counts
    - a timeout on one document (`httpx.MockTransport`) is recorded as
      `error` and the remaining documents are still collected
    - `--rescore` produces the same summary as the original scoring and makes
      no HTTP request
    - an unreachable API creates no run folder

## Done when

- [ ] `uv run pytest` passes and no test opens a network connection.
- [ ] With the API stopped, the harness prints one clear message and leaves
      nothing in `outputs/runs/`.
- [ ] `--rescore` on a saved run works with the API stopped.
- [ ] `data/ground_truth/` is unchanged.
- [ ] Checked by the user, not the agent: a real run creates
      `outputs/runs/<run_id>/` with six document files and a scorecard whose
      `model` and `prompt_version` match what the API used. That run is
      committed.

## Out of scope

- Calling the real provider. The agent verifies with fakes only; real runs are
  started by the user.
- Scoring fields other than `total`, name matching, line items — tasks 7 and 8.
- Slices by tag and document type — task 9.
- Comparing two runs and regression gating — task 10.
- Sending documents concurrently — task 11.