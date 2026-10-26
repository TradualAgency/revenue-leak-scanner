"""The finding-verifier (app/agents/verifier): grouping, the id allowlist, and that a
failing run never costs the report its euros. The Anthropic client is faked."""

import json
import uuid
from types import SimpleNamespace

import pytest

from app.agents.verifier.schemas import FindingVerdict, VerificationReport, VerificationSubmission
from app.agents.verifier.service import collect_verdicts, group_findings, run_verifier, verification_candidates
from app.config import settings
from app.full_audit.client_report import client_revenue_leak
from app.full_audit.schemas import FindingOut, FullAuditData, RevenueLeakReport

STORE = "https://store.nl"


def _finding(fid, priced=True, status="warning"):
    return FindingOut(
        finding_id=fid, owning_layer=1, metric=fid, status=status, priced=priced,
        monthly_low=100 if priced else None, monthly_high=300 if priced else None,
    )


def _audit(findings) -> FullAuditData:
    return FullAuditData(store_url=STORE, scan_level="outside-only", revenue_leak=RevenueLeakReport(findings=list(findings)))


def _verdict(fid, verdict="confirmed"):
    return {"finding_id": fid, "verdict": verdict, "evidence_nl": "fetch_page /", "reason_nl": "gezien"}


def _tool_use(name, args):
    return SimpleNamespace(type="tool_use", name=name, input=args, id=uuid.uuid4().hex)


def _response(*blocks, stop_reason="tool_use"):
    return SimpleNamespace(
        content=list(blocks), stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=100, output_tokens=50, cache_read_input_tokens=0, cache_creation_input_tokens=0),
    )


class GroupedFakeClient:
    """Groups run in parallel, so responses are scripted per group, keyed by the first
    finding id in the run's first message."""

    def __init__(self, scripts: dict[str, list]):
        self._scripts = {k: list(v) for k, v in scripts.items()}
        self.calls: list[dict] = []
        self.messages = self

    async def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        first = json.loads(kwargs["messages"][0]["content"])
        item = self._scripts[first["findings"][0]["finding_id"]].pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_only_priced_non_good_findings_are_checked_and_grouped_like_the_fix_agents():
    data = _audit([
        _finding("perf.lcp_mobile"), _finding("checkout.no_guest"), _finding("cro.social_proof", priced=False),
        _finding("cart.cross_sell", status="good"), _finding("shipping.cost_clarity"), _finding("unknown.thing"),
    ])
    groups = group_findings(verification_candidates(data))
    assert {k: [f.finding_id for f in v] for k, v in groups.items()} == {
        "speed_bloat": ["perf.lcp_mobile", "unknown.thing"],
        "checkout_schema": ["checkout.no_guest"],
        "cro_pdp": ["shipping.cost_clarity"],
    }


def test_collect_verdicts_drops_foreign_ids_keeps_first_and_fills_gaps():
    findings = [_finding("perf.lcp_mobile"), _finding("perf.cls_mobile")]
    sub = VerificationSubmission.model_validate({"verdicts": [
        _verdict("perf.lcp_mobile", "refuted"), _verdict("perf.lcp_mobile", "confirmed"), _verdict("checkout.no_guest", "refuted"),
    ]})
    verdicts = {v.finding_id: v.verdict for v in collect_verdicts(sub, findings)}
    assert verdicts == {"perf.lcp_mobile": "refuted", "perf.cls_mobile": "unverifiable"}


@pytest.mark.asyncio
async def test_run_verifier_retries_invalid_submission_and_never_sends_euros():
    data = _audit([_finding("perf.lcp_mobile")])
    client = GroupedFakeClient({"perf.lcp_mobile": [
        _response(_tool_use("submit_verification", {"verdicts": []})),  # min_length=1 -> tool error
        _response(_tool_use("submit_verification", {"verdicts": [_verdict("perf.lcp_mobile", "refuted")]})),
    ]})

    report = await run_verifier(data, client=client)

    assert report.verdict_map() == {"perf.lcp_mobile": "refuted"}
    assert report.errors == [] and (report.input_tokens, report.output_tokens) == (200, 100)
    assert client.calls[1]["messages"][-1]["content"][0]["is_error"] is True
    first = json.loads(client.calls[0]["messages"][0]["content"])
    assert "monthly_low" not in first["findings"][0] and "monthly_high" not in first["findings"][0]


@pytest.mark.asyncio
async def test_failed_group_gives_no_verdicts_and_other_groups_still_count():
    data = _audit([_finding("perf.lcp_mobile"), _finding("checkout.no_guest")])
    client = GroupedFakeClient({
        "perf.lcp_mobile": [_response(stop_reason="refusal")],
        "checkout.no_guest": [_response(_tool_use("submit_verification", {"verdicts": [_verdict("checkout.no_guest", "unverifiable")]}))],
    })

    report = await run_verifier(data, client=client)

    # The refused group's finding keeps its analyzer price: no verdict, just an error.
    assert report.verdict_map() == {"checkout.no_guest": "unverifiable"}
    assert len(report.errors) == 1 and report.errors[0].startswith("speed_bloat:")


@pytest.mark.asyncio
async def test_disabled_or_nothing_priced_returns_none(monkeypatch):
    client = GroupedFakeClient({})
    assert await run_verifier(_audit([_finding("perf.lcp_mobile", priced=False)]), client=client) is None
    monkeypatch.setattr(settings, "VERIFIER_ENABLED", False)
    assert await run_verifier(_audit([_finding("perf.lcp_mobile")]), client=client) is None
    assert client.calls == []


def test_verification_is_not_in_the_client_projection():
    leak = RevenueLeakReport(verification=VerificationReport(verdicts=[FindingVerdict(**_verdict("perf.lcp_mobile", "refuted"))]))
    assert "verification" not in client_revenue_leak(leak).model_dump(mode="json")


def test_admin_client_for_never_raises(monkeypatch):
    from app.agents.verifier.service import admin_client_for

    assert admin_client_for(None, None) is None
    monkeypatch.setattr(settings, "TOKEN_ENCRYPTION_KEY", "")
    assert admin_client_for("store.myshopify.com", "garbage") is None
    monkeypatch.setattr(settings, "TOKEN_ENCRYPTION_KEY", "not-a-fernet-key")
    assert admin_client_for("store.myshopify.com", "garbage") is None
