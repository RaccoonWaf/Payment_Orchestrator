import uuid
from datetime import datetime, timezone

import pytest

from app.schemas.operation import CreateOperationRequest
from app.schemas.receipt import ReceiptRequest
from app.services.operation_service import (
    create_operation,
    get_operation,
    get_operation_events,
    submit_operation,
)
from app.services.receipt_service import (
    ReceiptProviderPaymentIdConflictError,
    process_receipt,
)


async def _create_and_submit(session, op_id: str) -> None:
    await create_operation(
        session,
        CreateOperationRequest(
            operationId=op_id,
            amount="30.00",
            currency="RUB",
            description="receipt test",
        ),
    )
    await submit_operation(session, op_id)


@pytest.mark.asyncio
async def test_receipt_sets_rejected(session):
    op_id = f"test-{uuid.uuid4()}"
    provider_payment_id = str(uuid.uuid4())

    await _create_and_submit(session, op_id)

    await process_receipt(
        session,
        ReceiptRequest(
            providerPaymentId=provider_payment_id,
            operationId=op_id,
            result="REJECTED",
            message="Payment rejected",
            occurredAt=datetime.now(timezone.utc),
        ),
    )

    op = await get_operation(session, op_id)
    assert op is not None
    assert getattr(op.status, "value", op.status) == "REJECTED"
    assert op.provider_payment_id == provider_payment_id


@pytest.mark.asyncio
async def test_receipt_idempotent_no_second_transition(session):
    op_id = f"test-{uuid.uuid4()}"
    provider_payment_id = str(uuid.uuid4())

    await _create_and_submit(session, op_id)

    receipt = ReceiptRequest(
        providerPaymentId=provider_payment_id,
        operationId=op_id,
        result="COMPLETED",
        message="ok",
        occurredAt=datetime.now(timezone.utc),
    )
    await process_receipt(session, receipt)
    await process_receipt(session, receipt)

    events = await get_operation_events(session, op_id)
    completed = [e for e in events if e.toStatus == "COMPLETED"]
    assert len(completed) == 1


@pytest.mark.asyncio
async def test_receipt_provider_id_conflict(session):
    op_id = f"test-{uuid.uuid4()}"
    pid1 = str(uuid.uuid4())
    pid2 = str(uuid.uuid4())

    await _create_and_submit(session, op_id)

    await process_receipt(
        session,
        ReceiptRequest(
            providerPaymentId=pid1,
            operationId=op_id,
            result="COMPLETED",
            message="ok",
            occurredAt=datetime.now(timezone.utc),
        ),
    )

    with pytest.raises(ReceiptProviderPaymentIdConflictError):
        await process_receipt(
            session,
            ReceiptRequest(
                providerPaymentId=pid2,
                operationId=op_id,
                result="COMPLETED",
                message="ok",
                occurredAt=datetime.now(timezone.utc),
            ),
        )