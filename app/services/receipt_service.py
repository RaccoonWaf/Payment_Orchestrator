from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums import OperationStatus
from app.models.event import Event
from app.models.operation import Operation
from app.schemas.receipt import ReceiptRequest
from app.logging_config import get_logger


logger = get_logger(__name__)


class ReceiptOperationNotFoundError(Exception):
    """Операция для квитанции не найдена."""


class ReceiptProviderPaymentIdConflictError(Exception):
    """providerPaymentId в квитанции не совпадает с уже сохранённым."""


async def process_receipt(session: AsyncSession, data: ReceiptRequest) -> None:
    """
    Обрабатывает callback-квитанцию провайдера.

    В одной транзакции:
    - сверяет/сохраняет providerPaymentId;
    - при необходимости переводит в COMPLETED/REJECTED;
    - пишет Event.

    Повторная квитанция и противоположный результат после финала
    не создают новый переход.
    """
    result = await session.execute(
        select(Operation)
        .where(Operation.operation_id == data.operationId)
        .with_for_update()
    )
    operation = result.scalar_one_or_none()

    if operation is None:
        logger.warning(
            "receipt_operation_not_found",
            operationId=data.operationId,
            providerPaymentId=data.providerPaymentId,
            result=data.result,
        )
        raise ReceiptOperationNotFoundError(
            f"Operation {data.operationId} not found"
        )

    # Конфликт: у операции уже другой providerPaymentId
    if (
        operation.provider_payment_id is not None
        and operation.provider_payment_id != data.providerPaymentId
    ):
        logger.warning(
            "receipt_provider_payment_id_conflict",
            operationId=data.operationId,
            existing=operation.provider_payment_id,
            got=data.providerPaymentId,
            result=data.result,
        )
        raise ReceiptProviderPaymentIdConflictError(
            "providerPaymentId does not match operation"
        )

    # Ранний callback — id ещё не было
    if operation.provider_payment_id is None:
        operation.provider_payment_id = data.providerPaymentId
        logger.info(
            "receipt_provider_payment_id_set",
            operationId=data.operationId,
            providerPaymentId=data.providerPaymentId,
        )

    target_status = OperationStatus(data.result)

    # Уже финальный статус — идемпотентность / игнор противоположного результата
    if operation.status in (
        OperationStatus.COMPLETED,
        OperationStatus.REJECTED,
    ):
        logger.info(
            "receipt_ignored_already_final",
            operationId=data.operationId,
            status=str(
                operation.status.value
                if hasattr(operation.status, "value")
                else operation.status
            ),
            result=data.result,
            providerPaymentId=data.providerPaymentId,
        )
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

    logger.info(
        "receipt_processed",
        operationId=data.operationId,
        providerPaymentId=data.providerPaymentId,
        result=data.result,
        fromStatus=from_status,
        toStatus=data.result,
    )
