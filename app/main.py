"""The extraction API. One endpoint that matters, plus a healthcheck."""

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from openai import APIError, APITimeoutError, RateLimitError
from pydantic import ValidationError

from app.extractor import ProviderError, extract
from app.pages import NotAPdf, TooManyPages

# Local convenience only. Does not override variables already in the
# environment, so Docker's env_file still wins.
load_dotenv()

app = FastAPI(title="Expense document extraction")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness only. Never touches the provider, so compose can wait on it."""
    return {"status": "ok"}


# Sync def, so FastAPI runs this in a threadpool: the provider call blocks.
@app.post("/extract")
def extract_document(file: UploadFile = File(...)) -> dict:
    content_type = file.content_type or ""
    if not (content_type.startswith("image/") or content_type == "application/pdf"):
        raise HTTPException(
            415, f"expected an image or a PDF, got content type {content_type!r}"
        )
    try:
        document, meta = extract(file.file.read(), content_type)
    except NotAPdf as exc:
        raise HTTPException(415, str(exc)) from exc
    except TooManyPages as exc:
        raise HTTPException(413, str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(422, f"model output failed validation:\n{exc}") from exc
    except RateLimitError as exc:
        raise HTTPException(429, f"provider rate limit: {exc}") from exc
    except APITimeoutError as exc:
        raise HTTPException(504, f"provider timed out: {exc}") from exc
    except (APIError, ProviderError) as exc:  # provider down, rate limited, bad key
        raise HTTPException(502, f"provider call failed: {exc}") from exc
    except RuntimeError as exc:  # missing configuration
        raise HTTPException(500, str(exc)) from exc
    return {"document": document.model_dump(mode="json"), "meta": meta}
