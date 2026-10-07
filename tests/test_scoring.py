import pytest

from evals.scoring import VALUE_FIELDS, classify, match_line_items, merchant_matches, score_fields

PRESENT = {"value": 161700, "status": "present"}
ABSENT = {"value": None, "status": "not_present"}
UNREADABLE = {"value": None, "status": "unreadable"}


def test_same_value_is_correct():
    assert classify(PRESENT, dict(PRESENT)) == "correct"


def test_different_value_is_wrong():
    assert classify(PRESENT, {"value": 161000, "status": "present"}) == "wrong_value"


@pytest.mark.parametrize("actual", [ABSENT, UNREADABLE])
def test_abstaining_on_a_real_value_is_missed(actual):
    assert classify(PRESENT, actual) == "missed"


@pytest.mark.parametrize("expected", [ABSENT, UNREADABLE])
def test_inventing_a_value_is_hallucinated(expected):
    assert classify(expected, PRESENT) == "hallucinated"


@pytest.mark.parametrize("expected", [ABSENT, UNREADABLE])
@pytest.mark.parametrize("actual", [ABSENT, UNREADABLE])
def test_both_abstaining_is_correct(expected, actual):
    """Nothing missed, nothing invented — the two statuses need not match."""
    assert classify(expected, actual) == "correct"


def test_zero_is_a_value_not_an_absence():
    """A printed `Diskon: 0` is present with value 0, per the labelling rules."""
    zero = {"value": 0, "status": "present"}
    assert classify(zero, dict(zero)) == "correct"
    assert classify(zero, ABSENT) == "missed"
    assert classify(ABSENT, zero) == "hallucinated"


# --- merchant name ----------------------------------------------------------

MERCHANT = {"value": "Rumah Kecil Talenta", "status": "present",
            "accept": ["Rumah Kecil Talenta M Bloc", "Talenta"]}


@pytest.mark.parametrize("name", [
    "RUMAH KECIL TALENTA",          # case
    "Rumah  Kecil   Talenta ",      # spacing
    "talenta",                      # an accepted spelling
    "Rumah Kecil Talanta",          # one misread letter, ratio 94.7
])
def test_merchant_name_matches(name):
    assert merchant_matches(MERCHANT, name)


@pytest.mark.parametrize("name", [
    "Rumah Kecil",                  # ratio 73.3
    "Rumah Makan Talenta",          # a different brand, ratio 78.9
    "Kopi Kenangan",
])
def test_merchant_name_does_not_match(name):
    assert not merchant_matches(MERCHANT, name)


def test_merchant_mismatch_is_a_wrong_value():
    truth = {"merchant_name": MERCHANT} | _absent_fields_except("merchant_name")
    document = _document(merchant_name={"value": "Kopi Kenangan", "status": "present"})
    assert score_fields(truth, document)["merchant_name"]["class"] == "wrong_value"


# --- every field ------------------------------------------------------------


def _absent_fields_except(*present: str) -> dict:
    return {f: dict(ABSENT) for f in VALUE_FIELDS if f not in present} | {
        "document_type": "food"
    }


def _document(**fields) -> dict:
    absent = {"value": None, "status": "not_present", "confidence": 0.9, "evidence": None}
    return {f: absent for f in VALUE_FIELDS} | {"document_type": "food"} | {
        name: {"confidence": 0.9, "evidence": None} | value
        for name, value in fields.items()
    }


def test_one_document_can_miss_and_hallucinate_on_different_fields():
    truth = {"total": PRESENT} | _absent_fields_except("total")
    document = _document(discount={"value": 5000, "status": "present"})
    results = score_fields(truth, document)

    assert results["total"]["class"] == "missed"
    assert results["discount"]["class"] == "hallucinated"
    assert results["tax"]["class"] == "correct"


def test_document_type_is_scored_without_a_status():
    truth = _absent_fields_except() | {"document_type": "retail"}
    results = score_fields(truth, _document())
    assert results["document_type"] == {
        "expected": "retail", "extracted": "food", "class": "wrong_value"
    }
    assert "document_type" not in VALUE_FIELDS


# --- line items -------------------------------------------------------------


def _row(description, quantity=1, unit_price=None, amount=None):
    return {"description": description, "quantity": quantity,
            "unit_price": unit_price, "amount": amount}


def test_repeated_rows_are_matched_once_each():
    truth = [_row("ES TEH", amount=8000), _row("ES TEH", amount=8000)]
    predicted = [_row("Es Teh", amount=8000)]
    assert match_line_items(truth, predicted) == {"matched": 1, "missing": 1, "extra": 0}


def test_extra_and_wrong_amount_rows_do_not_match():
    truth = [_row("MISOA AYAM JAMUR", amount=48000)]
    predicted = [_row("MISOA AYAM JAMUR", amount=46000), _row("LESS SWEET", amount=0)]
    assert match_line_items(truth, predicted) == {"matched": 0, "missing": 1, "extra": 2}


def test_handwritten_rows_without_amounts_match_on_description():
    truth = [_row("Semen 2 sak", quantity=None), _row("Pasir", quantity=None)]
    predicted = [_row("pasir", quantity=None), _row("Semen 2 sak", quantity=None)]
    assert match_line_items(truth, predicted) == {"matched": 2, "missing": 0, "extra": 0}


def test_fuel_quantity_uses_a_tolerance_and_columns_run_together():
    truth = [_row("BPULTIMATE", quantity=3.07, unit_price=12930, amount=39695)]
    predicted = [_row("BP ULTIMATE", quantity=3.071, unit_price=12930, amount=39695)]
    assert match_line_items(truth, predicted)["matched"] == 1


def test_best_description_wins_when_amounts_tie():
    truth = [_row("KOPI SUSU", amount=25000), _row("TEH TARIK", amount=25000)]
    predicted = [_row("TEH TARIK", amount=25000), _row("KOPI SUSU", amount=25000)]
    assert match_line_items(truth, predicted)["matched"] == 2
