# Task 9: Custom extension, `eval-compare` skill

**Build order item:** hard requirement "ship one custom coding-agent extension
that was actually used"
**Status:** todo
**Depends on:** task 8

## Goal

A Claude Code skill that compares two eval runs, reports regressions and fixes
by field and failure kind, and stops on a regression. It is committed before
the first prompt change, and every use is logged.

Why now: it has to exist before prompt v2 (task 12) so the git history shows
it in use on that change, not written afterwards.

## Files

- `.claude/skills/eval-compare/SKILL.md` — new. The skill.
- `docs/skill-usage.md` — new. One entry per use.

## Steps

1. **Frontmatter.** `name: eval-compare` and a `description` that says when
   to use it: comparing a baseline and a candidate run folder under
   `outputs/runs/`.
2. **Input:** a baseline and a candidate run folder. If either is missing,
   list `outputs/runs/` and ask; never guess.
3. **Steps for the agent:**
   1. Rescore both: `uv run python evals/run_eval.py --rescore <run>`.
   2. Run `uv run python evals/compare.py <baseline> <candidate> --json`.
   3. Report: header (models, prompt versions, cached counts), per-field
      change, then regressions grouped by field and by kind (hallucinated,
      missed, wrong value), then fixes, then tokens and latency.
   4. If the exit code is 1, say "regression" in the first line, list the
      flips, and stop. Do not propose prompt edits in the same turn.
   5. Append an entry to `docs/skill-usage.md`.
4. **Hard rules in the skill:** never call the provider or start an eval run;
   never edit `data/ground_truth/`; never edit a saved run's `documents/`;
   when the two runs share a model and prompt version, say the result is a
   noise measurement.
5. **Usage log format:** date, baseline, candidate, why it was run, what it
   found (one or two lines), and what was done next.
6. **First real use:** `20261007-051452` against `20261007-083154`, the two
   v1 runs. Log it.

## Done when

- [ ] The skill shows up in Claude Code (`/eval-compare` is listed).
- [ ] One logged use in `docs/skill-usage.md`, from a real invocation.
- [ ] Committed in its own commit, before any change to `PROMPT`.

## Out of scope

- Hooks, MCP servers or other extension types. One skill is enough.
- Running evals from the skill. The user starts real runs.
