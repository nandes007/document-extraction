"""Accuracy by stated confidence, from a saved run. No model or API calls.

`uv run python evals/calibration.py outputs/runs/<id>` prints, for `dev`
documents only, how often a `present` field was correct in each confidence
bucket. Uses the model's raw values: fields the API abstained on are restored
from `meta.abstained`, so a run with abstention still calibrates. Pick
ABSTAIN_THRESHOLD in app/validation.py from this table.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from evals.scoring import VALUE_FIELDS, score_fields  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GROUND_TRUTH = ROOT / "data" / "ground_truth"

# Lower bounds; each bucket runs up to the next one.
BUCKETS = [(0.0, "< 0.5"), (0.5, "0.5-0.7"), (0.7, "0.7-0.8"), (0.8, "0.8-0.9"),
           (0.9, "0.9-0.95"), (0.95, ">= 0.95")]


def raw_document(response: dict) -> dict:
    """The document as the model read it, before abstention."""
    document = dict(response["document"])
    for entry in response["meta"].get("abstained", []):
        document[entry["field"]] = document[entry["field"]] | {
            "value": entry["value"], "status": "present",
            "confidence": entry["confidence"],
        }
    return document


def _bucket(confidence: float) -> str:
    return [label for low, label in BUCKETS if confidence >= low][-1]


def calibrate(run_dir: Path, ground_truth: Path = GROUND_TRUTH) -> list[dict]:
    rows = {label: {"bucket": label, "fields": 0, "correct": 0} for _, label in BUCKETS}
    for path in sorted((run_dir / "documents").glob("*.json")):
        record = json.loads(path.read_text())
        truth = json.loads((ground_truth / f"{Path(record['file']).stem}.json").read_text())
        if truth["split"] != "dev" or "response" not in record:
            continue
        fields = score_fields(truth, raw_document(record["response"]))
        for name in VALUE_FIELDS:
            field = fields[name]
            if field["status"] != "present":
                continue  # abstention only ever touches present fields
            row = rows[_bucket(field["confidence"])]
            row["fields"] += 1
            row["correct"] += field["class"] == "correct"
    for row in rows.values():
        row["accuracy"] = round(row["correct"] / row["fields"], 3) if row["fields"] else None
    return list(rows.values())


def render(rows: list[dict]) -> str:
    lines = [f"{'confidence':<12}{'fields':>7}{'correct':>9}{'accuracy':>10}"]
    for r in rows:
        accuracy = f"{r['accuracy']:.3f}" if r["accuracy"] is not None else "-"
        lines.append(f"{r['bucket']:<12}{r['fields']:>7}{r['correct']:>9}{accuracy:>10}")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: calibration.py outputs/runs/<id>")
    print(render(calibrate(Path(sys.argv[1]))))
