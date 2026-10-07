"""Compare two eval runs and gate on regressions.

    uv run python evals/compare.py <baseline_run> <candidate_run> [--json]

Both runs are scored fresh from their saved documents against the current
labels, in memory: neither scorecard is written. Only documents present in
both runs are compared. Exit code 1 when any field's accuracy drops or the
hallucination count rises, 2 for bad arguments or a missing run folder.
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

# Run as `python evals/compare.py`, Python puts evals/ on the path, not the
# repo root, so the package import needs this.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from evals import run_eval  # noqa: E402
from evals.scoring import VALUE_FIELDS  # noqa: E402

FIELDS = [*VALUE_FIELDS, "document_type"]


def load(run_dir: Path) -> dict:
    """Score a saved run without writing anything."""
    old = run_dir / "scorecard.json"
    run = json.loads(old.read_text())["run"] if old.exists() else {"run_id": run_dir.name}
    return run_eval.score(run_dir, run)


def _side(scorecard: dict, files: list[str]) -> dict:
    """Per-field counts, tokens and latency over the shared documents only."""
    docs = [d for d in scorecard["documents"] if d["file"] in files]
    fresh = [d for d in docs if d.get("cached") is False]
    latencies = [d["provider_latency_seconds"] for d in fresh]
    return {
        "run_id": scorecard["run"].get("run_id"),
        "model": scorecard["run"]["model"],
        "prompt_version": scorecard["run"]["prompt_version"],
        "documents": len(docs),
        "cached_documents": sum(1 for d in docs if d.get("cached")),
        "correct": {
            f: sum(d["fields"][f]["class"] == "correct" for d in docs) for f in FIELDS
        },
        "hallucinated": sum(
            d["fields"][f]["class"] == "hallucinated" for d in docs for f in VALUE_FIELDS
        ),
        "line_items": run_eval._line_items(docs),
        "total_tokens": sum((d["usage"] or {}).get("total_tokens", 0) for d in fresh),
        "provider_latency_seconds": {
            "median": statistics.median(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
        },
    }


def _flip(before: dict, after: dict, field: str) -> dict:
    return {
        "file": before["file"],
        "field": field,
        "before": before["fields"][field]["class"],
        "after": after["fields"][field]["class"],
        "value_before": before["fields"][field].get("extracted"),
        "value_after": after["fields"][field].get("extracted"),
    }


def compare(baseline: dict, candidate: dict) -> dict:
    by_file_b = {d["file"]: d for d in baseline["documents"]}
    by_file_c = {d["file"]: d for d in candidate["documents"]}
    shared = sorted(by_file_b.keys() & by_file_c.keys())

    regressions, fixes = [], []
    for name in shared:
        b, c = by_file_b[name], by_file_c[name]
        for field in FIELDS:
            was = b["fields"][field]["class"] == "correct"
            now = c["fields"][field]["class"] == "correct"
            if was and not now:
                regressions.append(_flip(b, c, field))
            elif now and not was:
                fixes.append(_flip(b, c, field))

    before, after = _side(baseline, shared), _side(candidate, shared)
    # Same documents on both sides, so a lower correct count is a lower accuracy.
    reasons = [f"{f} accuracy dropped" for f in FIELDS
               if after["correct"][f] < before["correct"][f]]
    if after["hallucinated"] > before["hallucinated"]:
        reasons.append("hallucinations rose")

    return {
        "baseline": before,
        "candidate": after,
        "same_version": (before["model"], before["prompt_version"])
        == (after["model"], after["prompt_version"]),
        "shared_documents": len(shared),
        "only_in_baseline": sorted(by_file_b.keys() - by_file_c.keys()),
        "only_in_candidate": sorted(by_file_c.keys() - by_file_b.keys()),
        "regressions": regressions,
        "fixes": fixes,
        "regression": bool(reasons),
        "reasons": reasons,
    }


def _seconds(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}s"


def render(result: dict) -> str:
    b, c, n = result["baseline"], result["candidate"], result["shared_documents"]
    lines = []
    for label, side in (("baseline ", b), ("candidate", c)):
        lines.append(f"{label}  {side['run_id']}  model {side['model']}  "
                     f"prompt {side['prompt_version']}  "
                     f"cached {side['cached_documents']}/{side['documents']}")
    if result["same_version"]:
        lines.append("note: same model and prompt version on both sides, "
                     "so this measures run-to-run noise.")
    lines.append(f"documents compared: {n}")
    for key in ("only_in_baseline", "only_in_candidate"):
        if result[key]:
            lines.append(f"{key.replace('_', ' ')} (not counted): {', '.join(result[key])}")

    lines += ["", f"{'field':18} {'before':>7} {'after':>7} {'change':>7}"]
    for f in FIELDS:
        was, now = b["correct"][f], c["correct"][f]
        lines.append(f"{f:18} {f'{was}/{n}':>7} {f'{now}/{n}':>7} {now - was:>+7}")
    was, now = sum(b["correct"][f] for f in VALUE_FIELDS), sum(c["correct"][f] for f in VALUE_FIELDS)
    total = n * len(VALUE_FIELDS)
    lines.append(f"{'value fields':18} {f'{was}/{total}':>7} {f'{now}/{total}':>7} {now - was:>+7}")
    lines.append(f"{'hallucinated':18} {b['hallucinated']:>7} {c['hallucinated']:>7} "
                 f"{c['hallucinated'] - b['hallucinated']:>+7}")
    for key in ("precision", "recall"):
        lines.append(f"{'line item ' + key:18} {b['line_items'][key] or 0:>7.3f} "
                     f"{c['line_items'][key] or 0:>7.3f}")

    for title, flips in (("regressions", result["regressions"]), ("fixes", result["fixes"])):
        lines += ["", f"{title} ({len(flips)})"]
        for x in flips:
            lines.append(f"  {x['file']:24} {x['field']:16} {x['before']} -> {x['after']}  "
                         f"{x['value_before']!r} -> {x['value_after']!r}")

    lines += ["", "cost and speed (non-cached documents only)",
              f"  total tokens    {b['total_tokens']:>9} -> {c['total_tokens']}"]
    for key in ("median", "max"):
        lines.append(f"  latency {key:7} {_seconds(b['provider_latency_seconds'][key]):>9} -> "
                     f"{_seconds(c['provider_latency_seconds'][key])}")

    verdict = "REGRESSION: " + "; ".join(result["reasons"]) if result["regression"] else "OK"
    lines += ["", verdict]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args(argv)  # bad arguments exit 2

    for run_dir in (args.baseline, args.candidate):
        if not (run_dir / "documents").is_dir():
            print(f"not a run folder: {run_dir} (no documents/)", file=sys.stderr)
            return 2

    result = compare(load(args.baseline), load(args.candidate))
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 1 if result["regression"] else 0


if __name__ == "__main__":
    sys.exit(main())
