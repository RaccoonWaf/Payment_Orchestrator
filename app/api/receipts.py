from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.receipt import ReceiptRequest
from app.services.receipt_service import (
    ReceiptOperationNotFoundError,
    ReceiptProviderPaymentIdConflictError,
    process_receipt,
)

router = APIRouter(tags=["receipts"])


@router.post(
    "/receipts",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def post_receipt(
    body: ReceiptRequest,
    session: AsyncSession = Depends(get_session),
) -> None:
    try:
        await process_receipt(session, body)
    except ReceiptOperationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e
    except ReceiptProviderPaymentIdConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        ) from e
