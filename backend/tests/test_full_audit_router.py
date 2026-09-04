"""The operator scan list: what it must show, and what it must never ship.

Rows are created straight through `db_session` rather than through the API, so nothing
here needs a background-task stub — except the two tests that exercise `POST` itself.

Every list assertion is scoped with `q`. The test database is created once per session
and never truncated between tests, so the table also holds whatever the competitor
router tests committed; an unscoped `total` would be a moving target.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from app.config import settings
from app.full_audit import router as full_audit_router
from app.full_audit.models import FullAudit

pytestmark = pytest.mark.asyncio

OPERATOR = {"X-Operator-Key": settings.OPERATOR_API_KEY}


async def _add_audit(db_session, **kwargs) -> FullAudit:
    audit = FullAudit(
        id=kwargs.pop("id", uuid.uuid4()),
        store_url=kwargs.pop("store_url", f"https://{uuid.uuid4().hex}.example"),
        scan_level=kwargs.pop("scan_level", "outside-only"),
        status=kwargs.pop("status", "ready_for_review"),
        **kwargs,
    )
    db_session.add(audit)
    await db_session.commit()
    return audit


async def _list(client, **params) -> dict:
    resp = await client.get("/api/v1/full-audit", params=params, headers=OPERATOR)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_list_without_an_operator_key_is_403(client):
    resp = await client.get("/api/v1/full-audit")
    assert resp.status_code == 403


async def test_list_with_a_wrong_operator_key_is_403(client):
    resp = await client.get("/api/v1/full-audit", headers={"X-Operator-Key": "definitely-wrong"})
    assert resp.status_code == 403


async def test_list_never_ships_the_three_jsonb_columns(client, db_session):
    """The regression this endpoint exists to avoid.

    `full_audits` has three JSONB columns and `audit_data` is the complete audit
    payload. If someone ever "simplifies" the query to `select(FullAudit)`, this is
    what catches it — so the seeded payload has to be non-trivial enough that a leak
    would be visible.
    """
    marker = "leak-canary-a7f31c"
    token = f"blobscan-{uuid.uuid4().hex[:8]}"
    audit = await _add_audit(
        db_session,
        store_url=f"https://{token}.example",
        company_name="Blob Scan BV",
        audit_data={
            "store_url": f"https://{token}.example",
            "scan_level": "full-access",
            "performance": {"mobile_cwv": {"lcp_ms": 4200.0, "note": marker}},
            "third_party": {"scripts": [{"name": marker, "kb": 180} for _ in range(40)]},
        },
        seranking_traffic_json={"organic": {"traffic": 12000, "note": marker}},
        competitor_benchmark_json={"competitors": [{"domain": f"{marker}.nl"}]},
    )

    resp = await client.get("/api/v1/full-audit", params={"q": token}, headers=OPERATOR)

    assert resp.status_code == 200
    body = resp.json()
    assert [i["id"] for i in body["items"]] == [str(audit.id)]
    assert marker not in resp.text
    for column in ("audit_data", "seranking_traffic_json", "competitor_benchmark_json"):
        assert column not in resp.text
    assert set(body["items"][0]) == {
        "id", "store_url", "company_name", "industry", "scan_level", "status",
        "created_at", "completed_at", "latest_benchmark", "benchmark_run_count",
    }


async def test_an_audit_with_two_runs_reports_the_newest_and_the_count(
    client, db_session, two_run_audit,
):
    """The barts.eu case: one audit, two paid runs, because the page lost the run id."""
    audit, older, newer = two_run_audit

    body = await _list(client, q=audit.store_url)

    assert [i["id"] for i in body["items"]] == [str(audit.id)]
    item = body["items"][0]
    assert item["benchmark_run_count"] == 2
    assert item["latest_benchmark"]["id"] == str(newer.id)
    assert item["latest_benchmark"]["status"] == "measuring"
    assert item["latest_benchmark"]["id"] != str(older.id)
    # The summary is a summary — no run payload rides along here either.
    assert set(item["latest_benchmark"]) == {
        "id", "status", "store_domain", "created_at", "completed_at",
    }


async def test_runs_written_in_one_transaction_still_resolve_deterministically(
    client, db_session,
):
    """`created_at` defaults to `transaction_timestamp()`, so rows committed together
    are genuinely tied. `id DESC` is what makes "the newest" a fact rather than a
    planner detail."""
    from app.competitor_benchmark.models import CompetitorBenchmarkRun

    token = f"tiebreak-{uuid.uuid4().hex[:8]}"
    audit = await _add_audit(db_session, store_url=f"https://{token}.example")
    tied_at = datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
    runs = [
        CompetitorBenchmarkRun(
            id=uuid.uuid4(), full_audit_id=audit.id, store_domain=f"{token}.example",
            location_code=2528, language_code="nl", status="ready", created_at=tied_at,
        )
        for _ in range(3)
    ]
    db_session.add_all(runs)
    await db_session.commit()

    body = await _list(client, q=token)

    item = body["items"][0]
    assert item["benchmark_run_count"] == 3
    assert item["latest_benchmark"]["id"] == str(max(r.id for r in runs))


async def test_an_audit_without_a_run_has_no_latest_benchmark(client, db_session):
    token = f"norun-{uuid.uuid4().hex[:8]}"
    await _add_audit(db_session, store_url=f"https://{token}.example")

    body = await _list(client, q=token)

    assert body["items"][0]["latest_benchmark"] is None
    assert body["items"][0]["benchmark_run_count"] == 0


async def test_search_matches_both_store_url_and_company_name(client, db_session):
    token = f"bothfields{uuid.uuid4().hex[:8]}"
    by_url = await _add_audit(
        db_session, store_url=f"https://{token}.example", company_name="Onvindbaar BV",
    )
    by_name = await _add_audit(
        db_session, store_url=f"https://{uuid.uuid4().hex}.example",
        company_name=f"{token.upper()} Handelsmaatschappij",
    )

    body = await _list(client, q=token)

    assert body["total"] == 2  # and case-insensitively, note the .upper() above
    assert {i["id"] for i in body["items"]} == {str(by_url.id), str(by_name.id)}


async def test_a_percent_in_the_query_is_a_literal_and_not_a_wildcard(client, db_session):
    token = f"pctesc{uuid.uuid4().hex[:8]}"
    literal = await _add_audit(
        db_session, store_url=f"https://{token}-a.example", company_name=f"Vijftig% {token}",
    )
    await _add_audit(
        db_session, store_url=f"https://{token}-b.example", company_name=f"Vijftig Procent {token}",
    )

    body = await _list(client, q=f"Vijftig% {token}")

    # Unescaped, `%` would make this match both rows.
    assert [i["id"] for i in body["items"]] == [str(literal.id)]
    assert body["total"] == 1


async def test_an_underscore_in_the_query_is_a_literal_too(client, db_session):
    token = f"uscesc{uuid.uuid4().hex[:8]}"
    literal = await _add_audit(db_session, store_url=f"https://a_b-{token}.example")
    await _add_audit(db_session, store_url=f"https://axb-{token}.example")

    body = await _list(client, q=f"a_b-{token}")

    assert [i["id"] for i in body["items"]] == [str(literal.id)]


async def test_limit_and_offset_page_the_list_while_total_reflects_the_filter(client, db_session):
    token = f"paging{uuid.uuid4().hex[:8]}"
    base = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    audits = [
        await _add_audit(
            db_session, store_url=f"https://{token}-{n}.example", created_at=base + timedelta(hours=n),
        )
        for n in range(3)
    ]
    newest_first = [str(a.id) for a in reversed(audits)]

    first_page = await _list(client, q=token, limit=2, offset=0)
    second_page = await _list(client, q=token, limit=2, offset=2)

    assert [i["id"] for i in first_page["items"]] == newest_first[:2]
    assert [i["id"] for i in second_page["items"]] == newest_first[2:]
    # `total` counts everything the filter matches, not what this page returned.
    assert first_page["total"] == second_page["total"] == 3
    assert (first_page["limit"], first_page["offset"]) == (2, 0)
    assert (second_page["limit"], second_page["offset"]) == (2, 2)


async def test_limit_is_bounded(client):
    assert (await client.get("/api/v1/full-audit", params={"limit": 0}, headers=OPERATOR)).status_code == 422
    assert (await client.get("/api/v1/full-audit", params={"limit": 201}, headers=OPERATOR)).status_code == 422
    assert (await client.get("/api/v1/full-audit", params={"offset": -1}, headers=OPERATOR)).status_code == 422


# --- POST is operator-only now --------------------------------------------------------


async def test_create_without_an_operator_key_is_403(client):
    """`/full-audit` is a public page with a public form, and every audit spends
    PageSpeed, Anthropic, SE Ranking and DataForSEO budget."""
    resp = await client.post("/api/v1/full-audit", json={"store_url": "https://example.com"})
    assert resp.status_code == 403


async def test_create_with_the_operator_key_still_works(client, db_session, monkeypatch):
    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(full_audit_router, "run_full_audit", noop)

    resp = await client.post(
        "/api/v1/full-audit",
        json={"store_url": "https://gated-but-working.example", "company_name": "Gate Test BV"},
        headers=OPERATOR,
    )

    assert resp.status_code == 201
    assert resp.json()["status"] == "queued"


@pytest_asyncio.fixture
async def two_run_audit(db_session):
    from app.competitor_benchmark.models import CompetitorBenchmarkRun

    token = f"tworuns-{uuid.uuid4().hex[:8]}"
    audit = await _add_audit(
        db_session, store_url=f"https://{token}.example", company_name="Twee Runs BV",
    )
    # Explicit timestamps: within one transaction `func.now()` is constant, so relying
    # on insertion order here would make the assertion below meaningless.
    older = CompetitorBenchmarkRun(
        id=uuid.uuid4(), full_audit_id=audit.id, store_domain=f"{token}.example",
        location_code=2528, language_code="nl", status="ready",
        created_at=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
        completed_at=datetime(2026, 9, 1, 10, 30, tzinfo=UTC),
        benchmark_data={"store_domain": f"{token}.example", "roster": [{"domain": "a.nl"}]},
    )
    newer = CompetitorBenchmarkRun(
        id=uuid.uuid4(), full_audit_id=audit.id, store_domain=f"{token}.example",
        location_code=2528, language_code="nl", status="measuring",
        created_at=datetime(2026, 9, 3, 10, 0, tzinfo=UTC),
    )
    db_session.add_all([older, newer])
    await db_session.commit()
    return audit, older, newer
