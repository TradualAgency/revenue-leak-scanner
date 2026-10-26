"""Read-only Shopify Admin GraphQL access for the fix agents.

The operator pastes a custom-app Admin API token per audit. It is stored Fernet-
encrypted and refused outright when it carries any write scope: the agents describe
fixes, the Tradual team applies them, and a token that could change the store has no
business sitting in this database.
"""

from __future__ import annotations

import re

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


class ShopifyAdminError(Exception):
    pass


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
