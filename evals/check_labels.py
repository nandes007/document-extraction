"""Check the ground truth files against the documents and the schema.

Reads only; never writes a label. Run `uv run python evals/check_labels.py`.
Prints every problem as `<file>: <field>: <what>`, then a count by document
type and split. Exits 1 if there is any problem.
"""

import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import get_args

# Same reason as run_eval.py: `python evals/check_labels.py` puts evals/ on the
# path, not the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.schema import ExpenseDocument, PaymentMethod, Status  # noqa: E402
from evals.scoring import VALUE_FIELDS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS = ROOT / "data" / "documents"
GROUND_TRUTH = ROOT / "data" / "ground_truth"

SPLITS = ("dev", "test")
TEST_PREFIX = "test_"  # naming convention: test documents start with it
DOCUMENT_TYPES = get_args(ExpenseDocument.model_fields["document_type"].annotation)
STATUSES = get_args(Status)
PAYMENT_METHODS = get_args(PaymentMethod)
AMOUNT_FIELDS = ("subtotal", "discount", "service_charge", "tax", "total")


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _value_problem(field: str, value) -> str | None:
    """Why a `present` value has the wrong type for its field, or None."""
    if field == "merchant_name":
        ok = isinstance(value, str) and value.strip()
        return None if ok else "must be a non-empty string"
    if field == "transaction_date":
        try:
            ok = date.fromisoformat(value).isoformat() == value
        except (TypeError, ValueError):
            ok = False
        return None if ok else f"must be an ISO date YYYY-MM-DD, got {value!r}"
    if field == "payment_method":
        return None if value in PAYMENT_METHODS else f"{value!r} is not one of {PAYMENT_METHODS}"
    if field in AMOUNT_FIELDS:
        return None if _is_int(value) else f"must be an integer in rupiah, got {value!r}"
    return None


def check_label(stem: str, label: dict, document_names: set[str]) -> list[str]:
    """Problems in one ground truth file, as `field: what`."""
    problems = []

    file = label.get("file")
    if file not in document_names:
        problems.append(f"file: {file!r} is not in data/documents/")
    elif Path(file).stem != stem:
        problems.append(f"file: {file!r} does not match the label name {stem}.json")

    split = label.get("split")
    if split not in SPLITS:
        problems.append(f"split: {split!r} is not one of {SPLITS}")
    elif stem.startswith(TEST_PREFIX) != (split == "test"):
        problems.append(
            f"split: {split!r}, but names starting with {TEST_PREFIX!r} are "
            "exactly the test split"
        )

    tags = label.get("tags")
    if not (isinstance(tags, list) and all(isinstance(t, str) for t in tags)):
        problems.append("tags: must be a list of strings")

    if label.get("document_type") not in DOCUMENT_TYPES:
        problems.append(
            f"document_type: {label.get('document_type')!r} is not one of {DOCUMENT_TYPES}"
        )

    for field in VALUE_FIELDS:
        entry = label.get(field)
        if not isinstance(entry, dict):
            problems.append(f"{field}: missing")
            continue
        status, value = entry.get("status"), entry.get("value")
        if status not in STATUSES:
            problems.append(f"{field}.status: {status!r} is not one of {STATUSES}")
        elif status != "present" and value is not None:
            problems.append(f"{field}.value: must be null when status is {status!r}")
        elif status == "present" and value is None:
            problems.append(f"{field}.value: null, but status is 'present'")
        elif status == "present" and (problem := _value_problem(field, value)):
            problems.append(f"{field}.value: {problem}")

    accept = label.get("merchant_name", {}).get("accept", [])
    if not (isinstance(accept, list) and all(isinstance(a, str) for a in accept)):
        problems.append("merchant_name.accept: must be a list of strings")

    items = label.get("line_items")
    if not isinstance(items, list):
        problems.append("line_items: must be a list")
        items = []
    for i, item in enumerate(items):
        where = f"line_items[{i}]"
        if not isinstance(item, dict):
            problems.append(f"{where}: must be an object")
            continue
        description = item.get("description")
        if not (isinstance(description, str) and description.strip()):
            problems.append(f"{where}.description: must be a non-empty string")
        quantity = item.get("quantity")
        if quantity is not None and not _is_number(quantity):
            problems.append(f"{where}.quantity: must be a number or null, got {quantity!r}")
        for key in ("unit_price", "amount"):
            if item.get(key) is not None and not _is_int(item.get(key)):
                problems.append(f"{where}.{key}: must be an integer or null, got {item.get(key)!r}")

    return problems


def check(documents: Path, ground_truth: Path) -> tuple[list[str], Counter]:
    """All problems as `<file>: <field>: <what>`, and counts by (type, split)."""
    document_names = {p.name for p in documents.iterdir() if not p.name.startswith(".")}
    label_paths = sorted(ground_truth.glob("*.json"))
    problems = []
    counts: Counter = Counter()

    labelled = {p.stem for p in label_paths}
    for name in sorted(document_names):
        if Path(name).stem not in labelled:
            problems.append(f"{name}: no ground truth file {Path(name).stem}.json")

    for path in label_paths:
        try:
            label = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            problems.append(f"{path.name}: not valid JSON: {exc}")
            continue
        if not isinstance(label, dict):
            problems.append(f"{path.name}: must be a JSON object")
            continue
        problems += [f"{path.name}: {p}" for p in check_label(path.stem, label, document_names)]
        counts[(label.get("document_type"), label.get("split"))] += 1

    return problems, counts


def render_counts(counts: Counter) -> str:
    types = sorted({t for t, _ in counts}, key=str)
    lines = [f"{'type':<16}{'dev':>5}{'test':>6}{'total':>7}"]
    for t in types:
        dev, test = counts[(t, "dev")], counts[(t, "test")]
        lines.append(f"{str(t):<16}{dev:>5}{test:>6}{sum(n for (k, _), n in counts.items() if k == t):>7}")
    dev = sum(n for (_, s), n in counts.items() if s == "dev")
    test = sum(n for (_, s), n in counts.items() if s == "test")
    lines.append(f"{'total':<16}{dev:>5}{test:>6}{sum(counts.values()):>7}")
    return "\n".join(lines)


def main(documents: Path = DOCUMENTS, ground_truth: Path = GROUND_TRUTH) -> int:
    problems, counts = check(documents, ground_truth)
    for problem in problems:
        print(problem)
    if problems:
        print()
    print(render_counts(counts))
    print(f"\n{len(problems)} problem(s)" if problems else "\nall labels OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
