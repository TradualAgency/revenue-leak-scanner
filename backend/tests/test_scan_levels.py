"""What semi and full-access add over outside-only: the agents always run, and a
full-access audit takes its business numbers from the store's own Shopify analytics."""

import uuid

import pytest
from cryptography.fernet import Fernet

from app.config import settings
from app.fix_agents.shopify_admin import ShopifyAdminClient, ShopifyAdminError, encrypt_token
from app.full_audit import router as full_audit_router
from app.full_audit.models import FullAudit
from app.full_audit.service import agents_enabled, fill_from_shopify

OPERATOR = {"X-Operator-Key": settings.OPERATOR_API_KEY}


@pytest.fixture(autouse=True)
def encryption_key(monkeypatch):
    monkeypatch.setattr(settings, "TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())


def _stub_queries(monkeypatch, *, currency="EUR", sales=None, sessions=None, fail=()):
    """Fake Admin API: `sales`/`sessions` are ShopifyQL rows; a dataset named in
    `fail` raises like a token without read_reports would."""
    async def _query(self, query, variables=None):
        if "ShopCurrency" in query:
            return {"shop": {"currencyCode": currency}}
        q = variables["q"]
        dataset = "sales" if q.startswith("FROM sales") else "sessions"
        if dataset in fail:
            raise ShopifyAdminError("Access denied for shopifyqlQuery field.")
        rows = sales if dataset == "sales" else sessions
        return {"shopifyqlQuery": {"tableData": {"rows": rows or []}, "parseErrors": []}}

    monkeypatch.setattr(ShopifyAdminClient, "_query", _query)


_SALES = [{"total_sales": "390000.00", "orders": "3000"}]  # 90 days
_SESSIONS = [
    {"session_device_type": "Mobile", "sessions": "150000"},
    {"session_device_type": "Desktop", "sessions": "54000"},
]


# --- store_metrics -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_metrics_are_monthly_averages_over_one_window(monkeypatch):
    _stub_queries(monkeypatch, sales=_SALES, sessions=_SESSIONS)
    m = await ShopifyAdminClient("s.myshopify.com", "t").store_metrics(days=90)

    assert m.monthly_revenue_eur == 130_000 and m.annual_revenue_eur == 1_560_000
    assert m.aov_eur == 130 and m.monthly_sessions == 68_000
    assert m.mobile_share_pct == pytest.approx(73.5)
    # Consistent by construction: sessions x CR x AOV gives the revenue back.
    cr = m.monthly_revenue_eur / (m.monthly_sessions * m.aov_eur)
    assert m.monthly_sessions * cr * m.aov_eur == pytest.approx(m.monthly_revenue_eur)
    assert m.warnings == []


@pytest.mark.asyncio
async def test_usd_is_converted_and_other_currencies_are_skipped(monkeypatch):
    monkeypatch.setattr(settings, "USD_TO_EUR_RATE", 0.5)
    _stub_queries(monkeypatch, currency="USD", sales=_SALES, sessions=_SESSIONS)
    m = await ShopifyAdminClient("s.myshopify.com", "t").store_metrics()
    assert m.monthly_revenue_eur == 65_000 and m.aov_eur == 65

    _stub_queries(monkeypatch, currency="SEK", sales=_SALES, sessions=_SESSIONS)
    m = await ShopifyAdminClient("s.myshopify.com", "t").store_metrics()
    assert m.monthly_revenue_eur is None and m.aov_eur is None
    assert m.monthly_sessions == 68_000  # sessions don't depend on currency
    assert any("SEK" in w for w in m.warnings)


@pytest.mark.asyncio
async def test_a_missing_scope_leaves_none_and_a_warning_instead_of_raising(monkeypatch):
    _stub_queries(monkeypatch, sales=_SALES, sessions=_SESSIONS, fail=("sessions",))
    m = await ShopifyAdminClient("s.myshopify.com", "t").store_metrics()
    assert m.monthly_revenue_eur == 130_000
    assert m.monthly_sessions is None and m.mobile_share_pct is None
    assert any("Sessies niet gelezen" in w for w in m.warnings)


# --- fill_from_shopify ---------------------------------------------------------------

def _audit(**kwargs) -> FullAudit:
    return FullAudit(
        id=uuid.uuid4(), store_url="https://store.nl", scan_level=kwargs.pop("scan_level", "full-access"),
        shopify_shop_domain="store.myshopify.com", shopify_admin_token_enc=encrypt_token("shpat_x"), **kwargs,
    )


@pytest.mark.asyncio
async def test_shopify_fills_only_the_fields_the_operator_left_empty(monkeypatch):
    _stub_queries(monkeypatch, sales=_SALES, sessions=_SESSIONS)
    audit = _audit(aov_eur=114.0)

    notes = await fill_from_shopify(audit)

    assert audit.aov_eur == 114.0  # the operator's correction wins
    assert audit.estimated_annual_revenue_eur == 1_560_000
    assert audit.monthly_sessions == 68_000 and audit.mobile_share_pct == pytest.approx(73.5)
    assert notes and "Shopify Admin" in notes[0] and "AOV" not in notes[0]


@pytest.mark.asyncio
async def test_other_scan_levels_never_call_shopify(monkeypatch):
    async def boom(self, *a, **k):
        raise AssertionError("no Shopify call expected")
    monkeypatch.setattr(ShopifyAdminClient, "_query", boom)
    for level in ("outside-only", "semi"):
        audit = _audit(scan_level=level)
        assert await fill_from_shopify(audit) == []
        assert audit.monthly_sessions is None


def test_semi_and_full_access_always_run_the_agents():
    assert agents_enabled("semi") and agents_enabled("full-access")
    assert not agents_enabled("outside-only")


# --- POST /full-audit ----------------------------------------------------------------

@pytest.fixture
def no_background_work(monkeypatch):
    async def noop(*args, **kwargs):
        return None
    monkeypatch.setattr(full_audit_router, "run_full_audit", noop)


@pytest.fixture
def stub_verify(monkeypatch):
    scopes = {"value": ["read_themes", "read_products", "read_reports"]}

    async def verify(self):
        return "Store BV", scopes["value"]

    monkeypatch.setattr(ShopifyAdminClient, "verify", verify)
    return scopes


@pytest.mark.asyncio
async def test_full_access_without_a_token_is_422(client, no_background_work):
    resp = await client.post(
        "/api/v1/full-audit", json={"store_url": "https://store.nl", "scan_level": "full-access"}, headers=OPERATOR,
    )
    assert resp.status_code == 422 and "token" in resp.text


@pytest.mark.asyncio
async def test_full_access_refuses_a_token_with_write_scopes(client, no_background_work, stub_verify):
    stub_verify["value"] = ["read_reports", "write_orders"]
    resp = await client.post(
        "/api/v1/full-audit",
        json={"store_url": "https://store.nl", "scan_level": "full-access",
              "shopify_shop_domain": "store.myshopify.com", "shopify_access_token": "shpat_0123456789"},
        headers=OPERATOR,
    )
    assert resp.status_code == 422 and "write_orders" in resp.text


@pytest.mark.asyncio
async def test_full_access_stores_the_token_encrypted(client, db_session, no_background_work, stub_verify):
    resp = await client.post(
        "/api/v1/full-audit",
        json={"store_url": "https://store.nl", "scan_level": "full-access",
              "shopify_shop_domain": "https://Store.myshopify.com/", "shopify_access_token": "shpat_0123456789"},
        headers=OPERATOR,
    )
    assert resp.status_code == 201
    audit = await db_session.get(FullAudit, uuid.UUID(resp.json()["id"]))
    assert audit.shopify_shop_domain == "store.myshopify.com"
    assert audit.shopify_admin_token_enc and "shpat_0123456789" not in audit.shopify_admin_token_enc
