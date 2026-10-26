"""One JSON-LD reader for every analyzer that needs structured data.

rich_results, product_feeds and cro each parsed `<script type="application/ld+json">`
themselves, each missing a different shape: `@type` given as a list, `ProductGroup`
(newer Shopify themes), or data nested under `@graph`, `mainEntity`, `offers` or
`hasVariant`. This walks the whole tree once, so a Product nested three levels deep
counts the same as one at the top.
"""

from __future__ import annotations

import json

from bs4 import BeautifulSoup

PRODUCT_TYPES = frozenset({"Product", "ProductGroup"})


def _walk(node, out: list[dict]) -> None:
    if isinstance(node, dict):
        if "@type" in node:
            out.append(node)
        for value in node.values():
            _walk(value, out)
    elif isinstance(node, list):
        for item in node:
            _walk(item, out)


def jsonld_nodes(html: str) -> list[dict]:
    """Every typed object in the page's JSON-LD, at any depth. Unparseable blocks are
    skipped rather than failing the page."""
    nodes: list[dict] = []
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return nodes
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            _walk(json.loads(tag.string or tag.get_text()), nodes)
        except Exception:
            continue
    return nodes


def node_types(node: dict) -> set[str]:
    t = node.get("@type")
    if isinstance(t, list):
        return {x for x in t if isinstance(x, str)}
    return {t} if isinstance(t, str) and t else set()


def product_keys(node: dict) -> set[str]:
    """Lower-cased keys of a Product plus its offers and first variant — Shopify puts
    `sku` and `gtin13` on the offer or variant, not on the Product itself."""
    keys = {k.lower() for k in node}
    for nested_key in ("offers", "hasVariant"):
        nested = node.get(nested_key)
        first = nested[0] if isinstance(nested, list) and nested else nested
        if isinstance(first, dict):
            keys |= {k.lower() for k in first}
    return keys
