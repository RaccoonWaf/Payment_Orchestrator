import asyncio
import random

import httpx

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


class ProviderError(Exception):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class ProviderClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 10.0,
        max_attempts: int = 5,
        base_delay: float = 0.5,
        max_delay: float = 8.0,
    ):
        self.base_url = (base_url or settings.PROVIDER_URL).rstrip("/")
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay

    async def create_payment(
        self,
        *,
        operation_id: str,
        amount: str,
        currency: str,
    ) -> str:
        url = f"{self.base_url}/payments"
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": operation_id,
            "X-Correlation-ID": operation_id,
        }
        payload = {
            "operationId": operation_id,
            "amount": amount,
            "currency": currency,
        }

        last_error: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        url,
                        json=payload,
                        headers=headers
                        )
            except httpx.RequestError as e:
                last_error = ProviderError(str(e), retryable=True)
                logger.warning(
                    "provider_network_error",
                    operationId=operation_id,
                    attempt=attempt,
                    max_attempts=self.max_attempts,
                    error=str(e),
                )
            else:
                if response.status_code == 503:
                    last_error = ProviderError("provider unavailable", retryable=True)
                    logger.warning(
                        "provider_unavailable",
                        operationId=operation_id,
                        attempt=attempt,
                        max_attempts=self.max_attempts,
                        status_code=503,
                    )
                elif response.status_code not in (200, 202):
                    raise ProviderError(
                        f"provider returned {response.status_code}: {response.text}",
                        retryable=False,
                    )
                else:
                    data = response.json()
                    provider_payment_id = data.get("providerPaymentId")
                    if not provider_payment_id:
                        raise ProviderError(
                            "providerPaymentId missing in response"
                            )
                    logger.info(
                        "provider_accepted",
                        operationId=operation_id,
                        attempt=attempt,
                        providerPaymentId=provider_payment_id,
                    )
                    return provider_payment_id

            if attempt >= self.max_attempts:
                break

            delay = min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)
            delay = delay * (0.5 + random.random())
            await asyncio.sleep(delay)

        logger.error(
                    "provider_call_exhausted",
                    operationId=operation_id,
                    attempts=self.max_attempts,
                    error=str(last_error) if last_error else None,
                )
        raise last_error or ProviderError(
            "provider call failed",
            retryable=True
            )
