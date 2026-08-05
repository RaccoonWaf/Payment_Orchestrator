from datetime import datetime, timezone

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import OperationStatus
from app.models.event import Event
from app.models.operation import Operation
from app.schemas.operation import CreateOperationRequest, OperationResponse


class OperationConflictError(Exception):
    pass


class OperationNotFoundError(Exception):
    pass


async def submit_operation(
    session: AsyncSession,
    operation_id: str,
) -> tuple[OperationResponse, int]:
    """
    Возвращает (response, http_status_code).
    202 — намерение только что создано
    200 — повторный submit / уже не CREATED
    """
    result = await session.execute(
        select(Operation)
        .where(Operation.operation_id == operation_id)
        .with_for_update()
    )
    operation = result.scalar_one_or_none()

    if operation is None:
        raise OperationNotFoundError(f"Operation {operation_id} not found")

    if operation.status != OperationStatus.CREATED:
        return to_operation_response(operation), status.HTTP_200_OK

    operation.status = OperationStatus.PROCESSING
    operation.submit_intent_at = datetime.now(timezone.utc)

    last_event_id = await session.scalar(
        select(Event.event_id)
        .where(Event.operation_id == operation_id)
        .order_by(Event.event_id.desc())
        .limit(1)
    )
    next_event_id = (last_event_id or 0) + 1

    session.add(
        Event(
            event_id=next_event_id,
            operation_id=operation_id,
            type="PROCESSING",
            from_status="CREATED",
            to_status="PROCESSING",
            message="Submit intent saved",
        )
    )

    await session.commit()
    await session.refresh(operation)

    return to_operation_response(operation), status.HTTP_202_ACCEPTED


def to_operation_response(operation: Operation) -> OperationResponse:
    return OperationResponse(
        operationId=operation.operation_id,
        amount=f"{operation.amount:.2f}",
        currency=operation.currency,
        description=operation.description,
        status=operation.status.value if hasattr(operation.status, "value") else str(operation.status),
        providerPaymentId=operation.provider_payment_id,
    )


async def create_operation(
    session: AsyncSession,
    data: CreateOperationRequest,
) -> OperationResponse:
    existing = await session.scalar(
        select(Operation).where(Operation.operation_id == data.operationId)
    )
    if existing is not None:
        raise OperationConflictError(
            f"Operation {data.operationId} already exists"
            )

    operation = Operation(
        operation_id=data.operationId,
        amount=data.amount,
        currency=data.currency,
        description=data.description,
        status=OperationStatus.CREATED,
        provider_payment_id=None,
    )
    session.add(operation)

    event = Event(
        event_id=1,
        operation_id=data.operationId,
        type="CREATED",
        from_status=None,
        to_status="CREATED",
        message="Operation created",
    )
    session.add(event)

    await session.commit()
    await session.refresh(operation)

    return to_operation_response(operation)


async def get_operation(
    session: AsyncSession,
    operation_id: str,
) -> Operation | None:
    return await session.scalar(
        select(Operation).where(Operation.operation_id == operation_id)
    )
