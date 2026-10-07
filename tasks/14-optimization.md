# Task 14: One optimization, measured before and after

**Build order item:** 14
**Status:** todo
**Owner:** user runs and decides; the agent adds the setting.
**Depends on:** tasks 8, 12, 13

## Goal

One change that cuts cost or latency, with tokens, latency, cost and accuracy
reported before and after from `compare`.

Why this one: completion tokens are 3,200 to 9,200 per document for about 300
tokens of JSON, while prompt tokens, image included, are about 1,750 (run
`20261007-051452`). The cost is in the model's reasoning, not the image, so
downscaling would save little.

## Files

- `app/extractor.py` — changed. Optional `LLM_REASONING_EFFORT` sent to the
  provider; included in the cache key and in `meta`.
- `.env.example` — `LLM_REASONING_EFFORT=` (empty: provider default).
- `tests/test_extractor.py`, `tests/test_cache.py` — new cases.
- `README.md` — the before and after table, in task 15.

## Steps

1. **Setting.** When `LLM_REASONING_EFFORT` is set (`low`, `medium`,
   `high`), send it as the provider's reasoning option through `extra_body`.
   When empty, send nothing, so other providers are unaffected. Check the
   exact parameter name in the provider's documentation and cite it in a
   comment.
2. **Cache key** includes the setting. Otherwise a low-effort run would be
   served the high-effort answers.
3. **`meta.reasoning_effort`** records what was sent.
4. **Tests**, no network: the fake client receives the option when set and
   nothing when empty; a changed setting misses the cache.
5. **Measure** (user): the final v2 version on `dev`, cache off, with and
   without `low`. Check the completion tokens actually fall; if the model
   ignores the option, try the second candidate, a faster model, instead.
6. **Report** (user + agent): `compare` output, and a table of total tokens,
   cost, median and p95 latency, accuracy and hallucinations before and
   after. State the noise floor from task 8 next to the accuracy change.
7. **Decide** (user): keep it only if no field regresses beyond the noise
   floor. The chosen setting is what the final `test` run uses.

## Done when

- [ ] `uv run pytest` passes and no test opens a network connection.
- [ ] Checked by the user: before and after runs committed, compared, and the
      table written for the README.

## Out of scope

- A second optimization. Only if time remains.
- Image downscaling. The token numbers say it is not where the cost is.
