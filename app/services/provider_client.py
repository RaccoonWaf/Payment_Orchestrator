import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class ProviderClient:
    def __init__(self, base_url: str | None = None, timeout: float = 10.0):
        self.base_url = (base_url or settings.PROVIDER_URL).rstrip("/")
        self.timeout = timeout

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

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.RequestError as e:
            logger.warning(
                "provider network error operation_id=%s error=%s",
                operation_id,
                e,
            )
            raise ProviderError(str(e), retryable=True) from e

        if response.status_code == 503:
            raise ProviderError("provider unavailable", retryable=True)

        if response.status_code not in (200, 202):
            raise ProviderError(
                f"provider returned {response.status_code}: {response.text}",
                retryable=False,
            )

        data = response.json()
        provider_payment_id = data.get("providerPaymentId")
        if not provider_payment_id:
            raise ProviderError("providerPaymentId missing in response")

        return provider_payment_id
