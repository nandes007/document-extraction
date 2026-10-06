# Task 4: Docker Compose

**Build order item:** 4
**Status:** todo

## Goal

`docker compose up` leaves the API serving. `docker compose run --rm eval` runs
the harness against it and writes the scorecard to a mounted `outputs/`. Both
work from a fresh clone with only a filled-in `.env`.

## Files

- `Dockerfile` — new. One image, used by both services.
- `docker-compose.yml` — new. `api` and `eval`.
- `.dockerignore` — new. `.git`, `.env`, `outputs`, `__pycache__`, `.venv`.

## Steps

1. Dockerfile: `python:3.12-slim`, copy the `uv` binary in from
   `ghcr.io/astral-sh/uv`, copy `pyproject.toml` and `uv.lock`, run
   `uv sync --frozen --no-dev`, then copy the source. One stage — the image
   is not shipped anywhere. Dependency layer before source layer so code
   edits do not reinstall.
2. `api` service: builds the image, `env_file: .env`, publishes `8000`,
   command `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000`.
   Healthcheck on `GET /health`.
3. `eval` service: same image, no ports, `API_URL=http://api:8000`,
   command `uv run python evals/run_eval.py`, `depends_on: api` with
   `condition: service_healthy`. Mount `./outputs` and `./data` so the
   scorecard lands on the host.
4. Keep `.env` out of the image and out of git. `.env.example` already lists
   `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`; add `API_URL`.
5. Commit a scorecard from a real run through compose, not from a local run.
6. Keep `docker-compose.yml` to plain Compose spec features so it runs under
   both engines. Local verification happens with `podman compose`; the README
   documents `docker compose`, which is what the grader will run.

## Done when

- [ ] `podman compose up -d` then `curl localhost:8000/health` returns 200.
- [ ] `podman compose run --rm eval` exits 0 and `outputs/scorecard.json` is
      updated on the host.
- [ ] `podman compose config` shows no literal secret values.
- [ ] Nothing engine-specific in the compose file or Dockerfile — no
      `podman`-only keys, no Docker-only build features.
- [ ] README has the two `docker compose` commands and nothing else is needed
      to reproduce the run.

## Out of scope

- Multi-stage builds, image size tuning, non-root user — not asked for.
- Rootless volume permission tuning beyond whatever `./outputs` needs to be
  writable. If the mount fights back, note it in the README rather than
  engineering around it.
- CI. The grader runs compose by hand.
