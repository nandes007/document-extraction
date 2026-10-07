"""Minimal eval harness: send every document to the API, score `total`.

Deliberately thin. It proves the loop — documents in, scorecard out — before
the real per-field scorer lands in task 7. Talks to the API over HTTP only, so
it scores the thing we ship rather than the code in this repo.
"""

import json
import mimetypes
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Only to record LLM_MODEL on the scorecard. The harness itself talks HTTP and
# needs no provider credentials.
load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS = ROOT / "data" / "documents"
GROUND_TRUTH = ROOT / "data" / "ground_truth"
SCORECARD = ROOT / "outputs" / "scorecard.json"

CLASSES = ["correct", "wrong_value", "missed", "hallucinated", "error"]


def classify(expected: dict, actual: dict) -> str:
    """Compare one field. `expected` and `actual` are {"value", "status"} dicts."""
    expected_has = expected["status"] == "present"
    actual_has = actual["status"] == "present"

    if expected_has and actual_has:
        return "correct" if expected["value"] == actual["value"] else "wrong_value"
    if expected_has:
        return "missed"  # we abstained where a value exists
    if actual_has:
        return "hallucinated"  # we gave a value where there is none to give
    # Both abstained. Nothing was missed and nothing invented, so this is right
    # even when one says "not_present" and the other "unreadable".
    return "correct"


def score_document(path: Path, truth: dict, client: httpx.Client, api: str) -> dict:
    """One document: POST it, time it, classify its total."""
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    started = time.perf_counter()
    response = client.post(
        f"{api}/extract",
        files={"file": (path.name, path.read_bytes(), content_type)},
    )
    latency = round(time.perf_counter() - started, 2)

    result = {
        "file": path.name,
        "split": truth["split"],
        "document_type": truth["document_type"],
        "expected_total": truth["total"]["value"],
        "latency_seconds": latency,
    }
    if response.status_code != 200:
        return result | {
            "class": "error",
            "error": f"HTTP {response.status_code}: {response.text[:200]}",
        }

    total = response.json()["document"]["total"]
    return result | {
        "extracted_total": total["value"],
        "status": total["status"],
        "class": classify(truth["total"], total),
    }


def main() -> int:
    api = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
    documents = sorted(p for p in DOCUMENTS.iterdir() if not p.name.startswith("."))
    if not documents:
        sys.exit(f"no documents in {DOCUMENTS}")

    results = []
    # Vision calls are slow; a tight timeout would score latency, not accuracy.
    with httpx.Client(timeout=180.0) as client:
        for path in documents:
            truth_path = GROUND_TRUTH / f"{path.stem}.json"
            if not truth_path.exists():
                # Skipping would quietly shrink the eval, which is worse than failing.
                sys.exit(f"no ground truth for {path.name}, expected {truth_path}")
            truth = json.loads(truth_path.read_text())

            try:
                result = score_document(path, truth, client, api)
            except httpx.RequestError as exc:
                sys.exit(f"cannot reach API at {api}: {exc}")

            print(f"{path.name:26} {result['class']:13} {result['latency_seconds']}s")
            results.append(result)

    counts = Counter(r["class"] for r in results)
    scorecard = {
        "run": {
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "api_url": api,
            "model": os.environ.get("LLM_MODEL", "unknown"),
            "field_scored": "total",
            "documents": len(results),
        },
        "summary": {
            "counts": {name: counts[name] for name in CLASSES},
            "accuracy": round(counts["correct"] / len(results), 3),
            "by_split": {
                split: _accuracy([r for r in results if r["split"] == split])
                for split in sorted({r["split"] for r in results})
            },
        },
        "documents": results,
    }

    SCORECARD.parent.mkdir(parents=True, exist_ok=True)
    SCORECARD.write_text(json.dumps(scorecard, indent=2) + "\n")

    print(
        f"\n{counts['correct']}/{len(results)} correct "
        f"({scorecard['summary']['accuracy']:.0%}) -> {SCORECARD.relative_to(ROOT)}"
    )
    # Non-zero so `docker compose run eval` fails loudly on a broken run.
    return 1 if counts["error"] else 0


def _accuracy(results: list[dict]) -> dict:
    correct = sum(1 for r in results if r["class"] == "correct")
    return {
        "documents": len(results),
        "correct": correct,
        "accuracy": round(correct / len(results), 3),
    }


if __name__ == "__main__":
    sys.exit(main())
