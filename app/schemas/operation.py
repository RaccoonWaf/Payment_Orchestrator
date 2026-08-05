from pydantic import BaseModel, Field, field_validator
from decimal import Decimal, InvalidOperation
import re


class CreateOperationRequest(BaseModel):
    operationId: str = Field(..., min_length=1, max_length=255)
    amount: str
    currency: str
    description: str = Field(..., min_length=1, max_length=512)

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        if not re.fullmatch(r"\d+(\.\d{1,2})?", v):
            raise ValueError(
                "amount must be a positive decimal string with at most 2 fractional digits"
            )
        try:
            value = Decimal(v)
        except InvalidOperation as e:
            raise ValueError("invalid amount") from e
        if value <= 0:
            raise ValueError("amount must be positive")
        return v

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        if v != "RUB":
            raise ValueError("only RUB currency is supported")
        return v


class OperationResponse(BaseModel):
    operationId: str
    amount: str
    currency: str
    description: str
    status: str
    providerPaymentId: str | None = None
