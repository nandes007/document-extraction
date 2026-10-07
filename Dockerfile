# One image for both services. Not shipped anywhere, so one stage is enough.
FROM docker.io/library/python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies before source, so a code edit does not reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY evals ./evals

# Processes start from the venv directly: `uv run` would sync the dev group
# at container start.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
