from datetime import datetime, timezone
import logging

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.common.enums import OperationStatus
from app.models.event import Event
from app.models.operation import Operation
from app.services.provider_client import ProviderClient, ProviderError
from app.schemas.event import EventResponse
from app.schemas.operation import CreateOperationRequest, OperationResponse


logger = logging.getLogger(__name__)


async def recover_pending_operations() -> None:
    """
    При старте приложения находит все операции в статусе PROCESSING
    и пытается повторно отправить их провайдеру.

    Нужен после рестарта: намерение уже сохранено в БД, а HTTP-вызов
    мог не завершиться. Ошибка по одной операции не останавливает остальные.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Operation).where(Operation.status == OperationStatus.PROCESSING)
        )
        operations = result.scalars().all()

    logger.info("recovery: found %s PROCESSING operations", len(operations))

    for operation in operations:
        try:
            async with AsyncSessionLocal() as session:
                await send_to_provider(session, operation.operation_id)
        except Exception:
            logger.exception(
                "recovery failed operation_id=%s",
                operation.operation_id,
            )


class OperationConflictError(Exception):
    pass


class OperationNotFoundError(Exception):
    pass


async def send_to_provider(session: AsyncSession, operation_id: str) -> None:
    """
    Отправляет платёж внешнему провайдеру и при успехе сохраняет providerPaymentId.

    Вызывается после первого submit и из recovery. Не меняет статус на
    COMPLETED/REJECTED — финальный статус ставит только callback.

    Пропуски:
    - операция не найдена;
    - уже финальный статус;
    - статус не PROCESSING;
    - providerPaymentId уже заполнен.

    При сетевой ошибке/503 операция остаётся PROCESSING.
    """
    result = await session.execute(
        select(Operation)
        .where(Operation.operation_id == operation_id)
        .with_for_update()
    )
    operation = result.scalar_one_or_none()
    if operation is None:
        return

    if operation.status in (OperationStatus.COMPLETED, OperationStatus.REJECTED):
        return
    if operation.status != OperationStatus.PROCESSING:
        return
    if operation.provider_payment_id is not None:
        return

    client = ProviderClient()
    amount_str = f"{operation.amount:.2f}"

    try:
        provider_payment_id = await client.create_payment(
            operation_id=operation.operation_id,
            amount=amount_str,
            currency=operation.currency,
        )
    except ProviderError as e:
        logger.warning(
            "provider call failed operation_id=%s retryable=%s error=%s",
            operation_id,
            e.retryable,
            e,
        )
        return

    await session.refresh(operation)
    if operation.status in (OperationStatus.COMPLETED, OperationStatus.REJECTED):
        return

    if operation.provider_payment_id is None:
        operation.provider_payment_id = provider_payment_id
    elif operation.provider_payment_id != provider_payment_id:
        logger.warning(
            "providerPaymentId mismatch operation_id=%s existing=%s got=%s",
            operation_id,
            operation.provider_payment_id,
            provider_payment_id,
        )
        return

    await session.commit()


async def get_operation_events(
    session: AsyncSession,
    operation_id: str,
) -> list[EventResponse]:
    """
    Возвращает историю событий операции по возрастанию event_id.

    Если операции нет — OperationNotFoundError.
    """
    operation = await get_operation(session, operation_id)
    if operation is None:
        raise OperationNotFoundError(f"Operation {operation_id} not found")

    result = await session.execute(
        select(Event)
        .where(Event.operation_id == operation_id)
        .order_by(Event.event_id.asc())
    )
    events = result.scalars().all()

    return [
        EventResponse(
            eventId=e.event_id,
            type=e.type,
            fromStatus=e.from_status,
            toStatus=e.to_status,
            message=e.message,
            occurredAt=e.occurred_at,
        )
        for e in events
    ]


async def submit_operation(
    session: AsyncSession,
    operation_id: str,
) -> tuple[OperationResponse, int]:
    """
    Фиксирует намерение отправки платежа.

    Атомарно (с блокировкой строки FOR UPDATE):
    - если CREATED → переводит в PROCESSING, пишет событие, commit;
      возвращает (операция, 202);
    - если уже PROCESSING/COMPLETED/REJECTED → ничего не меняет;
      возвращает (текущее состояние, 200).

    Вызов провайдера здесь не выполняется — только сохранение намерения в БД.
    Если операции нет — OperationNotFoundError.
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
    """
    Преобразует ORM-модель Operation в схему ответа API (camelCase, amount строкой).
    """
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
    """
    Создаёт новую операцию в статусе CREATED и первое событие истории.

    Повторный operationId → OperationConflictError.
    Операция и событие сохраняются в одной транзакции.
    """
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
