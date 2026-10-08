"""Arithmetic checks and the abstention rule. Pure functions: no I/O.

Runs after the cache, on the model's raw document, so changing a check or the
threshold needs no model calls: rerun with the cache on.

Each check gives `pass`, `fail` or `skipped` and names the fields it covers. A
`present` field that takes part in a failed check, or whose confidence is below
ABSTAIN_THRESHOLD, is returned as `unreadable`: a wrong amount in an expense
claim pays out money, an abstention only costs a person a look.
"""

from app.schema import ExpenseDocument

# Relative tolerance for quantity * unit_price vs amount. Fuel receipts round
# the litres: 3.96 x 12,610 = 49,935.6, printed 50,000 (0.13% off).
LINE_TOLERANCE = 0.01

# Accuracy of `present` fields by stated confidence, dev documents only, run
# v2-full (prompt v2, 7 dev documents):
# `uv run python evals/calibration.py outputs/runs/v2-full`
#
#   confidence   fields  correct  accuracy
#   < 0.5             0        0         -
#   0.5-0.7           0        0         -
#   0.7-0.8           0        0         -
#   0.8-0.9           2        1     0.500
#   0.9-0.95          1        1     1.000
#   >= 0.95          30       27     0.900
#
# 0.9 abstains on the 0.8-0.9 bucket: half wrong (service_receipts01
# service_charge), so it costs one correct value to stop one wrong one. Raising
# to 0.95 would only drop the one correct 0.9-0.95 value. The three wrong values
# at >= 0.95 are confident mistakes no threshold can catch; the arithmetic
# checks are the defence there. Small sample (33 fields): one threshold, no
# per-field tuning. Earlier table (run 20261007-083154, prompt v1, 6 dev
# documents): 0.9-0.95 3/4, >= 0.95 24/26, nothing below 0.9.
ABSTAIN_THRESHOLD = 0.9

AMOUNT_FIELDS = ("subtotal", "discount", "service_charge", "tax", "total")


def _check(name: str, result: str, fields: list[str], detail: str) -> dict:
    return {"name": name, "result": result, "fields": fields, "detail": detail}


def _amount(document: ExpenseDocument, field: str) -> int | None:
    extracted = getattr(document, field)
    return extracted.value if extracted.status == "present" else None


def line_items_sum(document: ExpenseDocument) -> dict:
    """Item amounts sum to subtotal, or to total when there is no subtotal."""
    amounts = [item.amount for item in document.line_items if item.amount is not None]
    target = "subtotal" if _amount(document, "subtotal") is not None else "total"
    expected = _amount(document, target)
    if not amounts or len(amounts) < len(document.line_items) or expected is None:
        return _check("line_items_sum", "skipped", [], "no items, an item without an amount, or no subtotal or total")
    got = sum(amounts)
    result = "pass" if got == expected else "fail"
    return _check("line_items_sum", result, [target], f"items sum to {got}, {target} is {expected}")


def totals(document: ExpenseDocument) -> dict:
    """subtotal - discount + service_charge + tax == total; tax-inclusive passes."""
    subtotal, total = _amount(document, "subtotal"), _amount(document, "total")
    if subtotal is None or total is None:
        return _check("totals", "skipped", [], "needs both subtotal and total")
    # An unreadable component is not 0: checking without it would blame the others.
    if any(getattr(document, f).status == "unreadable" for f in AMOUNT_FIELDS):
        return _check("totals", "skipped", [], "a component is unreadable")
    discount, service, tax = (_amount(document, f) or 0 for f in ("discount", "service_charge", "tax"))
    fields = [f for f in AMOUNT_FIELDS if _amount(document, f) is not None]
    without_tax = subtotal - discount + service
    if without_tax + tax == total:
        return _check("totals", "pass", fields, f"{without_tax + tax} == {total}")
    if without_tax == total:
        return _check("totals", "pass", fields, f"tax-inclusive: {without_tax} == {total}")
    return _check("totals", "fail", fields, f"{without_tax + tax} (or {without_tax} without tax) != {total}")


def line_arithmetic(document: ExpenseDocument) -> dict:
    """quantity * unit_price == amount per row, within LINE_TOLERANCE.

    Names no fields: line items carry no status, so a failure is reported, not
    abstained on.
    """
    rows = [(i, q * u, a) for i, item in enumerate(document.line_items)
            if (q := item.quantity) is not None and (u := item.unit_price) is not None
            and (a := item.amount) is not None]
    if not rows:
        return _check("line_arithmetic", "skipped", [], "no row has quantity, unit price and amount")
    bad = [i for i, product, amount in rows
           if abs(product - amount) > LINE_TOLERANCE * abs(amount)]
    if bad:
        return _check("line_arithmetic", "fail", [], f"rows {bad} off by more than {LINE_TOLERANCE:.0%}")
    return _check("line_arithmetic", "pass", [], f"{len(rows)} row(s) within {LINE_TOLERANCE:.0%}")


CHECKS = (line_items_sum, totals, line_arithmetic)


def run_checks(document: ExpenseDocument) -> list[dict]:
    return [check(document) for check in CHECKS]


def abstain(
    document: ExpenseDocument, checks: list[dict], threshold: float | None = None
) -> tuple[ExpenseDocument, list[dict]]:
    """Turn doubtful `present` fields into `unreadable`. Returns a new document
    and what was abstained on, with the original value and confidence."""
    threshold = ABSTAIN_THRESHOLD if threshold is None else threshold
    failed: dict[str, list[str]] = {}
    for check in checks:
        if check["result"] == "fail":
            for field in check["fields"]:
                failed.setdefault(field, []).append(check["name"])

    updates, abstained = {}, []
    for field, extracted in document:
        if not hasattr(extracted, "status") or extracted.status != "present":
            continue
        reasons = [f"check:{name}" for name in failed.get(field, [])]
        if extracted.confidence < threshold:
            reasons.append("low_confidence")
        if not reasons:
            continue
        abstained.append({
            "field": field,
            "reason": reasons,
            "value": extracted.model_dump(mode="json")["value"],
            "confidence": extracted.confidence,
        })
        updates[field] = extracted.model_copy(
            update={"value": None, "status": "unreadable", "evidence": None}
        )
    return document.model_copy(update=updates), abstained
