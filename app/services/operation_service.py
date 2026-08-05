from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import OperationStatus
from app.models.event import Event
from app.models.operation import Operation
from app.schemas.operation import CreateOperationRequest, OperationResponse


class OperationConflictError(Exception):
    pass


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
