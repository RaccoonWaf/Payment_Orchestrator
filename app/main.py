import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.operations import router as operations_router
from app.api.receipts import router as receipts_router
from app.services.operation_service import recover_pending_operations


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starting recovery of PROCESSING operations")
    try:
        await recover_pending_operations()
    except Exception:
        logger.exception("recovery on startup failed")
    yield


app = FastAPI(
    title="Payment Orchestrator",
    lifespan=lifespan
    )

app.include_router(health_router)
app.include_router(operations_router)
app.include_router(receipts_router)
