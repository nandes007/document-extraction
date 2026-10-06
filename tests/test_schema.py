import pytest
from pydantic import ValidationError

from app.schema import Extracted, ExpenseDocument

# The food_receipts01 example from PROJECT_BRIEF.md, with the confidence and
# evidence that the model returns and ground truth omits.
VALID_DOCUMENT = {
    "document_type": "food",
    "merchant_name": {
        "value": "Rumah Kecil Talenta",
        "status": "present",
        "confidence": 0.95,
        "evidence": "RUMAH KECIL TALENTA",
    },
    "transaction_date": {
        "value": "2026-10-03",
        "status": "present",
        "confidence": 0.9,
        "evidence": "03-10-2026",
    },
    "line_items": [
        {
            "description": "MISOA AYAM JAMUR",
            "quantity": 1,
            "unit_price": 48000,
            "amount": 48000,
        }
    ],
    "subtotal": {
        "value": 140000,
        "status": "present",
        "confidence": 0.9,
        "evidence": "140,000",
    },
    "discount": {
        "value": None,
        "status": "not_present",
        "confidence": 0.9,
        "evidence": None,
    },
    "service_charge": {
        "value": 7000,
        "status": "present",
        "confidence": 0.9,
        "evidence": "7,000",
    },
    "tax": {"value": 14700, "status": "present", "confidence": 0.9, "evidence": "14,700"},
    "total": {
        "value": 161700,
        "status": "present",
        "confidence": 0.95,
        "evidence": "161,700",
    },
    "payment_method": {
        "value": "qris",
        "status": "present",
        "confidence": 0.95,
        "evidence": "QRIS",
    },
}


def test_valid_document_parses():
    doc = ExpenseDocument.model_validate(VALID_DOCUMENT)
    assert doc.total.value == 161700
    assert doc.transaction_date.value.isoformat() == "2026-10-03"
    assert doc.discount.value is None
    assert doc.line_items[0].description == "MISOA AYAM JAMUR"


@pytest.mark.parametrize("status", ["not_present", "unreadable"])
def test_abstention_must_not_carry_a_value(status):
    """A value under an abstaining status is the hallucination we score against."""
    with pytest.raises(ValidationError):
        Extracted[int](value=0, status=status, confidence=0.9, evidence="0")


@pytest.mark.parametrize("status", ["not_present", "unreadable"])
def test_abstention_with_no_value_is_fine(status):
    field = Extracted[int](value=None, status=status, confidence=0.4, evidence=None)
    assert field.value is None


def test_json_schema_generates():
    """The extractor hands this to the model as the structured-output schema."""
    schema = ExpenseDocument.model_json_schema()
    assert set(schema["required"]) == set(ExpenseDocument.model_fields)
