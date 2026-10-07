"""Eval harness: collect API responses into a run folder, then score them.

Collecting and scoring are separate so a run can be rescored without calling
the API: `--rescore outputs/runs/<id>`. Talks to the API over HTTP only, so it
scores the thing we ship rather than the code in this repo. Still `total` only;
the per-field scorer lands in task 7.
"""

import argparse
import json
import mimetypes
import os
import statistics
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS = ROOT / "data" / "documents"
GROUND_TRUTH = ROOT / "data" / "ground_truth"
RUNS = ROOT / "outputs" / "runs"

# Vision calls are slow; a tight timeout would score latency, not accuracy.
# The API gives up at 150s per provider call, so it should answer first.
TIMEOUT = 180.0

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


# --- collect ----------------------------------------------------------------


def preflight(client: httpx.Client, api: str) -> bool:
    try:
        return client.get(f"{api}/health").status_code == 200
    except httpx.HTTPError:
        return False


def collect_document(path: Path, client: httpx.Client, api: str) -> dict:
    """POST one document. Never raises on a transport error: it is recorded."""
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    record: dict = {"file": path.name}
    started = time.perf_counter()
    try:
        response = client.post(
            f"{api}/extract",
            files={"file": (path.name, path.read_bytes(), content_type)},
        )
    except httpx.HTTPError as exc:  # timeout, connection reset, ...
        return record | {
            "http_status": None,
            "wall_seconds": round(time.perf_counter() - started, 2),
            "error": type(exc).__name__,
        }
    record |= {
        "http_status": response.status_code,
        "wall_seconds": round(time.perf_counter() - started, 2),
    }
    if response.status_code != 200:
        return record | {"error": response.text}
    return record | {"response": response.json()}


def collect(run_dir: Path, documents: list[Path], client: httpx.Client, api: str) -> None:
    out = run_dir / "documents"
    out.mkdir(parents=True)
    for path in documents:
        record = collect_document(path, client, api)
        (out / f"{path.stem}.json").write_text(json.dumps(record, indent=2) + "\n")
        outcome = "ok" if "response" in record else f"error: {record['error'][:80]}"
        print(f"{path.name:26} {record['wall_seconds']:>7}s  {outcome}")


# --- score ------------------------------------------------------------------


def score_record(record: dict, truth: dict) -> dict:
    result = {
        "file": record["file"],
        "split": truth["split"],
        "document_type": truth["document_type"],
        "expected_total": truth["total"]["value"],
        "http_status": record["http_status"],
        "wall_seconds": record["wall_seconds"],
    }
    if "response" not in record:
        return result | {"class": "error", "error": record["error"][:200]}

    total = record["response"]["document"]["total"]
    meta = record["response"]["meta"]
    return result | {
        "extracted_total": total["value"],
        "status": total["status"],
        "class": classify(truth["total"], total),
        "provider_latency_seconds": meta["latency_seconds"],
        "attempts": meta["attempts"],
        "usage": meta["usage"],
        "cached": meta["cached"],
    }


def _one_or_mixed(values: set) -> str | None:
    if not values:
        return None  # every document failed, so the API never said
    return values.pop() if len(values) == 1 else "mixed"


def _accuracy(results: list[dict]) -> dict:
    correct = sum(1 for r in results if r["class"] == "correct")
    return {
        "documents": len(results),
        "correct": correct,
        "accuracy": round(correct / len(results), 3),
    }


def score(run_dir: Path, run: dict, ground_truth: Path | None = None) -> dict:
    """Build a scorecard from saved responses only. Never calls the API."""
    ground_truth = ground_truth or GROUND_TRUTH
    records = [
        json.loads(p.read_text())
        for p in sorted((run_dir / "documents").glob("*.json"))
    ]
    if not records:
        sys.exit(f"no saved documents in {run_dir / 'documents'}")

    results = []
    for record in records:
        truth_path = ground_truth / f"{Path(record['file']).stem}.json"
        results.append(score_record(record, json.loads(truth_path.read_text())))

    metas = [r["response"]["meta"] for r in records if "response" in r]
    fresh = [r for r in results if r.get("cached") is False]
    latencies = [r["provider_latency_seconds"] for r in fresh]
    counts = Counter(r["class"] for r in results)

    return {
        "run": run | {
            "model": _one_or_mixed({m["model"] for m in metas}),
            "prompt_version": _one_or_mixed({m["prompt_version"] for m in metas}),
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
            # Tokens spent by this run: cached answers cost nothing today.
            "total_tokens": sum((r["usage"] or {}).get("total_tokens", 0) for r in fresh),
            "cached_documents": sum(1 for r in results if r.get("cached")),
            "provider_latency_seconds": {
                "median": statistics.median(latencies) if latencies else None,
                "max": max(latencies) if latencies else None,
            },
        },
        "documents": results,
    }


def write_scorecard(run_dir: Path, scorecard: dict) -> int:
    path = run_dir / "scorecard.json"
    path.write_text(json.dumps(scorecard, indent=2) + "\n")
    counts = scorecard["summary"]["counts"]
    n = scorecard["run"]["documents"]
    print(f"\n{counts['correct']}/{n} correct "
          f"({scorecard['summary']['accuracy']:.0%}) -> {path}")
    # Non-zero so `docker compose run eval` fails loudly on a broken run.
    return 1 if counts["error"] else 0


# --- entry point ------------------------------------------------------------


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"  # no git in the container, or not a checkout


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rescore(run_dir: Path) -> int:
    old = run_dir / "scorecard.json"
    # Keep when and where the run happened; recompute everything else.
    run = json.loads(old.read_text())["run"] if old.exists() else {"run_id": run_dir.name}
    return write_scorecard(run_dir, score(run_dir, run))


def main(argv: list[str] | None = None, client: httpx.Client | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rescore", type=Path, metavar="RUN_DIR",
                        help="rebuild scorecard.json from a saved run, no API calls")
    args = parser.parse_args(argv)
    if args.rescore:
        return rescore(args.rescore)

    api = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
    documents = sorted(p for p in DOCUMENTS.iterdir() if not p.name.startswith("."))
    if not documents:
        sys.exit(f"no documents in {DOCUMENTS}")
    for path in documents:
        # Skipping would quietly shrink the eval, which is worse than failing.
        if not (GROUND_TRUTH / f"{path.stem}.json").exists():
            sys.exit(f"no ground truth for {path.name}")

    client = client or httpx.Client(timeout=TIMEOUT)
    with client:
        if not preflight(client, api):
            print(f"cannot reach API at {api}", file=sys.stderr)
            return 1

        run_id = os.environ.get("RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        run_dir = RUNS / run_id
        if run_dir.exists():
            sys.exit(f"run folder {run_dir} already exists; set another RUN_ID")

        run = {"run_id": run_id, "api_url": api, "git_commit": _git_commit(),
               "started_at": _now()}
        collect(run_dir, documents, client, api)
        run["finished_at"] = _now()

    return write_scorecard(run_dir, score(run_dir, run))


if __name__ == "__main__":
    sys.exit(main())
