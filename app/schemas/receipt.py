from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ReceiptRequest(BaseModel):
    providerPaymentId: str = Field(..., min_length=1)
    operationId: str = Field(..., min_length=1)
    result: str
    message: str = ""
    occurredAt: datetime | None = None

    @field_validator("result")
    @classmethod
    def validate_result(cls, v: str) -> str:
        if v not in ("COMPLETED", "REJECTED"):
            raise ValueError("result must be COMPLETED or REJECTED")
        return v
