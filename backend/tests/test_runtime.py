import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.config import settings
from backend.app.database import AsyncSessionLocal, engine, get_db
from backend.app.main import app
from backend.app.models import Agency, BudgetEntry, Delivery, PaymentAttempt, User
from backend.seed import seed
from fixture.app import app as fixture_app


def test_fixture_routes_serve_distinct_versions_and_baseline():
    with TestClient(fixture_app) as fixture:
        broken = fixture.get("/checkout-broken")
        corrected = fixture.get("/checkout-fixed")
        assert broken.status_code == corrected.status_code == 200
        assert broken.headers["content-type"].startswith("text/html")
        assert broken.text != corrected.text
        assert fixture.get("/api/cart-total").json()["total_cents"] == 4200


def test_health_and_empty_queue_start(client):
    assert client.get("/livez").json()["status"] == "ok"
    assert client.get("/readyz").json()["workflow"] == "unavailable"
    assert client.get("/api/v1/tasks").status_code == 401


def test_readiness_failure_is_503_and_redacts_database_error(client):
    class BrokenDatabase:
        async def execute(self, query):
            raise RuntimeError("sensitive connection credentials")

    async def broken_db():
        yield BrokenDatabase()

    app.dependency_overrides[get_db] = broken_db
    try:
        response = client.get("/readyz")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable", "database": "disconnected"}
        assert "sensitive" not in response.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("path", [
    "/api/v1/briefs",
    "/api/v1/mandates/approve",
    "/api/v1/deliveries/submit",
    "/api/v1/judge/reset",
    f"/api/v1/judge/replay-task/{uuid.uuid4()}",
])
def test_unfinished_mutations_require_authentication(client, path):
    response = client.post(path, json={})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


async def test_delivery_hold_creates_no_evidence_payment_or_budget(client):
    response = client.post("/api/v1/deliveries/submit", json={
        "task_id": str(uuid.uuid4()), "artifact_ref": "checkout_mobile_fixed",
        "claim": "Ready to pay",
    })
    assert response.status_code == 401
    async with AsyncSessionLocal() as session:
        for model in (Delivery, PaymentAttempt, BudgetEntry):
            assert await session.scalar(select(func.count()).select_from(model)) == 0
    await engine.dispose()


async def test_repeated_seed_preserves_balance_and_actor_ids(monkeypatch):
    agency_id = uuid.uuid4()
    monkeypatch.setattr(settings, "DEFAULT_AGENCY_ID", agency_id)
    monkeypatch.setattr(settings, "DEFAULT_ADVISORY_LOCK_KEY", agency_id.int % (2 ** 62))
    await seed()
    async with AsyncSessionLocal() as session:
        agency = await session.get(Agency, agency_id)
        agency.consumed_cents = 100
        await session.commit()
        actor_ids = set(await session.scalars(select(User.id).where(User.agency_id == agency_id)))
    await seed()
    async with AsyncSessionLocal() as session:
        assert (await session.get(Agency, agency_id)).consumed_cents == 100
        assert set(await session.scalars(select(User.id).where(User.agency_id == agency_id))) == actor_ids
    await engine.dispose()
