from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.operation import CreateOperationRequest, OperationResponse
from app.services.operation_service import (
    OperationConflictError,
    create_operation,
    get_operation,
    to_operation_response,
)

router = APIRouter(tags=["operations"])


@router.post(
    "/operations",
    response_model=OperationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_operations(
    body: CreateOperationRequest,
    session: AsyncSession = Depends(get_session),
) -> OperationResponse:
    try:
        return await create_operation(session, body)
    except OperationConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e


@router.get(
    "/operations/{operation_id}",
    response_model=OperationResponse,
)
async def get_operation_by_id(
    operation_id: str,
    session: AsyncSession = Depends(get_session),
) -> OperationResponse:
    operation = await get_operation(session, operation_id)
    if operation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Operation not found",
        )
    return to_operation_response(operation)
