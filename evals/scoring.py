"""Field and line-item scoring. Pure functions: no files, no HTTP.

Every value field ends up in one of four classes. The two that matter most for
expense claims are `hallucinated` (a value the document does not have) and
`missed` (an abstention where a value exists): the first pays out money that
was never spent, the second only costs a person a look.
"""

from collections.abc import Callable

from rapidfuzz import fuzz

# The eight fields that carry a status. `document_type` has none and is
# scored on its own.
VALUE_FIELDS = [
    "merchant_name", "transaction_date", "subtotal", "discount",
    "service_charge", "tax", "total", "payment_method",
]

# fuzz.ratio is 0-100. 90 forgives one or two misread letters in a name of
# typical length ("Rumah Kecil Talenta" vs "Rumah Kecil Talanta" is 94.7) but not
# a different word.
MERCHANT_THRESHOLD = 90

# token_set_ratio, so "BPULTIMATE" still matches "BP ULTIMATE 92". Rows must
# already agree on amount and quantity, so this only has to rule out nonsense.
DESCRIPTION_THRESHOLD = 60

QUANTITY_TOLERANCE = 0.01


def classify(
    expected: dict, actual: dict, same: Callable[[object, object], bool] | None = None
) -> str:
    """Compare one field. `expected` and `actual` are {"value", "status"} dicts."""
    expected_has = expected["status"] == "present"
    actual_has = actual["status"] == "present"

    if expected_has and actual_has:
        equal = (same or (lambda a, b: a == b))(expected["value"], actual["value"])
        return "correct" if equal else "wrong_value"
    if expected_has:
        return "missed"  # we abstained where a value exists
    if actual_has:
        return "hallucinated"  # we gave a value where there is none to give
    # Both abstained. Nothing was missed and nothing invented, so this is right
    # even when one says "not_present" and the other "unreadable".
    return "correct"


def _norm(text: str) -> str:
    return " ".join(text.casefold().split())


def merchant_matches(expected: dict, actual_value: str) -> bool:
    """Label or any `accept` spelling, ignoring case and spacing, or close enough."""
    actual = _norm(actual_value)
    names = [_norm(n) for n in [expected["value"], *expected.get("accept", [])]]
    return any(n == actual or fuzz.ratio(n, actual) >= MERCHANT_THRESHOLD for n in names)


def score_fields(truth: dict, document: dict) -> dict:
    """Every value field plus document_type, for one document."""
    results = {}
    for name in VALUE_FIELDS:
        expected, actual = truth[name], document[name]
        same = (lambda _, a: merchant_matches(expected, a)) if name == "merchant_name" else None
        results[name] = {
            "expected": expected["value"],
            "extracted": actual["value"],
            "status": actual["status"],
            "confidence": actual["confidence"],
            "class": classify(expected, actual, same),
        }
    results["document_type"] = {
        "expected": truth["document_type"],
        "extracted": document["document_type"],
        "class": "correct" if truth["document_type"] == document["document_type"]
        else "wrong_value",
    }
    return results


def _quantity_equal(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is b
    return abs(a - b) <= QUANTITY_TOLERANCE


def match_line_items(truth_rows: list[dict], predicted_rows: list[dict]) -> dict:
    """Pair rows that agree on amount and quantity and look alike by description.

    Greedy, best description first, each row used once. Handwritten notes with
    no amounts still match: None equals None, and the description decides.
    """
    candidates = []
    for t, truth_row in enumerate(truth_rows):
        for p, row in enumerate(predicted_rows):
            if truth_row["amount"] != row["amount"]:
                continue
            if not _quantity_equal(truth_row["quantity"], row["quantity"]):
                continue
            similarity = fuzz.token_set_ratio(
                _norm(truth_row["description"]), _norm(row["description"])
            )
            if similarity >= DESCRIPTION_THRESHOLD:
                candidates.append((similarity, t, p))

    used_truth, used_predicted = set(), set()
    for _, t, p in sorted(candidates, reverse=True):
        if t not in used_truth and p not in used_predicted:
            used_truth.add(t)
            used_predicted.add(p)

    return {
        "matched": len(used_truth),
        "missing": len(truth_rows) - len(used_truth),
        "extra": len(predicted_rows) - len(used_predicted),
    }
