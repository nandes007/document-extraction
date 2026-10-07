# Task 4: Docker Compose

**Build order item:** 4
**Status:** todo

## Goal

`docker compose up` leaves the API serving. `docker compose run --rm eval` runs
the harness against it and writes a run folder to a mounted `outputs/runs/`.
Both work from a fresh clone with only a filled-in `.env`.

## Files

- `Dockerfile` — new. One image, used by both services.
- `docker-compose.yml` — new. `api` and `eval`.
- `.dockerignore` — new. `.git`, `.env`, `.cache`, `outputs`, `__pycache__`, `.venv`.
- `README.md` — new. A short "Run" section only.

## Steps

1. **Dockerfile.** Base image `docker.io/library/python:3.12-slim`, fully
   qualified because Podman does not resolve short names by default. Copy the
   `uv` binary in from `ghcr.io/astral-sh/uv`, copy `pyproject.toml` and
   `uv.lock`, run `uv sync --frozen --no-dev`, then copy the source. One stage:
   the image is not shipped anywhere. Dependency layer before source layer so
   code edits do not reinstall. Working directory `/app`.
2. **Start processes without `uv run`.** Put `/app/.venv/bin` on `PATH` and
   start `uvicorn` and `python` directly. `uv run` would try to sync the dev
   group at container start.
3. **`api` service.** Builds the image, `env_file: .env`, publishes `8000`,
   command `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
   Healthcheck on `GET /health` using Python, because the slim image has no
   `curl`. Mount `./.cache` to `/app/.cache` and set
   `CACHE_DIR=/app/.cache/responses`, so cached responses survive container
   rebuilds and are shared with local runs.
4. **`eval` service.** Same image, no ports, no `env_file`,
   `API_URL=http://api:8000`, command `python evals/run_eval.py`,
   `depends_on: api` with `condition: service_healthy`. Mount `./outputs`
   read-write so the run folder lands on the host, and `./data` read-only: a
   container must never be able to change ground truth.
5. **Secrets.** Keep `.env` out of the image and out of git. The compose file
   refers to it only through `env_file`.
6. **Portability.** Keep `docker-compose.yml` to plain Compose spec features
   so it runs under both engines. Local verification happens with
   `podman compose`; the README documents `docker compose`, which is what the
   grader will run.
7. **README.** A short "Run" section: how to copy `.env.example` to `.env` and
   fill it in, then the two `docker compose` commands, and where the run
   folder appears.
8. **Run by the user, not the agent:** one run through compose, committed.

## Done when

- [ ] `podman compose up -d` then `curl localhost:8000/health` returns 200.
- [ ] `podman compose ps` shows the `api` service as healthy.
- [ ] `docker-compose.yml` and `Dockerfile` contain no secret values; `.env`
      is referenced only through `env_file`. Do not run `compose config`: it
      prints the resolved values, including the API key.
- [ ] Nothing engine-specific in the compose file or Dockerfile: no
      Podman-only keys, no Docker-only build features.
- [ ] `README.md` exists with the "Run" section and nothing else yet.
- [ ] `uv run pytest` still passes.
- [ ] Checked by the user: `podman compose run --rm eval` exits 0, a new
      `outputs/runs/<run_id>/` is created on the host, and its scorecard
      shows `cached_documents: 6`.

## Out of scope

- Calling the real provider. The agent may start the API and call `/health`,
  but does not run the `eval` service; the user does.
- The full README (approach, architecture, results) — task 15.
- Recording the git commit inside the container. `git_commit` will read
  `"unknown"` for runs made through compose; that is accepted for now.
- Multi-stage builds, image size tuning, non-root user — not asked for.
- Rootless volume permission tuning beyond whatever `./outputs` and `./.cache`
  need to be writable. If a mount fights back, note it in the README rather
  than engineering around it.
- CI. The grader runs compose by hand.