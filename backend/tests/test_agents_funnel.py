"""The funnel agent (app/agents/funnel): the request guard, how a submission becomes a
walk, how issues are priced, and what the client sees. No browser or API is started."""

import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.agents.funnel.browser import is_checkout_url, is_request_allowed
from app.agents.funnel.schemas import FunnelIssue, FunnelStep, FunnelWalk, FunnelWalkSubmission
from app.agents.funnel.service import build_walk, walk_funnel
from app.agents.runtime import run_tool_loop, submit_definition
from app.agents.verifier.service import verification_candidates
from app.config import settings
from app.full_audit.analyzers.revenue_leak import calculate_revenue_leak
from app.full_audit.client_report import client_funnel_walk
from app.full_audit.schemas import FindingOut, FullAuditData, Performance, RevenueLeakReport, ShippingHealth

STORE = {"store.nl"}


# --- request guard -------------------------------------------------------------------

@pytest.mark.parametrize("method,url,allowed", [
    ("GET", "https://store.nl/products/x", True),
    ("GET", "https://cdn.shopify.com/s/files/x.js", True),
    ("GET", "https://widget.trustpilot.com/x.js", True),  # third-party UI must load
    ("POST", "https://store.nl/cart/add.js", True),
    ("POST", "https://store.nl/nl-be/cart/change.js", True),
    ("POST", "https://store.nl/api/2025-10/graphql.json", True),  # headless cart
    ("POST", "https://store.nl/checkouts/cn/abc", False),
    ("POST", "https://store.nl/contact", False),
    ("POST", "https://store.nl/account/login", False),
    ("POST", "https://evil.example/cart/add.js", False),
    ("PUT", "https://store.nl/cart/add.js", False),
    ("GET", "https://connect.facebook.net/en_US/fbevents.js", False),
    ("POST", "https://www.facebook.com/tr", False),
    ("GET", "https://www.google-analytics.com/g/collect?x=1", False),
    ("POST", "https://store.nl/.well-known/shopify/monorail/unstable/produce_batch", False),
])
def test_request_guard(method, url, allowed):
    assert is_request_allowed(method, url, STORE) is allowed


def test_checkout_urls_are_recognised():
    assert is_checkout_url("https://store.nl/checkouts/cn/abc/information")
    assert is_checkout_url("https://store.nl/checkout")
    assert not is_checkout_url("https://store.nl/products/checkout-mat")


# --- submission -> walk --------------------------------------------------------------

def _issue(key="atc_blocked_by_overlay", step="add_to_cart", shot=None):
    return {"issue_key": key, "step": step, "description_nl": "Popup over de knop", "evidence_nl": "click gaf intercepts", "screenshot_id": shot}


def _submission(issues=(), blocked=False):
    return FunnelWalkSubmission.model_validate({
        "blocked": blocked, "steps": [{"step": "home", "reached": True}], "issues": list(issues), "summary_nl": "s",
    })


def test_unknown_issue_key_is_rejected():
    with pytest.raises(ValidationError):
        _submission([_issue(key="made_up")])


def test_blocked_walk_carries_no_issues():
    status, issues, warnings = build_walk(_submission([_issue()], blocked=True), set())
    assert status == "blocked" and issues == [] and warnings


def test_screenshot_reference_must_exist_in_the_session():
    status, issues, warnings = build_walk(
        _submission([_issue(shot="real"), _issue(shot="invented")]), {"real"}, {"intercepted_click"},
    )
    assert status == "ok"
    assert [i.screenshot_id for i in issues] == ["real", None] and len(warnings) == 1


def test_priced_keys_need_the_fact_the_browser_recorded():
    sub = _submission([_issue(), _issue(key="checkout_unreachable", step="checkout"), _issue(key="search_no_results", step="search")])

    _, issues, warnings = build_walk(sub, set(), {"intercepted_click"})

    confirmed = {i.issue_key: i.machine_confirmed for i in issues}
    assert confirmed == {"atc_blocked_by_overlay": True, "checkout_unreachable": False, "search_no_results": False}
    assert any("checkout_unreachable" in w for w in warnings)


@pytest.mark.asyncio
async def test_disabled_walk_is_skipped_without_a_browser(monkeypatch):
    monkeypatch.setattr(settings, "FUNNEL_AGENT_ENABLED", False)
    walk = await walk_funnel(uuid.uuid4(), "https://store.nl", [], client=object())
    assert walk.status == "skipped"


@pytest.mark.asyncio
async def test_tool_loop_passes_image_blocks_back_to_the_model():
    image_result = [{"type": "text", "text": "{}"}, {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAAA"}}]

    async def executor(ctx, name, args):
        return image_result, False

    def tool_use(name, args):
        return SimpleNamespace(type="tool_use", name=name, input=args, id=uuid.uuid4().hex)

    usage = SimpleNamespace(input_tokens=1, output_tokens=1, cache_read_input_tokens=0, cache_creation_input_tokens=0)
    responses = [
        SimpleNamespace(content=[tool_use("screenshot", {"caption": "x"})], stop_reason="tool_use", usage=usage),
        SimpleNamespace(content=[tool_use("submit_funnel_walk", _submission().model_dump())], stop_reason="tool_use", usage=usage),
    ]
    calls = []

    class Client:
        messages = None

        async def create(self, **kwargs):
            calls.append(list(kwargs["messages"]))
            return responses.pop(0)

    client = Client()
    client.messages = client
    loop = await run_tool_loop(
        client, model="m", system="s", tools=[], first_message="go", ctx=None, max_turns=3, executor=executor,
        submit_tool=submit_definition("submit_funnel_walk", "d", FunnelWalkSubmission), submission_model=FunnelWalkSubmission,
    )
    assert loop.submission.summary_nl == "s"
    assert calls[1][-1]["content"][0]["content"] == image_result


# --- pricing -------------------------------------------------------------------------

_KW = dict(annual_revenue_eur=2_400_000, aov_override=80.0, sessions_override=50_000, cr_override_pct=2.0)


def _report(walk=None, shipping=None):
    return calculate_revenue_leak(
        performance=Performance(), third_party=None, checkout=None, cro_observations=[],
        rich_results=None, product_feeds=None, accessibility=None, ad_traffic=None,
        shipping=shipping, funnel_walk=walk, **_KW,
    )


def _walk(*issues, status="ok", confirmed=True):
    return FunnelWalk(
        status=status, steps=[FunnelStep(step="home", reached=True)],
        issues=[FunnelIssue(**i, machine_confirmed=confirmed) for i in issues],
    )


def _by_id(report):
    return {f.finding_id: f for f in report.findings}


def test_no_walk_or_unfinished_walk_changes_nothing():
    base = _report().model_dump()
    assert _report(_walk(status="blocked")).model_dump() == base
    assert _report(_walk(_issue(), status="failed")).model_dump() == base


def test_priced_walk_issue_adds_euros_from_the_rule_table_with_its_screenshot():
    report = _report(_walk(_issue(shot="s1")))
    f = _by_id(report)["walk.atc_blocked_by_overlay"]
    assert f.priced and f.monthly_high > 0
    assert f.exposure_share == report.funnel.mobile_share and (f.uplift_low, f.uplift_high) == (0.02, 0.06)
    assert f.screenshot_ids == ["s1"] and f.sources == ["funnel_walk"]
    assert report.total_monthly_loss_eur_high > (_report().total_monthly_loss_eur_high or 0)
    assert any(m.finding_id == "walk.atc_blocked_by_overlay" for layer in report.layers for m in layer.metrics)


def test_priced_key_without_machine_evidence_is_shown_without_euros():
    f = _by_id(_report(_walk(_issue(), confirmed=False)))["walk.atc_blocked_by_overlay"]
    assert f.priced is False and f.monthly_low is None and f.uplift_high is None


def test_unpriced_walk_issue_is_shown_without_euros():
    f = _by_id(_report(_walk(_issue(key="search_no_results", step="search"))))["walk.search_no_results"]
    assert f.priced is False and f.monthly_low is None


def test_two_other_issues_stay_separate():
    ids = _by_id(_report(_walk(_issue(key="other", step="cart"), _issue(key="other", step="product"))))
    assert {"walk.other_1", "walk.other_2"} <= set(ids)


def test_shipping_cost_late_merges_into_the_analyzer_finding_and_counts_once():
    shipping = ShippingHealth(cost_info_on_pdp=False)
    alone = _report(shipping=shipping)
    both = _report(_walk(_issue(key="shipping_cost_late", step="cart", shot="s2")), shipping=shipping)

    f = _by_id(both)["shipping.cost_clarity"]
    assert f.sources == ["shipping", "funnel_walk"] and f.screenshot_ids == ["s2"]
    assert both.total_monthly_loss_eur_high == alone.total_monthly_loss_eur_high
    assert not both.model_warnings or all(w.kind != "duplicate_finding" for w in both.model_warnings)


def test_shipping_cost_late_alone_registers_the_shipping_finding():
    f = _by_id(_report(_walk(_issue(key="shipping_cost_late", step="cart"))))["shipping.cost_clarity"]
    assert f.priced and f.sources == ["funnel_walk"]


# --- verifier and client -------------------------------------------------------------

def test_verifier_skips_walk_findings():
    data = FullAuditData(store_url="https://store.nl", scan_level="outside-only", revenue_leak=RevenueLeakReport(findings=[
        FindingOut(finding_id="walk.atc_no_feedback", owning_layer=3, metric="m", priced=True),
        FindingOut(finding_id="perf.lcp_mobile", owning_layer=1, metric="m", priced=True),
    ]))
    assert [f.finding_id for f in verification_candidates(data)] == ["perf.lcp_mobile"]


def test_client_sees_description_and_screenshot_but_no_evidence_model_or_warnings():
    walk = _walk(_issue(shot="s1"))
    walk.model, walk.input_tokens, walk.warnings = "m", 999, ["intern"]
    client = client_funnel_walk(walk).model_dump()
    assert client["issues"] == [{"issue_key": "atc_blocked_by_overlay", "step": "add_to_cart", "description_nl": "Popup over de knop", "screenshot_id": "s1"}]
    assert set(client) == {"steps", "issues", "summary_nl"}
    assert client_funnel_walk(_walk(status="blocked")) is None
