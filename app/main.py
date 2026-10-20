import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.operations import router as operations_router
from app.api.receipts import router as receipts_router
from app.services.operation_service import recover_pending_operations
from app.logging_config import setup_logging, get_logger


setup_logging(json_logs=os.getenv("JSON_LOGS", "true").lower() == "true")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("app_starting")
    try:
        await recover_pending_operations()
    except Exception:
        logger.exception("recovery_failed")
    yield
    logger.info("app_stopping")


app = FastAPI(
    title="Payment Orchestrator",
    lifespan=lifespan
    )

app.include_router(health_router)
app.include_router(operations_router)
app.include_router(receipts_router)
