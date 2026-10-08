import json

from app.extractor import extract
from app.schema import ExpenseDocument
from app.validation import abstain, line_arithmetic, line_items_sum, run_checks, totals
from tests.test_extractor import FakeClient, temp_cache  # noqa: F401
from tests.test_schema import VALID_DOCUMENT


def field(value, status="present", confidence=0.99):
    return {"value": value, "status": status, "confidence": confidence,
            "evidence": None if value is None else str(value)}


ABSENT = field(None, "not_present")


def doc(items=(), subtotal=ABSENT, discount=ABSENT, service_charge=ABSENT,
        tax=ABSENT, total=ABSENT, **fields) -> ExpenseDocument:
    """A document with the given amounts; everything else valid and confident."""
    return ExpenseDocument.model_validate(VALID_DOCUMENT | {
        "line_items": [{"description": "x", "quantity": q, "unit_price": u, "amount": a}
                       for q, u, a in items],
        "subtotal": subtotal, "discount": discount, "service_charge": service_charge,
        "tax": tax, "total": total,
        "merchant_name": field("Shop"), "transaction_date": field("2026-10-03"),
        "payment_method": field("cash"),
    } | fields)


# --- line_items_sum ---------------------------------------------------------


def test_items_sum_to_subtotal_passes():
    check = line_items_sum(doc([(1, 10, 10), (2, 5, 10)], subtotal=field(20), total=field(22)))
    assert check["result"] == "pass" and check["fields"] == ["subtotal"]


def test_items_sum_to_total_when_no_subtotal():
    check = line_items_sum(doc([(1, 10, 10)], total=field(10)))
    assert check["result"] == "pass" and check["fields"] == ["total"]


def test_items_not_summing_fails():
    assert line_items_sum(doc([(1, 10, 10)], subtotal=field(99)))["result"] == "fail"


def test_item_without_amount_skips():
    assert line_items_sum(doc([(1, 10, None)], total=field(10)))["result"] == "skipped"


# --- totals -----------------------------------------------------------------


def test_totals_with_every_component_passes():
    # The brief's example receipt: 140,000 + 7,000 + 14,700 = 161,700.
    document = doc(subtotal=field(140000), discount=field(0), service_charge=field(7000),
                   tax=field(14700), total=field(161700))
    check = totals(document)
    assert check["result"] == "pass"
    assert check["fields"] == ["subtotal", "discount", "service_charge", "tax", "total"]


def test_tax_inclusive_receipt_passes():
    check = totals(doc(subtotal=field(110000), tax=field(10000), total=field(110000)))
    assert check["result"] == "pass" and "tax-inclusive" in check["detail"]


def test_totals_that_do_not_add_up_fail():
    assert totals(doc(subtotal=field(100), tax=field(10), total=field(500)))["result"] == "fail"


def test_totals_without_subtotal_skips():
    assert totals(doc(total=field(100)))["result"] == "skipped"


def test_totals_with_an_unreadable_component_skips():
    document = doc(subtotal=field(100), tax=field(None, "unreadable"), total=field(110))
    assert totals(document)["result"] == "skipped"


# --- line_arithmetic --------------------------------------------------------


def test_rounded_fuel_litres_pass():
    # 3.96 x 12,610 = 49,935.6, printed 50,000.
    assert line_arithmetic(doc([(3.96, 12610, 50000)]))["result"] == "pass"


def test_row_far_off_fails():
    assert line_arithmetic(doc([(2, 10000, 30000)]))["result"] == "fail"


def test_rows_without_quantity_skip():
    assert line_arithmetic(doc([(None, None, 5000)]))["result"] == "skipped"


# --- abstention -------------------------------------------------------------


def test_low_confidence_field_abstains():
    document = doc(total=field(100), merchant_name=field("Shop", confidence=0.4))
    result, abstained = abstain(document, run_checks(document), threshold=0.9)
    assert result.merchant_name.status == "unreadable"
    assert result.merchant_name.value is None
    assert abstained == [{"field": "merchant_name", "reason": ["low_confidence"],
                          "value": "Shop", "confidence": 0.4}]


def test_field_in_a_failed_check_abstains():
    document = doc([(1, 10, 10)], subtotal=field(99), total=field(99))
    result, abstained = abstain(document, run_checks(document))
    assert result.subtotal.status == "unreadable"
    assert result.total.value == 99  # totals passed, so total stands
    assert abstained == [{"field": "subtotal", "reason": ["check:line_items_sum"],
                          "value": 99, "confidence": 0.99}]


def test_clean_document_is_unchanged():
    document = doc([(1, 10, 10)], subtotal=field(10), tax=field(1), total=field(11))
    result, abstained = abstain(document, run_checks(document))
    assert result == document and abstained == []


def test_absent_fields_are_never_touched():
    document = doc(total=field(100), discount=field(None, "not_present", 0.1))
    result, _ = abstain(document, run_checks(document))
    assert result.discount.status == "not_present"


# --- through extract() ------------------------------------------------------


def test_cache_hit_reapplies_the_current_rules(monkeypatch):
    # Items sum to 10, subtotal says 99: the check fails on the raw document.
    raw = doc([(1, 10, 10)], subtotal=field(99), total=field(99)).model_dump(mode="json")
    client = FakeClient(json.dumps(raw))
    first, first_meta = extract(b"img", client=client, model="m")
    assert first.subtotal.status == "unreadable"
    assert [c["result"] for c in first_meta["checks"]] == ["fail", "pass", "pass"]

    # A stricter threshold on the next call, served from the cache.
    monkeypatch.setattr("app.validation.ABSTAIN_THRESHOLD", 1.0)
    second, second_meta = extract(b"img", client=client, model="m")
    assert len(client.calls) == 1 and second_meta["cached"] is True
    assert second.total.status == "unreadable"  # newly abstained, from the raw cache
    assert {a["field"] for a in second_meta["abstained"]} >= {"subtotal", "total"}
