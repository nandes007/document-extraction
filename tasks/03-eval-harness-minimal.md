# Task 3: Minimal eval harness

**Build order item:** 3
**Status:** todo

## Goal

One command that sends every document in `data/documents/` to the running API
over HTTP, compares `total` against ground truth, and writes
`outputs/scorecard.json`. Proves the loop end to end before the real scorer
goes in.

## Files

- `evals/run_eval.py` — new. The whole harness, one file, `httpx` for the calls.
- `tests/test_scoring.py` — new. The four-way classifier.
- `outputs/scorecard.json` — generated, committed.

## Steps

1. Take the API base URL from `API_URL` (default `http://localhost:8000`);
   document and ground-truth directories are constants.
2. For each file in `data/documents/`, load the matching
   `data/ground_truth/<stem>.json`. A document with no ground truth is an
   error, not a skip — the eval must not silently shrink.
3. `POST` each image to `/extract` with `httpx.Client` sequentially. Record
   wall-clock seconds per document. Generous timeout — vision calls are slow.
4. Compare `total` only, as a small pure function so it is testable:
   `correct` when status and value both match; `wrong_value`; `missed` (we
   abstained or said `not_present` where a value exists); `hallucinated` (we
   gave a value where ground truth is `not_present` or `unreadable`).
5. Write `outputs/scorecard.json`: a `run` block (UTC timestamp, model name,
   document count), a `summary` block (counts per class, accuracy overall and
   split by `dev` / `test`), and a `documents` list with expected total,
   extracted total, class and latency per file.
6. Print a one-line summary. Exit non-zero if any document errored, so
   `docker compose run eval` fails loudly.
7. `tests/test_scoring.py`: one case per class, fed to the classifier directly.
   No API, no network.

## Done when

- [ ] `uv run python evals/run_eval.py` against a running API writes
      `outputs/scorecard.json` covering all 6 documents.
- [ ] The scorecard is readable without the code next to it: expected, got,
      verdict per document.
- [ ] A stopped API gives one clear "cannot reach API at <url>" message.
- [ ] `uv run pytest` passes.
- [ ] `data/ground_truth/` is unchanged.

## Out of scope

- All fields, line-item matching, tag and type slices — tasks 7-9.
- `rapidfuzz` merchant-name matching — task 7, where `accept` lists are used.
- `compare` and regression gating — task 10.
- Token and cost accounting — task 12. Latency only for now.
