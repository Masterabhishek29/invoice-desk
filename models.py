"""The extraction contract. Null means unknown, never zero by default."""
from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LineItem(StrictModel):
    description: str | None
    quantity: str | None
    unit_price: str | None
    amount: str | None
    evidence: str | None


class Invoice(StrictModel):
    vendor_name: str | None
    invoice_number: str | None
    invoice_date: str | None
    po_reference: str | None
    currency: str | None
    line_items: list[LineItem]
    subtotal: str | None
    tax: str | None
    total: str | None
    quality: Literal["clear", "uncertain", "unreadable"]
    uncertainties: list[str]
    # Exact visible text with a page number, one entry for each header field.
    evidence: dict[str, str]

    @field_validator("subtotal", "tax", "total")
    @classmethod
    def valid_money(cls, value):
        if value is not None:
            number = Decimal(value)
            if not number.is_finite() or number < 0 or number.as_tuple().exponent < -2:
                raise ValueError("Money must be non-negative decimal text with at most 2 places")
        return value

    @field_validator("invoice_date")
    @classmethod
    def valid_date(cls, value):
        if value is not None:
            date.fromisoformat(value)
        return value
