---
name: eval-compare
description: Compare a baseline and a candidate eval run folder under outputs/runs/ and report regressions and fixes by field and failure kind. Use after any change to the prompt, model, validation or scoring, when the user asks whether a run is better or worse than another, or to measure run-to-run noise. Stops on a regression.
argument-hint: <baseline_run> <candidate_run>
---

# eval-compare

Judge a candidate eval run against a baseline. Read-only with respect to the
model: everything here works from saved run folders.

## Hard rules

- Never call the LLM provider, start the API, or start an eval run. The user
  starts real runs.
- Never edit anything in `data/ground_truth/`.
- Never edit a saved run's `documents/`. Rescoring rewrites only
  `scorecard.json`.
- When both runs have the same model and prompt version, say plainly that the
  result is a noise measurement, not an improvement or a regression caused by
  a change.

## Input

Two run folders: baseline first, candidate second, e.g.
`outputs/runs/20261007-051452 outputs/runs/20261007-083154`. A bare run id
means `outputs/runs/<id>`.

If either is missing or does not exist, run `ls outputs/runs/`, show the list
and ask which two to compare. Never guess, and never pick "the latest two" on
your own.

## Steps

1. Rescore both runs, so their committed scorecards match the current labels
   and scorer:

   ```
   uv run python evals/run_eval.py --rescore <baseline>
   uv run python evals/run_eval.py --rescore <candidate>
   ```

   A non-zero exit here only means a run has error documents; keep going.

2. Compare:

   ```
   uv run python evals/compare.py <baseline> <candidate> --json
   echo "exit=$?"
   ```

   Exit 0 is OK, 1 is a regression, 2 is a bad folder (stop and report it).

3. Report from the JSON, in this order:
   1. **First line:** `REGRESSION` with the `reasons`, or `OK`. Add "(noise
      measurement)" when `same_version` is true.
   2. **Header:** both run ids, models, prompt versions, cached counts, the
      number of documents compared, and any `only_in_baseline` /
      `only_in_candidate` documents.
   3. **Per field:** a table of correct counts before and after and the
      change, for the eight value fields and `document_type`, then
      hallucinations and line-item precision and recall.
   4. **Regressions,** grouped by field, and within each field by the new
      class: `hallucinated`, `missed`, `wrong_value`. Give file and the value
      before and after.
   5. **Fixes,** the same way.
   6. **Tokens and latency** before and after, over non-cached documents. If
      a side is mostly cached, say its latency is not a measurement.

4. If the exit code was 1, stop after the report. Do not propose prompt,
   label or code changes in the same turn; the user decides what to do next.

5. Append an entry to `docs/skill-usage.md` (format below). Fill "what was
   done next" with what the user said; if they have not said yet, write
   "pending" and ask.

## Usage log entry

```
### <YYYY-MM-DD> — <baseline id> vs <candidate id>

- **Why:** <the change being judged, or "noise measurement">
- **Found:** <verdict, value fields before -> after, the flips in one or two lines>
- **Next:** <what was done next>
```
