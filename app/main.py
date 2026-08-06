from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.operations import router as operations_router
from app.api.receipts import router as receipts_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown


app = FastAPI(
    title="Payment Orchestrator",
    lifespan=lifespan
    )

app.include_router(health_router)
app.include_router(operations_router)
app.include_router(receipts_router)
