"""Read-only Shopify Admin GraphQL access for the fix agents.

The operator pastes a custom-app Admin API token per audit. It is stored Fernet-
encrypted and refused outright when it carries any write scope: the agents describe
fixes, the Tradual team applies them, and a token that could change the store has no
business sitting in this database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import aiohttp
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

_SHOP_DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$")

# Every query this module sends. All of them are reads.
_VERIFY_QUERY = """
query VerifyToken {
  shop { name myshopifyDomain }
  currentAppInstallation { accessScopes { handle } }
}
"""

_MAIN_THEME_QUERY = """
query MainTheme {
  themes(first: 1, roles: [MAIN]) { nodes { id name } }
}
"""

_THEME_FILES_QUERY = """
query ThemeFiles($id: ID!, $after: String) {
  theme(id: $id) {
    files(first: 250, after: $after) {
      nodes { filename size }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""

_THEME_FILE_BODY_QUERY = """
query ThemeFileBody($id: ID!, $filenames: [String!]) {
  theme(id: $id) {
    files(filenames: $filenames, first: 1) {
      nodes {
        filename
        body { ... on OnlineStoreThemeFileBodyText { content } }
      }
    }
  }
}
"""

_PRODUCTS_QUERY = """
query ProductsSample($first: Int!) {
  products(first: $first, sortKey: UPDATED_AT, reverse: true) {
    nodes {
      handle title status totalInventory productType vendor
      description(truncateAt: 300)
      seo { title description }
      mediaCount { count }
      variantsCount { count }
    }
  }
}
"""


_CURRENCY_QUERY = """
query ShopCurrency {
  shop { currencyCode }
}
"""

_SHOPIFYQL_QUERY = """
query StoreMetrics($q: String!) {
  shopifyqlQuery(query: $q) {
    tableData { columns { name } rows }
    parseErrors
  }
}
"""

# What a read-only token needs: the agents read the theme and products, the full-access
# audit reads the store's own sales and session numbers.
REQUIRED_SCOPES = ("read_themes", "read_products", "read_reports")


class ShopifyAdminError(Exception):
    pass


@dataclass
class StoreMetrics:
    """Monthly averages over one window, so sessions x CR x AOV matches the revenue by
    construction (the leak model derives CR from these three)."""
    days: int
    monthly_revenue_eur: float | None = None
    aov_eur: float | None = None
    monthly_sessions: int | None = None
    mobile_share_pct: float | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def annual_revenue_eur(self) -> float | None:
        return self.monthly_revenue_eur * 12 if self.monthly_revenue_eur is not None else None


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_shop_domain(raw: str) -> str:
    domain = raw.strip().lower().removeprefix("https://").removeprefix("http://").split("/")[0]
    if not _SHOP_DOMAIN_RE.match(domain):
        raise ShopifyAdminError("Gebruik de myshopify-domeinnaam, bv. 'merk.myshopify.com'.")
    return domain


def _fernet() -> Fernet:
    if not settings.TOKEN_ENCRYPTION_KEY:
        raise ShopifyAdminError("TOKEN_ENCRYPTION_KEY is niet ingesteld; tokens kunnen niet worden opgeslagen.")
    return Fernet(settings.TOKEN_ENCRYPTION_KEY.encode())


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt_token(token_enc: str) -> str:
    try:
        return _fernet().decrypt(token_enc.encode()).decode()
    except InvalidToken as exc:
        raise ShopifyAdminError("Opgeslagen token kan niet worden ontsleuteld (andere TOKEN_ENCRYPTION_KEY?).") from exc


def write_scopes(scopes: list[str]) -> list[str]:
    return [s for s in scopes if s.startswith("write_") or s.startswith("unauthenticated_write_")]


async def validate_and_encrypt(raw_domain: str, access_token: str) -> tuple[str, str, str, list[str]]:
    """(domain, encrypted token, shop name, scopes) for a token that works and can only
    read. Raises ShopifyAdminError otherwise."""
    domain = normalize_shop_domain(raw_domain)
    shop_name, scopes = await ShopifyAdminClient(domain, access_token).verify()
    if write := write_scopes(scopes):
        raise ShopifyAdminError(
            f"Token heeft schrijfrechten ({', '.join(write)}). Maak een custom app met "
            f"alleen read-scopes ({', '.join(REQUIRED_SCOPES)})."
        )
    return domain, encrypt_token(access_token), shop_name, scopes


class ShopifyAdminClient:
    def __init__(self, shop_domain: str, access_token: str):
        self.shop_domain = shop_domain
        self._token = access_token
        self._main_theme_id: str | None = None

    @property
    def _endpoint(self) -> str:
        return f"https://{self.shop_domain}/admin/api/{settings.SHOPIFY_ADMIN_API_VERSION}/graphql.json"

    async def _query(self, query: str, variables: dict | None = None) -> dict:
        headers = {"X-Shopify-Access-Token": self._token, "Content-Type": "application/json"}
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self._endpoint, json={"query": query, "variables": variables or {}}, headers=headers) as resp:
                if resp.status in (401, 403):
                    raise ShopifyAdminError(f"Shopify weigert het token (HTTP {resp.status}).")
                if resp.status != 200:
                    raise ShopifyAdminError(f"Shopify Admin API gaf HTTP {resp.status}.")
                payload = await resp.json()
        if payload.get("errors"):
            raise ShopifyAdminError(f"GraphQL-fout: {payload['errors']}")
        return payload.get("data") or {}

    async def verify(self) -> tuple[str, list[str]]:
        """(shop name, granted scopes)."""
        data = await self._query(_VERIFY_QUERY)
        scopes = [s["handle"] for s in (data.get("currentAppInstallation") or {}).get("accessScopes", [])]
        return (data.get("shop") or {}).get("name", ""), scopes

    async def _theme_id(self) -> str:
        if self._main_theme_id is None:
            nodes = (await self._query(_MAIN_THEME_QUERY)).get("themes", {}).get("nodes", [])
            if not nodes:
                raise ShopifyAdminError("Geen gepubliceerd (MAIN) theme gevonden.")
            self._main_theme_id = nodes[0]["id"]
        return self._main_theme_id

    async def list_theme_files(self) -> list[dict]:
        theme_id = await self._theme_id()
        files: list[dict] = []
        after: str | None = None
        while True:
            data = await self._query(_THEME_FILES_QUERY, {"id": theme_id, "after": after})
            conn = (data.get("theme") or {}).get("files") or {}
            files.extend(conn.get("nodes", []))
            page = conn.get("pageInfo") or {}
            if not page.get("hasNextPage"):
                return files
            after = page.get("endCursor")

    async def read_theme_file(self, filename: str) -> str | None:
        theme_id = await self._theme_id()
        data = await self._query(_THEME_FILE_BODY_QUERY, {"id": theme_id, "filenames": [filename]})
        nodes = ((data.get("theme") or {}).get("files") or {}).get("nodes", [])
        if not nodes:
            return None
        return (nodes[0].get("body") or {}).get("content")

    async def products_sample(self, first: int = 10) -> list[dict]:
        data = await self._query(_PRODUCTS_QUERY, {"first": max(1, min(first, 25))})
        return (data.get("products") or {}).get("nodes", [])

    async def _shopifyql(self, query: str) -> list[dict]:
        data = (await self._query(_SHOPIFYQL_QUERY, {"q": query})).get("shopifyqlQuery") or {}
        if data.get("parseErrors"):
            raise ShopifyAdminError(f"ShopifyQL: {'; '.join(data['parseErrors'])}")
        return ((data.get("tableData") or {}).get("rows")) or []

    async def store_metrics(self, days: int = 90) -> StoreMetrics:
        """Revenue, AOV, sessions and mobile share from the store's own analytics
        (needs read_reports). Never raises: a metric that can't be read stays None and
        leaves a warning, so the audit falls back to the operator's numbers."""
        metrics = StoreMetrics(days=days)
        months = days / 30
        window = f"SINCE startOfDay(-{days}d) UNTIL today"

        try:
            currency = ((await self._query(_CURRENCY_QUERY)).get("shop") or {}).get("currencyCode")
        except ShopifyAdminError as exc:
            currency = None
            metrics.warnings.append(f"Valuta onbekend: {exc}")
        rate = {"EUR": 1.0, "USD": settings.USD_TO_EUR_RATE}.get(currency or "")

        try:
            rows = await self._shopifyql(f"FROM sales SHOW total_sales, orders {window}")
            total = sum(_num(r.get("total_sales")) or 0 for r in rows)
            orders = sum(_num(r.get("orders")) or 0 for r in rows)
            if rate is None:
                metrics.warnings.append(f"Omzet niet overgenomen: winkelvaluta {currency or 'onbekend'} wordt niet omgerekend.")
            elif total > 0 and orders > 0:
                metrics.monthly_revenue_eur = round(total * rate / months, 2)
                metrics.aov_eur = round(total * rate / orders, 2)
            else:
                metrics.warnings.append(f"Geen omzet of orders gevonden in de laatste {days} dagen.")
        except ShopifyAdminError as exc:
            metrics.warnings.append(f"Omzet niet gelezen: {exc}")

        try:
            rows = await self._shopifyql(
                f"FROM sessions SHOW sessions WHERE human_or_bot_session = 'human' "
                f"GROUP BY session_device_type {window}"
            )
            by_device = {str(r.get("session_device_type") or "").lower(): _num(r.get("sessions")) or 0 for r in rows}
            sessions = sum(by_device.values())
            if sessions > 0:
                metrics.monthly_sessions = round(sessions / months)
                mobile = sum(v for k, v in by_device.items() if "mobile" in k)
                metrics.mobile_share_pct = round(mobile / sessions * 100, 1)
            else:
                metrics.warnings.append(f"Geen sessies gevonden in de laatste {days} dagen.")
        except ShopifyAdminError as exc:
            metrics.warnings.append(f"Sessies niet gelezen: {exc}")

        return metrics
