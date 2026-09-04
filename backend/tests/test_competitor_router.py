import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.competitor_benchmark import router as competitor_router
from app.competitor_benchmark.models import CompetitorBenchmarkRun
from app.config import settings

pytestmark = pytest.mark.asyncio

OPERATOR = {"X-Operator-Key": settings.OPERATOR_API_KEY}


@pytest.fixture(autouse=True)
def no_background_work(monkeypatch):
    """The endpoints enqueue BackgroundTasks that httpx's ASGI transport really does
    run. Stub both so no test reaches DataForSEO or a live scrape."""
    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(competitor_router, "run_competitor_benchmark", noop)
    monkeypatch.setattr(competitor_router, "measure_competitor_set", noop)


async def _run_count_for(db_session, audit_id) -> int:
    return (await db_session.execute(
        select(func.count()).select_from(CompetitorBenchmarkRun).where(
            CompetitorBenchmarkRun.full_audit_id == audit_id
        )
    )).scalar_one()


@pytest_asyncio.fixture
async def ready_run(db_session, ready_audit):
    run = CompetitorBenchmarkRun(
        id=uuid.uuid4(), full_audit_id=ready_audit.id, store_domain="store.nl",
        location_code=2528, language_code="nl", market_source="tld", status="ready",
        measure_limit=8, selected_domains=["a.nl"],
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


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


# --- manual competitor seeding + curation -------------------------------------------


async def test_create_reports_per_domain_outcomes_for_seeds(client, db_session, ready_audit):
    resp = await client.post(
        "/api/v1/competitor-benchmark",
        json={"full_audit_id": str(ready_audit.id), "seed_domains": ["https://a.nl", "a.nl", "junk"]},
        headers=OPERATOR,
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["seed_domains"] == ["a.nl"]
    assert [o["code"] for o in body["outcomes"]] == ["normalized", "duplicate", "invalid"]

    run = (await db_session.execute(
        CompetitorBenchmarkRun.__table__.select().where(
            CompetitorBenchmarkRun.full_audit_id == ready_audit.id
        )
    )).first()
    assert run.seed_domains == ["a.nl"]
    # store_domain is set at creation now, so a discovery failure can't leave it blank.
    assert run.store_domain == "store.nl"


async def test_create_clamps_max_competitors_to_the_ceiling(client, db_session, ready_audit):
    resp = await client.post(
        "/api/v1/competitor-benchmark",
        json={"full_audit_id": str(ready_audit.id), "max_competitors": 50},
        headers=OPERATOR,
    )

    assert resp.status_code == 201
    run = (await db_session.execute(
        CompetitorBenchmarkRun.__table__.select().where(
            CompetitorBenchmarkRun.full_audit_id == ready_audit.id
        )
    )).first()
    assert run.measure_limit == settings.COMPETITOR_MEASURE_LIMIT


async def test_patch_returns_outcomes_instead_of_an_opaque_200(client, ready_run):
    resp = await client.patch(
        f"/api/v1/competitor-benchmark/{ready_run.id}/competitors",
        json={"add": ["https://New.NL/"], "remove": []},
        headers=OPERATOR,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["selected_domains"] == ["a.nl", "new.nl"]
    assert body["outcomes"][0]["domain"] == "new.nl"
    # The copy must promise a decision, not a measurement.
    assert "meting gestart" in body["outcomes"][0]["message_nl"]


async def test_patch_with_only_invalid_input_does_not_trigger_a_remeasure(client, db_session, ready_run):
    resp = await client.patch(
        f"/api/v1/competitor-benchmark/{ready_run.id}/competitors",
        json={"add": ["not a domain"], "remove": []},
        headers=OPERATOR,
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"  # a typo shouldn't cost a full re-measure
    await db_session.refresh(ready_run)
    assert ready_run.status == "ready"


async def test_patch_on_a_running_benchmark_is_409(client, db_session, ready_run):
    ready_run.status = "measuring"
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/competitor-benchmark/{ready_run.id}/competitors",
        json={"add": ["new.nl"], "remove": []},
        headers=OPERATOR,
    )
    assert resp.status_code == 409


async def test_candidates_is_200_without_discovery_so_the_manual_path_stays_reachable(client, ready_run):
    assert ready_run.discovery_json is None

    resp = await client.get(
        f"/api/v1/competitor-benchmark/{ready_run.id}/candidates", headers=OPERATOR,
    )

    assert resp.status_code == 200  # used to 404, which hid the whole operator panel
    body = resp.json()
    assert body["discovery_available"] is False
    assert body["selected_domains"] == ["a.nl"]
    assert body["measure_limit"] == 8


async def test_candidates_still_404s_for_an_unknown_run(client):
    resp = await client.get(
        f"/api/v1/competitor-benchmark/{uuid.uuid4()}/candidates", headers=OPERATOR,
    )
    assert resp.status_code == 404


# --- finding runs back, and not paying for them twice --------------------------------


async def test_runs_list_requires_operator_key(client):
    resp = await client.get("/api/v1/competitor-benchmark", params={"full_audit_id": str(uuid.uuid4())})
    assert resp.status_code == 403


async def test_runs_list_returns_every_run_newest_first_without_the_jsonb_blobs(
    client, db_session, ready_audit,
):
    older = CompetitorBenchmarkRun(
        id=uuid.uuid4(), full_audit_id=ready_audit.id, store_domain="store.nl",
        location_code=2528, language_code="nl", status="ready",
        created_at=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
        benchmark_data={"store_domain": "store.nl", "roster": [{"domain": "a.nl"}]},
        discovery_json={"kept": [{"domain": "a.nl"}]},
    )
    newer = CompetitorBenchmarkRun(
        id=uuid.uuid4(), full_audit_id=ready_audit.id, store_domain="store.nl",
        location_code=2528, language_code="nl", status="measuring",
        created_at=datetime(2026, 9, 3, 10, 0, tzinfo=UTC),
    )
    db_session.add_all([older, newer])
    await db_session.commit()

    resp = await client.get(
        "/api/v1/competitor-benchmark", params={"full_audit_id": str(ready_audit.id)}, headers=OPERATOR,
    )

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["id"] for i in items] == [str(newer.id), str(older.id)]
    assert set(items[0]) == {"id", "status", "store_domain", "created_at", "completed_at"}
    assert "benchmark_data" not in resp.text and "discovery_json" not in resp.text


async def test_create_hands_back_the_running_run_instead_of_paying_for_a_second(
    client, db_session, ready_audit,
):
    first = await client.post(
        "/api/v1/competitor-benchmark",
        json={"full_audit_id": str(ready_audit.id), "seed_domains": ["a.nl"]},
        headers=OPERATOR,
    )
    assert first.status_code == 201
    assert first.json()["reused"] is False

    second = await client.post(
        "/api/v1/competitor-benchmark",
        json={"full_audit_id": str(ready_audit.id)},
        headers=OPERATOR,
    )

    assert second.status_code == 200  # not 201, and not 409
    assert second.json()["reused"] is True
    assert second.json()["id"] == first.json()["id"]
    # The seed outcomes come from the run that actually exists, not from this request.
    assert second.json()["seed_domains"] == ["a.nl"]
    # The whole point: no second DataForSEO discovery was enqueued, and no second row.
    assert await _run_count_for(db_session, ready_audit.id) == 1


async def test_create_reuses_a_finished_run_too(client, db_session, ready_audit, ready_run):
    assert ready_run.status == "ready"

    resp = await client.post(
        "/api/v1/competitor-benchmark", json={"full_audit_id": str(ready_audit.id)}, headers=OPERATOR,
    )

    # Deliberate re-measurement is POST /{run_id}/remeasure, which reuses this row.
    assert resp.status_code == 200
    assert resp.json()["reused"] is True
    assert resp.json()["id"] == str(ready_run.id)
    assert await _run_count_for(db_session, ready_audit.id) == 1


async def test_allow_duplicate_is_the_escape_hatch_from_the_reuse_guard(
    client, db_session, ready_audit, ready_run,
):
    resp = await client.post(
        "/api/v1/competitor-benchmark",
        json={"full_audit_id": str(ready_audit.id), "allow_duplicate": True},
        headers=OPERATOR,
    )

    assert resp.status_code == 201
    assert resp.json()["reused"] is False
    assert resp.json()["id"] != str(ready_run.id)
    assert await _run_count_for(db_session, ready_audit.id) == 2


async def test_reuse_picks_the_newest_run_when_several_exist(client, db_session, ready_audit):
    base = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
    runs = [
        CompetitorBenchmarkRun(
            id=uuid.uuid4(), full_audit_id=ready_audit.id, store_domain="store.nl",
            location_code=2528, language_code="nl", status="ready",
            created_at=base + timedelta(hours=offset),
        )
        for offset in (0, 2, 1)
    ]
    db_session.add_all(runs)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/competitor-benchmark", json={"full_audit_id": str(ready_audit.id)}, headers=OPERATOR,
    )

    assert resp.status_code == 200
    assert resp.json()["id"] == str(runs[1].id)  # base + 2h
    assert await _run_count_for(db_session, ready_audit.id) == 3
