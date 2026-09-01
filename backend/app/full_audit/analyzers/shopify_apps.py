import re

from app.full_audit.schemas import ShopifyAppsHealth

# Shopify's app-extension platform (theme app extensions, checkout UI extensions, etc.)
# serves each extension from a per-extension-instance UUID path. A distinct UUID here is
# strong evidence of a distinct installed app actually running on the storefront — unlike
# counting third-party domains, which mixes in trackers, fonts, and embeds that were never
# apps. Resolving the UUID to an app *name* requires Shopify's non-public Admin API, so
# this reports counts/ids only.
_EXTENSION_RE = re.compile(r"cdn\.shopify\.com/extensions/([0-9a-fA-F-]{36})/")


async def detect_shopify_apps(pages: list[dict]) -> ShopifyAppsHealth | None:
    if not pages:
        return None

    all_html = "\n".join(p.get("html", "") for p in pages)
    ids = sorted(set(_EXTENSION_RE.findall(all_html)))

    if not ids and "cdn.shopify.com" not in all_html:
        # No Shopify CDN reference at all — not a Shopify store, nothing to report.
        return None

    return ShopifyAppsHealth(
        app_extension_count=len(ids),
        app_extension_ids=ids,
        evidence=f"{len(ids)} unieke app-extension UUID's gevonden via cdn.shopify.com/extensions/" if ids else None,
        notes=(
            "App-namen zijn niet herleidbaar uit een extension-UUID zonder toegang tot de "
            "Shopify Admin API — dit telt alleen hoeveel losse app-extensies actief zijn."
        ),
    )
