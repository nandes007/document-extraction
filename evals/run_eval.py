"""Eval harness: collect API responses into a run folder, then score them.

Collecting and scoring are separate so a run can be rescored without calling
the API: `--rescore outputs/runs/<id>`. Talks to the API over HTTP only, so it
scores the thing we ship rather than the code in this repo. Sends
EVAL_CONCURRENCY documents at once and reports cost and latency.
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import httpx

# Run as `python evals/run_eval.py` (compose, the task docs), Python puts
# evals/ on the path, not the repo root, so the package import needs this.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from evals.scoring import VALUE_FIELDS, match_line_items, score_fields  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS = ROOT / "data" / "documents"
GROUND_TRUTH = ROOT / "data" / "ground_truth"
RUNS = ROOT / "outputs" / "runs"

# Vision calls are slow; a tight timeout would score latency, not accuracy.
# The API gives up at 150s per provider call, so it should answer first.
TIMEOUT = 180.0

CLASSES = ["correct", "wrong_value", "missed", "hallucinated", "error"]

# Free tiers rate limit (429) and drop connections upstream (502, 503); those
# are worth another try. A timeout is not: the API already gave up.
RETRY_STATUSES = {429, 502, 503}
EVAL_RETRIES = 2
BACKOFF_SECONDS = (5, 15)  # wait before retry 1, retry 2


def concurrency() -> int:
    return max(1, int(os.environ.get("EVAL_CONCURRENCY", "3")))


def prices() -> dict:
    """US dollars per million tokens. Default 0: free tiers cost nothing."""
    return {
        "input_per_m": float(os.environ.get("PRICE_INPUT_PER_M", "0")),
        "output_per_m": float(os.environ.get("PRICE_OUTPUT_PER_M", "0")),
    }


# --- collect ----------------------------------------------------------------


def preflight(client: httpx.Client, api: str) -> bool:
    try:
        return client.get(f"{api}/health").status_code == 200
    except httpx.HTTPError:
        return False


def collect_document(path: Path, client: httpx.Client, api: str) -> dict:
    """POST one document, retrying RETRY_STATUSES with backoff. Never raises on
    a transport error: it is recorded. `wall_seconds` includes the waits."""
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    record: dict = {"file": path.name}
    started = time.perf_counter()
    attempt = 0
    while True:
        attempt += 1
        record["attempts"] = attempt
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
        if response.status_code not in RETRY_STATUSES or attempt > EVAL_RETRIES:
            break
        time.sleep(BACKOFF_SECONDS[attempt - 1])
    record |= {
        "http_status": response.status_code,
        "wall_seconds": round(time.perf_counter() - started, 2),
    }
    if response.status_code != 200:
        return record | {"error": response.text}
    return record | {"response": response.json()}


def collect(
    run_dir: Path, documents: list[Path], client: httpx.Client, api: str,
    workers: int = 1,
) -> None:
    """`workers` documents in flight at once, sharing one client. Each file is
    written as its document finishes; scoring sorts by name, so order is moot."""
    out = run_dir / "documents"
    out.mkdir(parents=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(collect_document, path, client, api): path for path in documents}
        for future in as_completed(futures):
            path, record = futures[future], future.result()
            (out / f"{path.stem}.json").write_text(json.dumps(record, indent=2) + "\n")
            outcome = "ok" if "response" in record else f"error: {record['error'][:80]}"
            retried = f" (attempt {record['attempts']})" if record["attempts"] > 1 else ""
            print(f"{path.name:26} {record['wall_seconds']:>7}s  {outcome}{retried}")


# --- score ------------------------------------------------------------------


def cost(usage: dict | None, price: dict) -> float:
    """Input is prompt_tokens; output is everything else in total_tokens, so
    reasoning tokens reported in neither prompt nor completion count as output."""
    if not usage:
        return 0.0
    prompt = usage.get("prompt_tokens", 0)
    output = usage.get("total_tokens", 0) - prompt
    return round((prompt * price["input_per_m"] + output * price["output_per_m"]) / 1e6, 6)


def p95(values: list[float]) -> float | None:
    if len(values) < 2:
        return values[0] if values else None  # quantiles needs two points
    # Inclusive: the default ("exclusive") extrapolates past the slowest
    # document on small runs, reporting a p95 above the max.
    return round(statistics.quantiles(values, n=20, method="inclusive")[18], 2)


def score_record(record: dict, truth: dict, price: dict | None = None) -> dict:
    result = {
        "file": record["file"],
        "split": truth["split"],
        "document_type": truth["document_type"],  # the label, used for slicing
        "http_status": record["http_status"],
        "wall_seconds": record["wall_seconds"],
        "http_attempts": record.get("attempts", 1),  # pre-task-13 runs: one try
    }
    if "response" not in record:
        # An error document counts every field as an error, so it cannot
        # quietly drop out of the denominator.
        return result | {
            "error": record["error"][:200],
            "fields": {name: {"class": "error"}
                       for name in [*VALUE_FIELDS, "document_type"]},
            "line_items": {"matched": 0, "missing": len(truth["line_items"]), "extra": 0},
        }

    document = record["response"]["document"]
    meta = record["response"]["meta"]
    return result | {
        "fields": score_fields(truth, document),
        "line_items": match_line_items(truth["line_items"], document["line_items"]),
        "provider_latency_seconds": meta["latency_seconds"],
        "attempts": meta["attempts"],
        "usage": meta["usage"],
        "cached": meta["cached"],
        # A cached answer cost nothing today; its usage describes the first call.
        "cost_usd": 0.0 if meta["cached"] else cost(meta["usage"], price or prices()),
    }


def _one_or_mixed(values: set) -> str | None:
    if not values:
        return None  # every document failed, so the API never said
    return values.pop() if len(values) == 1 else "mixed"


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


def _value_fields(results: list[dict]) -> dict:
    """Correct out of total over the eight value fields."""
    classes = [r["fields"][f]["class"] for r in results for f in VALUE_FIELDS]
    correct = classes.count("correct")
    return {"correct": correct, "total": len(classes),
            "accuracy": _ratio(correct, len(classes))}


def _per_field(results: list[dict], name: str) -> dict:
    counts = Counter(r["fields"][name]["class"] for r in results)
    return {c: counts[c] for c in CLASSES} | {
        "accuracy": _ratio(counts["correct"], len(results))
    }


def _line_items(results: list[dict]) -> dict:
    matched = sum(r["line_items"]["matched"] for r in results)
    missing = sum(r["line_items"]["missing"] for r in results)
    extra = sum(r["line_items"]["extra"] for r in results)
    return {"matched": matched, "missing": missing, "extra": extra,
            "precision": _ratio(matched, matched + extra),
            "recall": _ratio(matched, matched + missing)}


def score(run_dir: Path, run: dict, ground_truth: Path | None = None) -> dict:
    """Build a scorecard from saved responses only. Never calls the API."""
    ground_truth = ground_truth or GROUND_TRUTH
    records = [
        json.loads(p.read_text())
        for p in sorted((run_dir / "documents").glob("*.json"))
    ]
    if not records:
        sys.exit(f"no saved documents in {run_dir / 'documents'}")

    # Prices are fixed when the run is collected, so a rescore keeps them.
    # Runs from before task 13 have none: price them with today's settings.
    run = run | {"prices_usd_per_m": run.get("prices_usd_per_m") or prices()}
    results = []
    for record in records:
        truth_path = ground_truth / f"{Path(record['file']).stem}.json"
        results.append(score_record(record, json.loads(truth_path.read_text()),
                                    run["prices_usd_per_m"]))

    metas = [r["response"]["meta"] for r in records if "response" in r]
    fresh = [r for r in results if r.get("cached") is False]
    latencies = [r["provider_latency_seconds"] for r in fresh]
    run = {k: v for k, v in run.items() if k != "field_scored"}  # pre-task-7 key

    return {
        "run": run | {
            "model": _one_or_mixed({m["model"] for m in metas}),
            "prompt_version": _one_or_mixed({m["prompt_version"] for m in metas}),
            "fields_scored": [*VALUE_FIELDS, "document_type", "line_items"],
            "documents": len(results),
        },
        "summary": {
            "value_fields": _value_fields(results),
            "hallucinated": sum(
                r["fields"][f]["class"] == "hallucinated"
                for r in results for f in VALUE_FIELDS
            ),
            "error_documents": sum(1 for r in results if "error" in r),
            "failures": [
                {"file": r["file"], "field": f, "class": r["fields"][f]["class"]}
                for r in results for f in VALUE_FIELDS
                if r["fields"][f]["class"] != "correct"
            ],
            "fields": {
                name: _per_field(results, name)
                for name in [*VALUE_FIELDS, "document_type"]
            },
            "by_document_type": {
                t: _value_fields([r for r in results if r["document_type"] == t])
                for t in sorted({r["document_type"] for r in results})
            },
            "by_split": {
                s: _value_fields([r for r in results if r["split"] == s])
                for s in sorted({r["split"] for r in results})
            },
            "line_items": _line_items(results),
            # Tokens spent by this run: cached answers cost nothing today.
            "total_tokens": sum((r["usage"] or {}).get("total_tokens", 0) for r in fresh),
            "cached_documents": sum(1 for r in results if r.get("cached")),
            "cost_usd": round(sum(r.get("cost_usd", 0.0) for r in results), 6),
            "provider_latency_seconds": {
                "documents": len(latencies),
                "median": statistics.median(latencies) if latencies else None,
                "p95": p95(latencies),
                # quantiles() interpolates; under 20 points p95 is a rough guide.
                "p95_note": f"from {len(latencies)} documents, fewer than 20"
                if len(latencies) < 20 else None,
                "max": max(latencies) if latencies else None,
            },
        },
        "documents": results,
    }


def write_scorecard(run_dir: Path, scorecard: dict) -> int:
    path = run_dir / "scorecard.json"
    path.write_text(json.dumps(scorecard, indent=2) + "\n")
    summary = scorecard["summary"]
    value = summary["value_fields"]
    print(f"\n{value['correct']}/{value['total']} value fields correct, "
          f"{summary['hallucinated']} hallucinated -> {path}")
    latency = summary["provider_latency_seconds"]
    note = f" ({latency['p95_note']})" if latency["p95_note"] else ""
    wall = scorecard["run"].get("wall_clock_seconds")
    wall = f"{wall}s" if wall is not None else "not recorded"  # pre-task-13 runs
    print(f"cost ${summary['cost_usd']:.4f}, {summary['total_tokens']} tokens; "
          f"provider latency median {latency['median']}s, p95 {latency['p95']}s{note}"
          f" over {latency['documents']} non-cached; wall clock {wall}")
    for failure in summary["failures"]:
        print(f"  {failure['file']:26} {failure['field']:16} {failure['class']}")
    # Non-zero so `docker compose run eval` fails loudly on a broken run.
    return 1 if summary["error_documents"] else 0


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
    parser.add_argument("--split", choices=["dev", "test"],
                        help="send only this split's documents (default: all)")
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
    if args.split:
        # Tuning runs use dev only, so the held-back test split is not re-read.
        documents = [p for p in documents
                     if json.loads((GROUND_TRUTH / f"{p.stem}.json").read_text())["split"] == args.split]

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
               "started_at": _now(), "concurrency": concurrency(),
               "split": args.split or "all",
               "prices_usd_per_m": prices()}
        started = time.perf_counter()
        collect(run_dir, documents, client, api, workers=run["concurrency"])
        run["wall_clock_seconds"] = round(time.perf_counter() - started, 2)
        run["finished_at"] = _now()

    return write_scorecard(run_dir, score(run_dir, run))


if __name__ == "__main__":
    sys.exit(main())
