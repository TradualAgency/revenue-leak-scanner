"""The read-only tools an agent (fix agents, verifier) can call.

Nothing here writes anywhere: the audit is read from the stored JSON, pages are fetched
from the public storefront (same domain only), analyzers are re-run against one page,
and the Admin tools only exist when the operator supplied a read-only token.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

from app.analysis.scraper import HEADERS, fetch_page
from app.config import settings
from app.fix_agents.shopify_admin import ShopifyAdminClient, ShopifyAdminError
from app.full_audit.analyzers.performance import analyze_performance
from app.full_audit.analyzers.rich_results import analyze_rich_results
from app.full_audit.analyzers.third_party import scan_third_party
from app.full_audit.analyzers.tracking import detect_tracking
from app.full_audit.schemas import FullAuditData

# Sections of the stored audit an agent may read. Contact details and the Sanity export
# (page password) are deliberately absent.
AUDIT_SECTIONS: tuple[str, ...] = (
    "platform_architecture", "detected_stack", "performance", "third_party_scripts",
    "bloat_what_must_go", "cost_analysis", "shopify_apps", "tracking_data_quality",
    "server_side_tracking", "checkout_flow", "cro_observations", "owned_channels",
    "seo_health", "rich_results", "product_feeds", "shopify_catalog", "retention",
    "accessibility", "ad_traffic_impact", "revenue_leak", "ai_analysis",
)

HTML_PAGE_CHARS = 40_000

NOT_AVAILABLE = (
    "Niet beschikbaar: er is geen Shopify Admin-token voor deze audit. Werk met de "
    "publieke data en markeer aannames met verify_manually."
)


@dataclass
class ToolContext:
    audit: FullAuditData
    admin: ShopifyAdminClient | None = None
    used_admin: bool = False
    page_cache: dict[str, dict] = field(default_factory=dict)

    @property
    def store_host(self) -> str:
        return (urlparse(self.audit.store_url).hostname or "").removeprefix("www.")


# --- tool definitions ----------------------------------------------------------------

TOOL_SPECS: dict[str, dict] = {
    "get_audit_section": {
        "description": (
            "Lees een sectie uit de opgeslagen audit (JSON). Gebruik dit eerst: de audit "
            "bevat al gemeten PageSpeed-, script-, tracking-, checkout- en CRO-data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"section": {"type": "string", "enum": list(AUDIT_SECTIONS)}},
            "required": ["section"],
        },
    },
    "fetch_page": {
        "description": (
            "Haal een live publieke pagina van de store op (alleen het eigen domein). "
            "mode 'scripts' geeft alle <script>/<link rel=preload|stylesheet> met src en "
            "attributen; 'text' de zichtbare tekst; 'html' ruwe HTML in blokken van "
            f"{HTML_PAGE_CHARS} tekens (gebruik offset om verder te lezen)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "mode": {"type": "string", "enum": ["scripts", "text", "html"]},
                "offset": {"type": "integer", "minimum": 0},
            },
            "required": ["url", "mode"],
        },
    },
    "run_analyzer": {
        "description": (
            "Draai één bestaande audit-analyzer opnieuw op één URL om een hypothese te "
            "checken. 'performance' is een volledige PageSpeed-run (traag, ~1 min); "
            "de andere werken op de HTML van die pagina."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "analyzer": {"type": "string", "enum": ["performance", "third_party", "tracking", "rich_results"]},
                "url": {"type": "string"},
            },
            "required": ["analyzer", "url"],
        },
    },
    "list_theme_files": {
        "description": "Admin-token vereist. Lijst alle bestanden van het gepubliceerde theme (naam + grootte).",
        "input_schema": {"type": "object", "properties": {}},
    },
    "read_theme_file": {
        "description": (
            "Admin-token vereist. Lees één theme-bestand, bv. 'layout/theme.liquid' of "
            "'sections/main-product.liquid'. Lange bestanden komen in blokken; gebruik offset."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"filename": {"type": "string"}, "offset": {"type": "integer", "minimum": 0}},
            "required": ["filename"],
        },
    },
    "get_products_sample": {
        "description": "Admin-token vereist. De laatst bijgewerkte producten met status, voorraad, SEO-velden en aantal media.",
        "input_schema": {
            "type": "object",
            "properties": {"first": {"type": "integer", "minimum": 1, "maximum": 25}},
        },
    },
}

ADMIN_TOOLS = frozenset({"list_theme_files", "read_theme_file", "get_products_sample"})


def tool_definitions(names: list[str]) -> list[dict]:
    return [{"name": n, **TOOL_SPECS[n]} for n in names]


# --- implementations -----------------------------------------------------------------

def _chunk(text: str, offset: int) -> dict:
    part = text[offset:offset + HTML_PAGE_CHARS]
    end = offset + len(part)
    return {"offset": offset, "total_chars": len(text), "next_offset": end if end < len(text) else None, "content": part}


def _same_store(ctx: ToolContext, url: str) -> bool:
    host = (urlparse(url).hostname or "").removeprefix("www.")
    allowed = {ctx.store_host}
    if ctx.admin:
        allowed.add(ctx.admin.shop_domain)
    return bool(host) and host in allowed


async def _get_page(ctx: ToolContext, url: str) -> dict:
    if url not in ctx.page_cache:
        timeout = aiohttp.ClientTimeout(total=settings.SCRAPER_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as session:
            html, headers, status, cookies = await fetch_page(session, url)
        ctx.page_cache[url] = {"url": url, "html": html, "headers": headers, "set_cookies": cookies, "status": status, "load_time_ms": 0}
    return ctx.page_cache[url]


def _scripts_view(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for tag in soup.find_all(["script", "link"]):
        if tag.name == "link" and not set(tag.get("rel") or []) & {"preload", "stylesheet", "preconnect", "modulepreload"}:
            continue
        attrs = {k: (" ".join(v) if isinstance(v, list) else v) for k, v in tag.attrs.items()}
        entry = {"tag": tag.name, "in_head": tag.find_parent("head") is not None, **attrs}
        if tag.name == "script" and not tag.get("src"):
            inline = tag.get_text() or ""
            entry["inline_chars"] = len(inline)
            entry["inline_start"] = inline[:300]
        out.append(entry)
    return out


async def get_audit_section(ctx: ToolContext, section: str) -> Any:
    if section not in AUDIT_SECTIONS:
        raise ValueError(f"Onbekende sectie '{section}'.")
    value = getattr(ctx.audit, section)
    if isinstance(value, list):
        return [v.model_dump(mode="json") for v in value]
    return value.model_dump(mode="json") if value is not None else None


async def fetch_page_tool(ctx: ToolContext, url: str, mode: str, offset: int = 0) -> Any:
    if not _same_store(ctx, url):
        raise ValueError(f"Alleen URL's op {ctx.store_host} zijn toegestaan.")
    page = await _get_page(ctx, url)
    if not page["html"]:
        return {"status": page["status"], "error": "Pagina kon niet worden opgehaald."}
    if mode == "scripts":
        return {"status": page["status"], "scripts": _scripts_view(page["html"])}
    if mode == "text":
        text = BeautifulSoup(page["html"], "lxml").get_text("\n", strip=True)
        return {"status": page["status"], **_chunk(text, offset)}
    return {"status": page["status"], **_chunk(page["html"], offset)}


async def run_analyzer(ctx: ToolContext, analyzer: str, url: str) -> Any:
    if not _same_store(ctx, url):
        raise ValueError(f"Alleen URL's op {ctx.store_host} zijn toegestaan.")
    if analyzer == "performance":
        # No pages: the URL itself is the page to measure, so skip the money-page pick.
        perf, _ = await analyze_performance(url, [], include_desktop=False)
        return perf.model_dump(mode="json")
    page = await _get_page(ctx, url)
    pages = [page] if page["html"] else []
    if not pages:
        return {"error": "Pagina kon niet worden opgehaald."}
    fn = {"third_party": scan_third_party, "tracking": detect_tracking, "rich_results": analyze_rich_results}[analyzer]
    return (await fn(pages)).model_dump(mode="json")


async def list_theme_files(ctx: ToolContext) -> Any:
    return await ctx.admin.list_theme_files()  # type: ignore[union-attr]


async def read_theme_file(ctx: ToolContext, filename: str, offset: int = 0) -> Any:
    content = await ctx.admin.read_theme_file(filename)  # type: ignore[union-attr]
    if content is None:
        return {"error": f"'{filename}' niet gevonden of geen tekstbestand."}
    return {"filename": filename, **_chunk(content, offset)}


async def get_products_sample(ctx: ToolContext, first: int = 10) -> Any:
    return await ctx.admin.products_sample(first)  # type: ignore[union-attr]


_IMPLS: dict[str, Callable[..., Awaitable[Any]]] = {
    "get_audit_section": get_audit_section,
    "fetch_page": fetch_page_tool,
    "run_analyzer": run_analyzer,
    "list_theme_files": list_theme_files,
    "read_theme_file": read_theme_file,
    "get_products_sample": get_products_sample,
}


async def execute_tool(ctx: ToolContext, name: str, args: dict) -> tuple[str, bool]:
    """(result text, is_error). Errors go back to the model as an is_error tool_result
    so it can adjust, rather than failing the whole run."""
    if name not in _IMPLS:
        return f"Onbekende tool '{name}'.", True
    if name in ADMIN_TOOLS:
        if ctx.admin is None:
            return NOT_AVAILABLE, True
        ctx.used_admin = True
    try:
        result = await _IMPLS[name](ctx, **args)
    except (ValueError, TypeError, ShopifyAdminError) as exc:
        return str(exc), True
    except Exception as exc:  # network/analyzer failures: report, don't crash the run
        return f"{type(exc).__name__}: {exc}", True
    return json.dumps(result, ensure_ascii=False, default=str), False
