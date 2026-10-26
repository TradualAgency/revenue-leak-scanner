"""Fix agents: euros come from the registry, tools stay read-only and on the store's own
domain, and the Admin token is refused with write scopes and never leaves the backend."""

import uuid
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from app.config import settings
from app.fix_agents import router as fix_router
from app.fix_agents.agents import AGENTS
from app.fix_agents.models import FixAgentRun
from app.fix_agents.runtime import AgentError, attach_fix_impact, run_agent
from app.fix_agents.schemas import FixPackageSubmission
from app.fix_agents.shopify_admin import ShopifyAdminClient, decrypt_token, encrypt_token, write_scopes
from app.fix_agents.tools import NOT_AVAILABLE, ToolContext, execute_tool
from app.full_audit.models import FullAudit
from app.full_audit.schemas import FindingOut, FullAuditData, RevenueLeakReport

OPERATOR = {"X-Operator-Key": settings.OPERATOR_API_KEY}
STORE = "https://store.nl"


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    monkeypatch.setattr(settings, "TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _finding(fid, low=None, high=None):
    return FindingOut(finding_id=fid, owning_layer=1, metric=fid, monthly_low=low, monthly_high=high, priced=low is not None)


def _fix(ids, title="Fix"):
    return {
        "finding_ids": ids, "title_nl": title, "steps_nl": ["Doe iets"], "risk": "laag",
        "rollback_nl": "Theme terugzetten", "verification_checklist": ["PSI draaien"],
    }


def _audit(findings=()) -> FullAuditData:
    return FullAuditData(
        store_url=STORE, scan_level="outside-only",
        revenue_leak=RevenueLeakReport(findings=list(findings)),
    )


# --- euros and effort ----------------------------------------------------------------

def test_fix_euros_come_from_the_registry_and_a_finding_counts_once():
    findings = [_finding("perf.lcp_mobile", 1_040, 2_960), _finding("perf.inp_mobile", 500, 1_500), _finding("perf.cls_mobile")]
    sub = FixPackageSubmission(summary_nl="s", fixes=[
        _fix(["perf.lcp_mobile", "made.up_by_llm", "perf.inp_mobile"]),
        _fix(["perf.lcp_mobile", "perf.cls_mobile"]),
    ])

    first, second = attach_fix_impact(sub, findings)

    assert first.finding_ids == ["perf.lcp_mobile", "perf.inp_mobile"]
    assert (first.monthly_low, first.monthly_high) == (1_500, 4_500)
    # The biggest action in the fix sets the effort: speed.lcp (5-15d) over speed.inp.
    assert (first.effort, first.effort_days_high, first.owner) == ("M", 15, "developer")
    assert first.remeasure_after_days == 28
    assert second.finding_ids == ["perf.cls_mobile"]  # lcp already claimed
    assert second.priced is False and second.monthly_low is None


def test_llm_cannot_submit_euros_or_effort():
    sub = FixPackageSubmission.model_validate({"summary_nl": "s", "fixes": [{**_fix([]), "monthly_low": 99_999, "effort": "S"}]})
    (item,) = attach_fix_impact(sub, [])
    assert item.monthly_low is None and item.effort is None


# --- the agent loop ------------------------------------------------------------------

def _tool_use(name, args, id_=None):
    return SimpleNamespace(type="tool_use", name=name, input=args, id=id_ or uuid.uuid4().hex)


def _response(*blocks, stop_reason="tool_use"):
    return SimpleNamespace(
        content=list(blocks), stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=100, output_tokens=50, cache_read_input_tokens=0, cache_creation_input_tokens=0),
    )


class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.messages = self

    async def create(self, **kwargs):
        # Snapshot: the loop keeps appending to the same messages list.
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_agent_loop_runs_tools_retries_invalid_submissions_and_returns_the_package():
    findings = [_finding("perf.lcp_mobile", 1_000, 3_000), _finding("checkout.no_guest", 400, 900)]
    client = FakeClient([
        _response(_tool_use("get_audit_section", {"section": "performance"}), _tool_use("read_theme_file", {"filename": "layout/theme.liquid"})),
        _response(_tool_use("submit_fix_package", {"summary_nl": "s", "fixes": []})),  # min_length=1 -> error
        _response(_tool_use("submit_fix_package", {"summary_nl": "Sneller", "fixes": [_fix(["perf.lcp_mobile", "checkout.no_guest"])]})),
    ])

    result = await run_agent(client, AGENTS["speed_bloat"], ToolContext(audit=_audit(findings)), findings)

    (fix,) = result.package.fixes
    assert fix.finding_ids == ["perf.lcp_mobile"]  # checkout.* isn't this agent's finding
    assert result.package.used_admin_data is False
    assert result.package.warnings  # no token -> says so
    assert (result.input_tokens, result.output_tokens) == (300, 150)

    tool_results = client.calls[1]["messages"][-1]["content"]
    assert tool_results[0].get("is_error") is None
    assert tool_results[1] == {**tool_results[1], "is_error": True, "content": NOT_AVAILABLE}
    retry = client.calls[2]["messages"][-1]["content"][0]
    assert retry["is_error"] is True
    assert client.calls[0]["model"] == settings.FIX_AGENT_MODEL


@pytest.mark.asyncio
async def test_agent_that_never_submits_fails(monkeypatch):
    monkeypatch.setattr(settings, "FIX_AGENT_MAX_TURNS", 2)
    client = FakeClient([_response(_tool_use("get_audit_section", {"section": "performance"})) for _ in range(2)])
    with pytest.raises(AgentError):
        await run_agent(client, AGENTS["tracking"], ToolContext(audit=_audit()), [])
    # The second-to-last turn carries a "submit now" nudge.
    assert client.calls[1]["messages"][-1]["content"][-1]["type"] == "text"
    # The last turn forces the submit tool; earlier turns leave the choice to the model.
    assert "tool_choice" not in client.calls[0]
    assert client.calls[1]["tool_choice"] == {"type": "tool", "name": "submit_fix_package"}


@pytest.mark.asyncio
async def test_refusal_fails_the_run():
    client = FakeClient([_response(stop_reason="refusal")])
    with pytest.raises(AgentError):
        await run_agent(client, AGENTS["cro_pdp"], ToolContext(audit=_audit()), [])


# --- tools ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_page_refuses_other_domains():
    text, is_error = await execute_tool(ToolContext(audit=_audit()), "fetch_page", {"url": "https://evil.example/x", "mode": "html"})
    assert is_error and "store.nl" in text


@pytest.mark.asyncio
async def test_contact_details_and_sanity_export_are_not_readable():
    ctx = ToolContext(audit=_audit())
    for section in ("contact_email", "sanity_export"):
        _, is_error = await execute_tool(ctx, "get_audit_section", {"section": section})
        assert is_error


def test_token_crypto_roundtrip_and_write_scope_detection():
    enc = encrypt_token("shpat_secret")
    assert "shpat_secret" not in enc and decrypt_token(enc) == "shpat_secret"
    assert write_scopes(["read_themes", "write_products", "read_products"]) == ["write_products"]


# --- router --------------------------------------------------------------------------

@pytest.fixture
def stub_shopify(monkeypatch):
    scopes = {"value": ["read_themes", "read_products"]}

    async def verify(self):
        return "Store BV", scopes["value"]

    monkeypatch.setattr(ShopifyAdminClient, "verify", verify)
    return scopes


@pytest.fixture
def no_background_work(monkeypatch):
    async def noop(*args, **kwargs):
        return None
    monkeypatch.setattr(fix_router, "run_fix_agents", noop)


@pytest.mark.asyncio
async def test_endpoints_require_the_operator_key(client, ready_audit):
    assert (await client.get(f"/api/v1/full-audit/{ready_audit.id}/fix-agents")).status_code == 403
    resp = await client.put(f"/api/v1/full-audit/{ready_audit.id}/admin-token", json={"shop_domain": "x.myshopify.com", "access_token": "shpat_0123456789"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_token_with_write_scopes_is_refused(client, ready_audit, stub_shopify, db_session):
    stub_shopify["value"] = ["read_themes", "write_themes"]
    resp = await client.put(
        f"/api/v1/full-audit/{ready_audit.id}/admin-token",
        json={"shop_domain": "store.myshopify.com", "access_token": "shpat_0123456789"}, headers=OPERATOR,
    )
    assert resp.status_code == 422 and "write_themes" in resp.text
    await db_session.refresh(ready_audit)
    assert ready_audit.shopify_admin_token_enc is None


@pytest.mark.asyncio
async def test_read_only_token_is_stored_encrypted_and_never_returned(client, ready_audit, stub_shopify, db_session):
    secret = "shpat_supersecret_token"
    resp = await client.put(
        f"/api/v1/full-audit/{ready_audit.id}/admin-token",
        json={"shop_domain": "https://Store.myshopify.com/admin", "access_token": secret}, headers=OPERATOR,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["shopify_shop_domain"] == "store.myshopify.com"
    await db_session.refresh(ready_audit)
    assert secret not in ready_audit.shopify_admin_token_enc

    for path in ("fix-agents", "report", ""):
        r = await client.get(f"/api/v1/full-audit/{ready_audit.id}/{path}".rstrip("/"), headers=OPERATOR)
        assert secret not in r.text and ready_audit.shopify_admin_token_enc not in r.text
    assert (await client.get(f"/api/v1/full-audit/{ready_audit.id}/fix-agents", headers=OPERATOR)).json()["has_admin_token"] is True

    await client.delete(f"/api/v1/full-audit/{ready_audit.id}/admin-token", headers=OPERATOR)
    await db_session.refresh(ready_audit)
    assert ready_audit.shopify_admin_token_enc is None


@pytest.mark.asyncio
async def test_start_queues_one_run_per_agent(client, ready_audit, no_background_work):
    resp = await client.post(
        f"/api/v1/full-audit/{ready_audit.id}/fix-agents",
        json={"agents": ["speed_bloat", "tracking", "speed_bloat"]}, headers=OPERATOR,
    )
    assert resp.status_code == 202, resp.text
    assert sorted(r["agent"] for r in resp.json()["runs"]) == ["speed_bloat", "tracking"]
    assert all(r["status"] == "queued" for r in resp.json()["runs"])


@pytest.mark.asyncio
async def test_start_requires_a_finished_audit(client, db_session, no_background_work):
    audit = FullAudit(id=uuid.uuid4(), store_url=STORE, scan_level="outside-only", status="processing")
    db_session.add(audit)
    await db_session.commit()
    resp = await client.post(f"/api/v1/full-audit/{audit.id}/fix-agents", json={"agents": ["tracking"]}, headers=OPERATOR)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_fix_packages_never_reach_the_client_report(client, db_session, ready_audit):
    marker = "fix-canary-91c2"
    db_session.add(FixAgentRun(
        id=uuid.uuid4(), full_audit_id=ready_audit.id, agent="tracking", status="done",
        result={"agent": "tracking", "summary_nl": marker, "fixes": []},
    ))
    await db_session.commit()
    report = await client.get(f"/api/v1/full-audit/{ready_audit.id}/report")
    assert report.status_code == 200 and marker not in report.text


# --- manual verifier / funnel runs ----------------------------------------------------

@pytest.mark.asyncio
async def test_manual_runs_ignore_the_automatic_switch_but_not_a_missing_api_key(monkeypatch):
    from app.agents.funnel.service import walk_funnel
    from app.agents.verifier.service import run_verifier

    monkeypatch.setattr(settings, "VERIFIER_ENABLED", False)
    monkeypatch.setattr(settings, "FUNNEL_AGENT_ENABLED", False)
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    data = _audit([_finding("perf.lcp_mobile", 100, 300)])

    # Automatic (pipeline) runs respect the switch...
    assert await run_verifier(data, client=FakeClient([])) is None
    assert (await walk_funnel(uuid.uuid4(), STORE, [], client=FakeClient([]))).status == "skipped"
    # ...a manual start doesn't, but still needs credentials.
    assert await run_verifier(data, force=True) is None
    assert (await walk_funnel(uuid.uuid4(), STORE, [], force=True)).status == "skipped"
    client = FakeClient([_response(_tool_use("submit_verification", {"verdicts": [
        {"finding_id": "perf.lcp_mobile", "verdict": "confirmed", "evidence_nl": "e", "reason_nl": "r"},
    ]}))])
    report = await run_verifier(data, client=client, force=True)
    assert report.verdict_map() == {"perf.lcp_mobile": "confirmed"}


def test_run_request_accepts_all_six_agents():
    from app.fix_agents.schemas import FixAgentRunRequest

    req = FixAgentRunRequest(agents=["speed_bloat", "tracking", "cro_pdp", "checkout_schema", "verifier", "funnel"])
    assert len(req.agents) == 6
