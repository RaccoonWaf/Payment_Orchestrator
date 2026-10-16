import uuid

import pytest


def _payload(op_id: str) -> dict:
    return {
        "operationId": op_id,
        "amount": "25.00",
        "currency": "RUB",
        "description": "submit test",
    }


@pytest.fixture
def mock_provider(monkeypatch):
    async def fake_create_payment(self, *, operation_id, amount, currency):
        return str(uuid.uuid4())

    monkeypatch.setattr(
        "app.services.provider_client.ProviderClient.create_payment",
        fake_create_payment,
    )


@pytest.mark.asyncio
async def test_submit_first_returns_202(client, mock_provider):
    op_id = f"test-{uuid.uuid4()}"
    await client.post("/operations", json=_payload(op_id))

    r = await client.post(f"/operations/{op_id}/submit")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "PROCESSING"


@pytest.mark.asyncio
async def test_submit_second_returns_200(client, mock_provider):
    op_id = f"test-{uuid.uuid4()}"
    await client.post("/operations", json=_payload(op_id))

    r1 = await client.post(f"/operations/{op_id}/submit")
    r2 = await client.post(f"/operations/{op_id}/submit")

    assert r1.status_code == 202
    assert r2.status_code == 200
    assert r2.json()["status"] == "PROCESSING"


@pytest.mark.asyncio
async def test_submit_missing_operation_404(client):
    r = await client.post("/operations/no-such-op/submit")
    assert r.status_code == 404