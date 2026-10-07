# Task 13: Concurrent eval, cost and latency report

**Build order item:** 11, 12
**Status:** todo
**Depends on:** task 7

## Goal

The harness sends several documents at once and the scorecard reports cost per
document and in total, and latency median and 95th percentile.

Why: this covers "more than one document at a time" and "make cost and
latency visible". A run of 20 documents at about 90 seconds each takes 30
minutes in sequence.

## Files

- `evals/run_eval.py` — changed. Concurrent collection, retry with backoff,
  cost, percentiles.
- `docker-compose.yml` — changed. Pass the price and concurrency settings to
  `eval`.
- `.env.example` — `EVAL_CONCURRENCY`, `PRICE_INPUT_PER_M`,
  `PRICE_OUTPUT_PER_M`.
- `tests/test_run_eval.py` — new cases.

## Steps

1. **Concurrency.** `concurrent.futures.ThreadPoolExecutor` with
   `EVAL_CONCURRENCY` workers, default 3, sharing one `httpx.Client`. Files
   are written as each document finishes. The order in the scorecard stays
   sorted by file name.
2. **Retry with backoff.** A 429, 502 or 503 is retried up to
   `EVAL_RETRIES = 2` times, waiting 5 then 15 seconds. Each document file
   records its attempts. A timeout is not retried: the API already gave up.
3. **Cost.** Prices in US dollars per million tokens from the environment,
   default 0. Input is `prompt_tokens`; output is `total_tokens -
   prompt_tokens`, so reasoning tokens that are in neither reported number
   are charged as output. Cost per document and in total; the prices are
   recorded in the run block. Cached documents cost 0.
4. **Latency.** Median and 95th percentile of provider latency over
   non-cached documents (`statistics.quantiles(n=20)`; with fewer than 20
   documents say so next to the number). Also the run's wall-clock time.
5. **Compose.** `eval` gets `EVAL_CONCURRENCY`, `PRICE_INPUT_PER_M` and
   `PRICE_OUTPUT_PER_M` through `environment:` with `${VAR:-default}`
   interpolation. These are not secrets; `env_file` stays only on `api`.
6. **Tests**, no network, `httpx.MockTransport`: never more than N requests
   in flight (count in the handler with a lock); every document is collected
   when one fails; a 429 then 200 is recorded as success on attempt 2; cost
   arithmetic with a reasoning-token gap; the percentile on a known list.

## Done when

- [ ] `uv run pytest` passes and no test opens a network connection.
- [ ] `EVAL_CONCURRENCY=1` behaves like the current sequential harness.
- [ ] Checked by the user: one real run with concurrency 3 shows cost, median
      and p95 latency, and a shorter wall-clock time than a sequential run.

## Out of scope

- A batch endpoint on the API. Concurrency in the client meets the
  requirement.
- Async rewrite of the API. FastAPI already runs the sync endpoint in a
  thread pool.
- Rupiah conversion.
