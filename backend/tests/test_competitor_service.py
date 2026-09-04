"""Operator curation of a competitor set: what gets persisted, what gets measured, and
what the report tells the prospect about it afterwards.

These are the regressions behind the "manual competitors" work — every one of them was
a live bug where the operator UI and the measured set disagreed.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.competitor_benchmark import service
from app.competitor_benchmark.models import CompetitorBenchmarkRun, CompetitorSnapshot as SnapshotRow
from app.competitor_benchmark.schemas import CompetitorSnapshot
from app.full_audit.models import FullAudit
from tests.conftest import TestSessionLocal

pytestmark = pytest.mark.asyncio

STORE_URL = "https://store.nl"
STORE_DOMAIN = "store.nl"


@pytest_asyncio.fixture
async def run(db_session):
    """A finished run with three auto-discovered competitors."""
    audit = FullAudit(
        id=uuid.uuid4(), store_url=STORE_URL, scan_level="outside-only",
        status="ready_for_review",
        audit_data={"store_url": STORE_URL, "scan_level": "outside-only"},
    )
    db_session.add(audit)
    await db_session.flush()  # the run's FK needs the audit row to exist first

    kept = [{"domain": d, "discovery_source": "competitors_domain"} for d in ("a.nl", "b.nl", "c.nl")]
    row = CompetitorBenchmarkRun(
        id=uuid.uuid4(), full_audit_id=audit.id, store_domain=STORE_DOMAIN,
        location_code=2528, language_code="nl", market_source="tld", status="ready",
        measure_limit=8,
        selected_domains=["a.nl", "b.nl", "c.nl"],
        discovery_json={
            "market": {"location_code": 2528, "language_code": "nl", "source": "tld", "confidence": "high"},
            "kept": kept, "rejected": [],
        },
    )
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    return row


@pytest.fixture(autouse=True)
def no_real_measurement(monkeypatch):
    """`measure_all` is imported into service's namespace, so patch it there.

    Also redirects the background half at the test database: `measure_competitor_set`
    opens its own session via `AsyncSessionLocal` rather than taking one as an argument,
    so the `get_db` override in conftest doesn't reach it.
    """
    calls: list[list[str]] = []

    async def fake_measure_all(domains, *, probe_checkout=False):
        calls.append(list(domains))
        return [
            CompetitorSnapshot(domain=d, measure_status="ok", measured_at=datetime.now(UTC))
            for d in domains
        ]

    monkeypatch.setattr(service, "measure_all", fake_measure_all)
    monkeypatch.setattr(service, "AsyncSessionLocal", TestSessionLocal)
    return calls


async def test_added_domain_is_normalized_before_it_is_stored(db_session, run):
    plan = await service.plan_competitor_set_update(db_session, run, add=["https://Www.New.NL/"], remove=[])

    assert plan.accepted == ["new.nl"]
    assert run.selected_domains == ["a.nl", "b.nl", "c.nl", "new.nl"]
    # The audit trail must record the domain, not whatever the operator happened to paste.
    assert run.operator_added == ["new.nl"]


async def test_add_past_the_cap_reaches_neither_the_selection_nor_the_candidate_list(db_session, run):
    run.measure_limit = 3
    plan = await service.plan_competitor_set_update(db_session, run, add=["overflow.nl"], remove=[])

    assert plan.accepted == []
    assert plan.outcomes[0].code == "over_limit"
    assert "overflow.nl" not in run.selected_domains
    # The other half of the bug: a chip used to appear because the candidate entry was
    # written even when the cap dropped the domain.
    assert "overflow.nl" not in [c["domain"] for c in run.discovery_json["kept"]]


async def test_removed_competitor_leaves_kept_and_lands_in_rejected(db_session, run):
    await service.plan_competitor_set_update(db_session, run, add=[], remove=["b.nl"])

    assert run.selected_domains == ["a.nl", "c.nl"]
    assert "b.nl" not in [c["domain"] for c in run.discovery_json["kept"]]
    rejected = {c["domain"]: c["reason_code"] for c in run.discovery_json["rejected"]}
    assert rejected["b.nl"] == "operator_removed"


async def test_the_store_itself_cannot_be_added_to_its_own_market(db_session, run):
    plan = await service.plan_competitor_set_update(db_session, run, add=["https://store.nl"], remove=[])

    assert plan.accepted == []
    assert plan.outcomes[0].code == "self"
    assert STORE_DOMAIN not in run.selected_domains


async def test_rejected_only_request_leaves_the_run_untouched(db_session, run):
    before = list(run.selected_domains)
    plan = await service.plan_competitor_set_update(db_session, run, add=["not a domain"], remove=[])

    assert plan.changed is False
    assert run.status == "ready"  # no re-measure triggered by a typo
    assert run.selected_domains == before


async def test_adding_a_competitor_flags_the_report_as_curated(db_session, run, no_real_measurement):
    await service.plan_competitor_set_update(db_session, run, add=["new.nl"], remove=[])
    await service.measure_competitor_set(run.id, force_domains=["new.nl"])
    await db_session.refresh(run)

    data = run.benchmark_data
    # Previously only *removing* flipped this, so an injected competitor was presented
    # as part of an automatic market median.
    assert data["manually_curated"] is True
    assert "toegevoegd" in data["curation_note_nl"]


async def test_removal_and_addition_get_different_disclosure_wording(db_session, run, no_real_measurement):
    await service.plan_competitor_set_update(db_session, run, add=[], remove=["b.nl"])
    await service.measure_competitor_set(run.id)
    await db_session.refresh(run)

    assert "verwijderd" in run.benchmark_data["curation_note_nl"]


async def test_readding_a_failed_domain_remeasures_despite_the_negative_cache(
    db_session, run, no_real_measurement,
):
    # A failed measurement is negative-cached for 2 days. Without force_domains an
    # operator fixing a typo would silently get the cached failure back.
    db_session.add(SnapshotRow(
        id=uuid.uuid4(), domain="typo.nl", measure_status="unreachable",
        snapshot_json={"domain": "typo.nl", "measure_status": "unreachable",
                       "measured_at": datetime.now(UTC).isoformat()},
        measured_at=datetime.now(UTC), schema_version=1,
    ))
    await db_session.commit()

    await service.plan_competitor_set_update(db_session, run, add=["typo.nl"], remove=[])
    await service.measure_competitor_set(run.id, force_domains=["typo.nl"])

    assert any("typo.nl" in call for call in no_real_measurement)


async def test_www_cache_hit_is_reported_as_measured_not_unreachable(db_session, run, no_real_measurement):
    """The cache is keyed on the registrable domain, but the stored snapshot payload
    carries whatever name it was measured under. A legacy row written as `www.cached.nl`
    used to be looked up in the roster under `cached.nl`, miss, and tell the prospect a
    successfully measured competitor was unreachable."""
    db_session.add(SnapshotRow(
        id=uuid.uuid4(), domain="cached.nl", measure_status="ok",
        snapshot_json={"domain": "www.cached.nl", "measure_status": "ok",
                       "measured_at": datetime.now(UTC).isoformat()},
        measured_at=datetime.now(UTC), schema_version=1,
    ))
    await db_session.commit()

    run.selected_domains = ["www.cached.nl"]
    await db_session.commit()
    await service.measure_competitor_set(run.id)
    await db_session.refresh(run)

    roster = {e["domain"]: e["measure_status"] for e in run.benchmark_data["roster"]}
    assert roster == {"cached.nl": "ok"}
    assert no_real_measurement == []  # served from cache, not re-measured


async def test_duplicate_www_variant_is_not_counted_twice(db_session, run, no_real_measurement):
    plan = await service.plan_competitor_set_update(
        db_session, run, add=["www.a.nl"], remove=[],
    )

    assert plan.accepted == []
    assert plan.outcomes[0].code == "duplicate"
    assert run.selected_domains.count("a.nl") == 1
