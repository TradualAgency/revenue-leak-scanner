"""Shared page-type classification for the scraped page set.

Originally lived only in cro.py; multiple analyzers now need "find me a PDP/collection
page from what we scraped" (CRO social-proof checks, EU compliance sampling, PSI runs
on a PDP instead of only the homepage), so it's centralized here.
"""

PAGE_TYPE_PATTERNS: dict[str, list[str]] = {
    "pdp": ["/product/", "/products/", "/p/", "/shop/", "/item/"],
    "collection": ["/collections/", "/category/", "/c/", "/shop-all", "/categorie"],
    "cart": ["/cart", "/winkelwagen", "/basket"],
    "checkout": ["/checkout"],
    "account": ["/account", "/login", "/register", "/inloggen"],
}

PAGE_LABELS = {
    "homepage": "Homepage",
    "pdp": "Product page (PDP)",
    "collection": "Collection page",
    "cart": "Cart",
    "checkout": "Checkout",
    "account": "Account",
    "other": "Other",
}


def classify_page(url: str, is_first: bool) -> str:
    if is_first:
        return "homepage"
    lower = url.lower()
    for ptype, patterns in PAGE_TYPE_PATTERNS.items():
        if any(p in lower for p in patterns):
            return ptype
    return "other"


def sample_pages_by_type(pages: list[dict]) -> dict[str, dict]:
    """Return one representative page per type — first match wins."""
    sampled: dict[str, dict] = {}
    for i, page in enumerate(pages):
        ptype = classify_page(page.get("url", ""), is_first=(i == 0))
        sampled.setdefault(ptype, page)
    return sampled
