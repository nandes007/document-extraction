# Task 8: Compare two runs, regression gate

**Build order item:** 10
**Status:** todo
**Depends on:** task 7

## Goal

`uv run python evals/compare.py <baseline_run> <candidate_run>` shows what
changed between two runs and exits non-zero when the candidate is worse.

Why now: prompt v2, abstention and the optimization are each judged by
comparing a run against the one before it. Without a gate, a regression on
one field hides behind a gain on another.

## Files

- `evals/compare.py` — new. Load two run folders, score both, diff, print,
  exit code.
- `tests/test_compare.py` — new.

## Steps

1. **Score both runs fresh.** Call `run_eval.score()` on each folder's saved
   documents, in memory, so both are judged against the current labels. Do not
   write either scorecard.
2. **Same documents only.** Compare documents present in both runs. List any
   that are only in one, and do not count them.
3. **Per field:** accuracy before, after and the change, for the eight value
   fields and `document_type`; hallucinations before and after; line-item
   precision and recall before and after.
4. **Flips.** Every (document, field) that went from correct to not correct
   (regressions) and from not correct to correct (fixes), with the old and
   new class and value.
5. **Cost and speed:** total tokens, median and maximum provider latency over
   non-cached documents, before and after. Say how many documents were cached
   in each run; cached latency is not a measurement.
6. **Header:** both run ids, models and prompt versions. Warn when they are
   identical, because then the comparison measures noise.
7. **Exit code:** 1 when any field's accuracy drops or the hallucination count
   rises, 0 otherwise, 2 for bad arguments or a missing run folder.
8. **Output** is plain text to stdout, readable in a terminal and pasteable
   into the README. `--json` prints the same content as JSON for the skill in
   task 9.
9. **Tests**, no network, run folders built in a temp directory: identical
   runs exit 0 with no flips; one field flipping to wrong exits 1 and is
   listed; a fix alone exits 0; one extra hallucination exits 1; a document
   missing from one run is listed and ignored.

## Done when

- [ ] `uv run pytest` passes and no test opens a network connection.
- [ ] `uv run python evals/compare.py outputs/runs/20261007-051452
      outputs/runs/20261007-083154` runs with the API stopped and prints the
      per-field table and flips. These are two runs of the same version, so
      the result is the first noise measurement; note it.
- [ ] Checked by the user: two fresh runs of the same version with
      `LLM_CACHE=0` on the API, then compared. The number of flips is the
      noise floor, recorded for the README.

## Out of scope

- A tolerance on the gate. With six to twenty documents one flip is a large
  percentage; the noise run shows how often that happens. Decide after.
- Statistical tests. Too few documents for them to mean anything.
- Writing a comparison file to `outputs/`. Paste the output where it is needed.
