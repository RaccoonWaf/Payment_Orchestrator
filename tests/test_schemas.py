import pytest
from pydantic import ValidationError

from app.schemas.operation import CreateOperationRequest


def test_amount_ok():
    data = CreateOperationRequest(
        operationId="op-1",
        amount="100.50",
        currency="RUB",
        description="test",
    )
    assert data.amount == "100.50"


def test_amount_rejects_too_many_decimals():
    with pytest.raises(ValidationError):
        CreateOperationRequest(
            operationId="op-1",
            amount="100.999",
            currency="RUB",
            description="test",
        )


def test_currency_must_be_rub():
    with pytest.raises(ValidationError):
        CreateOperationRequest(
            operationId="op-1",
            amount="10.00",
            currency="USD",
            description="test",
        )
