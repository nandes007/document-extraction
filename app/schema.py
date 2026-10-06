"""The extraction contract.

Transcribed from the Schema section of PROJECT_BRIEF.md. Field names, order and
types are the contract between the model, the API and the eval harness, so they
are not changed here without asking.
"""

from datetime import date
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, model_validator

T = TypeVar("T")

Status = Literal["present", "not_present", "unreadable"]
PaymentMethod = Literal[
    "cash", "debit", "credit", "card", "qris", "ewallet", "transfer", "other"
]


class Extracted(BaseModel, Generic[T]):
    """One field read off the document, with how sure we are and why.

    `not_present` means the field is absent from the document; `unreadable`
    means it is there but we will not guess. Both are abstentions and must
    carry no value.
    """

    value: T | None
    status: Status
    confidence: float
    evidence: str | None

    @model_validator(mode="after")
    def value_only_when_present(self) -> "Extracted[T]":
        if self.status != "present" and self.value is not None:
            raise ValueError(
                f"value must be null when status is {self.status!r}, got {self.value!r}"
            )
        return self


class LineItem(BaseModel):
    description: str
    quantity: float | None  # litres for fuel, kg for weighed goods
    unit_price: int | None
    amount: int | None


class ExpenseDocument(BaseModel):
    document_type: Literal["food", "fuel", "vehicle_service", "retail"]
    merchant_name: Extracted[str]
    transaction_date: Extracted[date]
    line_items: list[LineItem]
    subtotal: Extracted[int]
    discount: Extracted[int]
    service_charge: Extracted[int]
    tax: Extracted[int]
    total: Extracted[int]
    payment_method: Extracted[PaymentMethod]
