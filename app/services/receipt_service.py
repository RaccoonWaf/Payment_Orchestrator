from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import OperationStatus
from app.models.event import Event
from app.models.operation import Operation
from app.schemas.receipt import ReceiptRequest


class ReceiptOperationNotFoundError(Exception):
    pass


class ReceiptProviderPaymentIdConflictError(Exception):
    pass


async def process_receipt(session: AsyncSession, data: ReceiptRequest) -> None:
    result = await session.execute(
        select(Operation).where(
            Operation.operation_id == data.operationId
            ).with_for_update()  # Блокировка строки базы данных на время выполнения транзакции, для исключения возникновения race condition.
    )
    operation = result.scalar_one_or_none()

    if operation is None:
        raise ReceiptOperationNotFoundError(
            f"Operation {data.operationId} not found"
        )

    # Зашита от привязки результата платежа к сторонней транзакции
    if (
        operation.provider_payment_id is not None
        and operation.provider_payment_id != data.providerPaymentId
    ):
        raise ReceiptProviderPaymentIdConflictError(
            "providerPaymentId does not match operation"
        )

    if operation.provider_payment_id is None:
        operation.provider_payment_id = data.providerPaymentId

    target_status = OperationStatus(data.result)
    # Обеспечение идемпотентности обработки операции
    if operation.status in (
        OperationStatus.COMPLETED, OperationStatus.REJECTED
            ):
        await session.commit()
        return

    from_status = (
        operation.status.value
        if hasattr(operation.status, "value")
        else str(operation.status)
    )
    operation.status = target_status

    last_event_id = await session.scalar(
        select(Event.event_id)
        .where(Event.operation_id == operation.operation_id)
        .order_by(Event.event_id.desc())
        .limit(1)
    )
    next_event_id = (last_event_id or 0) + 1

    session.add(
        Event(
            event_id=next_event_id,
            operation_id=operation.operation_id,
            type=data.result,
            from_status=from_status,
            to_status=data.result,
            message=data.message or f"Payment {data.result.lower()}",
        )
    )

    await session.commit()
