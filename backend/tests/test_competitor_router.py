import uuid

import pytest

from app.config import settings

pytestmark = pytest.mark.asyncio


async def test_create_without_operator_key_is_403(client):
    resp = await client.post("/api/v1/competitor-benchmark", json={"full_audit_id": str(uuid.uuid4())})
    assert resp.status_code == 403


async def test_create_with_wrong_operator_key_is_403(client):
    resp = await client.post(
        "/api/v1/competitor-benchmark",
        json={"full_audit_id": str(uuid.uuid4())},
        headers={"X-Operator-Key": "definitely-wrong"},
    )
    assert resp.status_code == 403


async def test_candidates_endpoint_requires_operator_key(client):
    resp = await client.get(f"/api/v1/competitor-benchmark/{uuid.uuid4()}/candidates")
    assert resp.status_code == 403


async def test_patch_competitors_requires_operator_key(client):
    resp = await client.patch(f"/api/v1/competitor-benchmark/{uuid.uuid4()}/competitors", json={"add": [], "remove": []})
    assert resp.status_code == 403


async def test_remeasure_requires_operator_key(client):
    resp = await client.post(f"/api/v1/competitor-benchmark/{uuid.uuid4()}/remeasure", json={"force": False})
    assert resp.status_code == 403


async def test_public_status_endpoint_is_not_operator_gated_but_404s_for_unknown_run(client):
    resp = await client.get(f"/api/v1/competitor-benchmark/{uuid.uuid4()}/status")
    assert resp.status_code == 404  # not 403 — this endpoint is public, just not found


async def test_public_get_endpoint_is_not_operator_gated_but_404s_for_unknown_run(client):
    resp = await client.get(f"/api/v1/competitor-benchmark/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_create_with_valid_operator_key_but_missing_audit_returns_404(client):
    assert settings.OPERATOR_API_KEY, "OPERATOR_API_KEY must be configured for this test to be meaningful"
    resp = await client.post(
        "/api/v1/competitor-benchmark",
        json={"full_audit_id": str(uuid.uuid4())},
        headers={"X-Operator-Key": settings.OPERATOR_API_KEY},
    )
    assert resp.status_code == 404
