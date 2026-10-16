import uuid

import pytest


def _payload(op_id: str) -> dict:
    return {
        "operationId": op_id,
        "amount": "10.00",
        "currency": "RUB",
        "description": "pytest",
    }


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_create_operation(client):
    op_id = f"test-{uuid.uuid4()}"
    r = await client.post("/operations", json=_payload(op_id))
    assert r.status_code == 201
    body = r.json()
    assert body["operationId"] == op_id
    assert body["status"] == "CREATED"
    assert body["providerPaymentId"] is None


@pytest.mark.asyncio
async def test_create_duplicate_409(client):
    op_id = f"test-{uuid.uuid4()}"
    payload = _payload(op_id)
    assert (await client.post("/operations", json=payload)).status_code == 201
    r2 = await client.post("/operations", json=payload)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_get_operation(client):
    op_id = f"test-{uuid.uuid4()}"
    await client.post("/operations", json=_payload(op_id))
    r = await client.get(f"/operations/{op_id}")
    assert r.status_code == 200
    assert r.json()["operationId"] == op_id


@pytest.mark.asyncio
async def test_get_missing_404(client):
    r = await client.get("/operations/no-such-op")
    assert r.status_code == 404