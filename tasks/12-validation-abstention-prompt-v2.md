# Task 12: Validation checks, abstention rule, prompt v2

**Build order item:** 5, 6
**Status:** todo
**Depends on:** tasks 7, 8, 9 (the skill is committed before the prompt
changes), and 11 for the full-dataset runs

## Goal

Arithmetic checks run on every extraction and are reported in `meta`. A field
whose confidence is below a threshold chosen from data, or which takes part in
a failed check, is returned as `unreadable`. Prompt v2 adds the clarified
labelling rules.

Why: hallucinations are the worst failure in expense claims. Abstaining on a
field that does not add up turns a wrong value into a miss, which a person
checks.

## Files

- `app/validation.py` — new. Checks and the abstention rule. Pure functions.
- `app/extractor.py` — changed. Cache the raw model document; apply
  validation and abstention after the cache. Prompt v2.
- `evals/calibration.py` — new. Accuracy by confidence bucket from a saved
  run.
- `tests/test_validation.py`, `tests/test_calibration.py` — new.

## Steps

1. **Checks** in `app/validation.py`, each giving `pass`, `fail` or `skipped`
   with the fields involved:
   - `line_items_sum`: item amounts sum to `subtotal`, or to `total` when
     there is no subtotal. Skipped when any item has no amount.
   - `totals`: `subtotal - discount + service_charge + tax == total`, absent
     fields as 0. If that fails but the sum without `tax` equals `total`,
     pass as tax-inclusive. Skipped without both subtotal and total.
   - `line_arithmetic`: `quantity * unit_price` equals `amount` within
     `LINE_TOLERANCE = 0.01` (relative), for rounded fuel litres
     (3.96 × 12,610 = 49,935.6, printed 50,000).
2. **Raw cache.** The cache stores the model's document before checks and
   abstention. Changing the threshold or a check then needs no model calls:
   rerun with the cache on.
3. **`meta.checks`** lists every check result.
4. **Calibration** (no model calls): `uv run python evals/calibration.py
   <run>` prints, for `dev` documents only, accuracy per confidence bucket
   (below 0.5, 0.5-0.7, 0.7-0.8, 0.8-0.9, 0.9-0.95, 0.95 and up) over the
   eight value fields. Uses the raw values (step 5), so a run with abstention
   still calibrates.
5. **Abstention.** A `present` field with confidence below
   `ABSTAIN_THRESHOLD`, or listed in a failed check, becomes `unreadable` with
   `value` null. `meta.abstained` records field, reason, original value and
   confidence. `ABSTAIN_THRESHOLD` is a constant set from the calibration
   table, with the table's numbers in the comment.
6. **Prompt v2.** Add the 2026-10-07 rules from `docs/labeling-guide.md`
   (subtotal, payment method, document type). Bump `PROMPT_VERSION` to `"v2"`.
   Its own commit, after the skill is committed.
7. **Tests**, no network: each check passes, fails and skips; the fuel case
   passes; a tax-inclusive receipt passes; a low-confidence field abstains; a
   field in a failed check abstains; a cache hit re-applies the current rules;
   calibration buckets on a small run folder.
8. **Runs, by the user:** v1 and v2 on the full dataset, then `eval-compare`.
   Abstention effect alone: the same raw run rescored before and after the
   rule, via the cache.

## Done when

- [ ] `uv run pytest` passes and no test opens a network connection.
- [ ] `ABSTAIN_THRESHOLD` has the `dev` calibration table in its comment.
- [ ] `app/schema.py` is unchanged; everything new is in `meta`.
- [ ] Checked by the user: v2 compared with v1 through `eval-compare`, logged
      in `docs/skill-usage.md`, both runs committed.

## Out of scope

- Using `test` documents for the threshold or the prompt.
- Retrying the model when a check fails. One retry is only for invalid JSON.
- A per-field threshold. One threshold unless the table clearly needs more.
