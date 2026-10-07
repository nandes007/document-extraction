# Task 15: README, real Docker check, submission

**Build order item:** 15
**Status:** todo
**Owner:** user, with the agent drafting sections from committed results.
**Depends on:** everything else

## Goal

A README a reviewer can follow and judge from, verified on real Docker from a
fresh clone, with the final runs committed.

## Files

- `README.md` — the full document. The "Run" section from task 4 stays first.
- `outputs/runs/` — the final `dev` and `test` runs.

## Steps

1. **README sections**, each drafted from committed files, not from memory:
   1. Run: the two `docker compose` commands, `.env`, where results appear.
   2. Dataset: counts by type and split, sources, link to `docs/dataset.md`.
   3. Schema and approach, and why: status per field, abstention.
   4. Architecture: one vision call with structured output, validation in
      code, one retry on invalid JSON, cache. Why not an agent loop.
   5. Key trade-offs.
   6. Eval results: `dev` and `test`, per field, failures by kind,
      hallucination count, line-item precision and recall, noise floor.
   7. Cost and latency, and the optimization table from task 14.
   8. Agentic development: the task files, the `eval-compare` skill and its
      usage log.
   9. What I would do with more time.
2. **Every number** in the README is checked against a committed scorecard.
3. **Real Docker from a fresh clone:** `git clone`, `cp .env.example .env`
   and fill it, `docker compose up -d`, `docker compose run --rm eval`. Not
   Podman. Docker Desktop with WSL integration or a Linux machine.
4. **Secrets and personal data:** `git log --all -- .env` is empty; no key
   appears in `git log -p`; committed images are redacted.
5. **Final runs committed**, with their scorecards and per-document files.
6. **Read every file once more** before the last commit.
7. **Invite the three reviewers** named in the email to the repository.

## Done when

- [ ] A fresh clone runs end to end on real Docker.
- [ ] Every README number matches a committed scorecard.
- [ ] No secrets or unredacted personal data in the history.
- [ ] Reviewers invited before Friday 2026-10-09, 07:49 WIB.

## Out of scope

- New features. After this task starts, only fixes.
