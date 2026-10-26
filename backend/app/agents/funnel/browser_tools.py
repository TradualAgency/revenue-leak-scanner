"""The tools the funnel agent drives the browser with. Every tool reports what it
measured (status, timings, what changed) rather than what it assumes, and a failure
goes back to the model as an is_error tool_result — a click that Playwright refuses
because something "intercepts pointer events" is itself evidence of an overlay.
"""

from __future__ import annotations

import base64
import json
import re
import time
from typing import Any
from urllib.parse import urljoin

from app.agents.funnel.browser import BrowserSession, Screenshot, _host, is_checkout_url

MAX_SCREENSHOTS = 12
SNAPSHOT_CHARS = 9_000
CLICK_TIMEOUT_MS = 5_000
SETTLE_MS = 1_500

READ_ONLY_IN_CHECKOUT = "In de checkout mag je alleen kijken (snapshot/screenshot/scroll): niets aanklikken of invullen."

# Facts the browser layer records itself; FunnelWalk issues are only priced with one.
EVIDENCE_INTERCEPTED_CLICK = "intercepted_click"      # Playwright: another element receives the click
EVIDENCE_ATC_NO_CART_REQUEST = "atc_no_cart_request"  # an add-to-cart click with no cart call after it
EVIDENCE_CHECKOUT_ERROR = "checkout_error"            # the checkout page itself failed to load

_ATC_LABEL = re.compile(r"(add to (cart|bag|basket)|in (de )?winkel(wagen|mand)|toevoegen|in den warenkorb|ajouter au panier)", re.I)

TOOL_SPECS: list[dict] = [
    {
        "name": "goto",
        "description": "Open een URL van de eigen store (pad of volledige URL). Geeft status, titel, laadtijd en open overlays.",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    },
    {
        "name": "snapshot",
        "description": (
            "De toegankelijkheidsboom (ARIA) van de huidige pagina: rollen en namen van knoppen, links, "
            "velden. Gebruik die rollen/namen voor click en select_option. Meldt ook open dialogs/overlays. "
            "Lange pagina's worden afgekapt: geef `contains` mee (bv. 'checkout') om alleen regels met die "
            "tekst te krijgen, ook als ze onderaan de pagina staan (zoals in een cart drawer)."
        ),
        "input_schema": {"type": "object", "properties": {"contains": {"type": "string"}}},
    },
    {
        "name": "click",
        "description": (
            "Klik op een element via rol + naam uit de snapshot (bv. role 'button', name 'In winkelwagen'). "
            "Raakt de naam meerdere elementen, dan krijg je de kandidaten terug: kies dan met exact of nth. "
            "Meet hoe lang het duurt tot de winkelmand reageert en wat er veranderde. Een fout als "
            "'intercepts pointer events' betekent dat iets het element afdekt."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "role": {"type": "string"},
                "name": {"type": "string"},
                "exact": {"type": "boolean"},
                "nth": {"type": "integer", "minimum": 0, "description": "Alleen nodig als de naam meerdere elementen raakt."},
            },
            "required": ["role", "name"],
        },
    },
    {
        "name": "click_text",
        "description": (
            "Klik op het eerste zichtbare element met deze tekst. Gebruik dit als click(role, name) het element "
            "niet vindt terwijl het op de screenshot wel zichtbaar is (veel thema's gebruiken een <div> als knop)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "exact": {"type": "boolean"}},
            "required": ["text"],
        },
    },
    {
        "name": "select_option",
        "description": "Kies een optie in een <select> (bv. maat of kleur), via het label van het veld.",
        "input_schema": {
            "type": "object",
            "properties": {"label": {"type": "string"}, "option": {"type": "string"}},
            "required": ["label", "option"],
        },
    },
    {
        "name": "type_search",
        "description": "Typ een zoekterm in het zoekveld van de store en druk op Enter. Werkt alleen op zoekvelden.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    },
    {
        "name": "scroll",
        "description": "Scroll de pagina omlaag of omhoog.",
        "input_schema": {
            "type": "object",
            "properties": {"direction": {"type": "string", "enum": ["down", "up"]}, "pixels": {"type": "integer", "minimum": 100, "maximum": 3000}},
            "required": ["direction"],
        },
    },
    {
        "name": "screenshot",
        "description": (
            f"Maak een screenshot van wat de bezoeker nu ziet (mobiel scherm). Je krijgt de afbeelding "
            f"en een screenshot_id terug. Maximaal {MAX_SCREENSHOTS} per walk: bewaar ze voor bewijs."
        ),
        "input_schema": {"type": "object", "properties": {"caption": {"type": "string"}}, "required": ["caption"]},
    },
]

_OVERLAY_JS = """
() => {
  const vw = innerWidth, vh = innerHeight, out = [];
  for (const el of document.querySelectorAll('body *')) {
    const s = getComputedStyle(el);
    if (s.position !== 'fixed' && s.position !== 'sticky' && !(el.matches('dialog[open], [role=dialog], [aria-modal=true]'))) continue;
    if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) < 0.1) continue;
    const text = (el.innerText || '').trim();
    if (s.pointerEvents === 'none' && !text) continue;  // e.g. a closed mobile menu container
    const r = el.getBoundingClientRect();
    const share = Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0)) * Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0)) / (vw * vh);
    if (share < 0.25) continue;
    out.push({tag: el.tagName.toLowerCase(), id: el.id || null, cls: (el.className && el.className.toString().slice(0, 80)) || null,
              role: el.getAttribute('role'), viewport_share: Math.round(share * 100) / 100,
              text: text.slice(0, 160)});
    if (out.length >= 5) break;
  }
  return out;
}
"""


async def _page_state(session: BrowserSession) -> dict:
    page = session.page
    try:
        overlays = await page.evaluate(_OVERLAY_JS)
    except Exception:
        overlays = []
    return {"url": page.url, "title": await page.title(), "in_checkout": is_checkout_url(page.url), "overlays": overlays}


def _same_store(session: BrowserSession, url: str) -> bool:
    return _host(url) in session.store_hosts


async def goto(session: BrowserSession, url: str) -> Any:
    target = urljoin(session.store_url.rstrip("/") + "/", url)
    if not _same_store(session, target):
        raise ValueError(f"Alleen URL's op {next(iter(session.store_hosts))} zijn toegestaan.")
    start = time.monotonic()
    response = await session.page.goto(target, wait_until="domcontentloaded", timeout=30_000)
    try:
        await session.page.wait_for_load_state("load", timeout=10_000)
    except Exception:
        pass
    await session.page.wait_for_timeout(SETTLE_MS)  # let popups/widgets mount, as a visitor would see them
    status = response.status if response else None
    if (is_checkout_url(target) or is_checkout_url(session.page.url)) and (status is None or status >= 400):
        session.evidence.add(EVIDENCE_CHECKOUT_ERROR)
    return {
        "status": status,
        "load_ms": round((time.monotonic() - start) * 1000),
        **await _page_state(session),
    }


async def snapshot(session: BrowserSession, contains: str | None = None) -> Any:
    tree = await session.page.locator("body").aria_snapshot(timeout=10_000)
    if contains:
        needle = contains.lower()
        tree = "\n".join(line for line in tree.splitlines() if needle in line.lower()) or f"(geen regels met '{contains}')"
    truncated = len(tree) > SNAPSHOT_CHARS
    return {**await _page_state(session), "aria": tree[:SNAPSHOT_CHARS], "truncated": truncated}


async def click(session: BrowserSession, role: str, name: str, exact: bool = False, nth: int | None = None) -> Any:
    page = session.page
    if is_checkout_url(page.url):
        raise ValueError(READ_ONLY_IN_CHECKOUT)
    locator = page.get_by_role(role, name=name, exact=exact)  # type: ignore[arg-type]
    count = await locator.count()
    if count == 0:
        raise ValueError(f"Geen element met rol '{role}' en naam '{name}' gevonden. Maak eerst een snapshot.")
    if count > 1 and nth is None:
        # Never guess: a substring match on "Add to Cart" also hits the quick-add buttons
        # of recommended products, and clicking one of those is not what a visitor did.
        names = []
        for i in range(min(count, 8)):
            el = locator.nth(i)
            label = (await el.get_attribute("aria-label")) or (await el.inner_text(timeout=2_000))
            names.append({"nth": i, "name": " ".join((label or "").split())[:80], "visible": await el.is_visible()})
        raise ValueError(f"'{name}' raakt {count} elementen; kies met exact=true of nth: {json.dumps(names, ensure_ascii=False)}")
    target = locator.nth(min(nth or 0, count - 1))
    return {"matches": count, **await _click_and_measure(session, target, name)}


async def click_text(session: BrowserSession, text: str, exact: bool = False) -> Any:
    page = session.page
    if is_checkout_url(page.url):
        raise ValueError(READ_ONLY_IN_CHECKOUT)
    locator = page.get_by_text(text, exact=exact).locator("visible=true")
    count = await locator.count()
    if count == 0:
        raise ValueError(f"Geen zichtbaar element met tekst '{text}' gevonden.")
    return {"matches": count, **await _click_and_measure(session, locator.first, text)}


async def _click_and_measure(session: BrowserSession, target, label: str) -> dict:
    page = session.page
    before_url = page.url
    before_cart = len(session.cart_responses)
    start = time.monotonic()
    await target.click(timeout=CLICK_TIMEOUT_MS)
    await page.wait_for_timeout(SETTLE_MS)
    cart_ms = None
    if len(session.cart_responses) > before_cart:
        cart_ms = round((session.cart_responses[before_cart] - start) * 1000)
    elif _ATC_LABEL.search(label):
        session.evidence.add(EVIDENCE_ATC_NO_CART_REQUEST)
    return {
        "navigated": page.url != before_url,
        "cart_request_ms": cart_ms,  # None: no cart call followed the click
        **await _page_state(session),
    }


async def select_option(session: BrowserSession, label: str, option: str) -> Any:
    if is_checkout_url(session.page.url):
        raise ValueError(READ_ONLY_IN_CHECKOUT)
    selected = await session.page.get_by_label(label).first.select_option(label=option, timeout=CLICK_TIMEOUT_MS)
    await session.page.wait_for_timeout(SETTLE_MS)
    return {"selected": selected, **await _page_state(session)}


async def type_search(session: BrowserSession, query: str) -> Any:
    page = session.page
    if is_checkout_url(page.url):
        raise ValueError(READ_ONLY_IN_CHECKOUT)
    field = page.locator("input[type=search], input[name=q]").first
    if await field.count() == 0:
        raise ValueError("Geen zoekveld zichtbaar. Open eerst het zoek-icoon (click) of ga naar /search.")
    start = time.monotonic()
    await field.fill(query[:100], timeout=CLICK_TIMEOUT_MS)
    await field.press("Enter")
    await page.wait_for_load_state("domcontentloaded", timeout=15_000)
    await page.wait_for_timeout(SETTLE_MS)
    return {"search_ms": round((time.monotonic() - start) * 1000), **await _page_state(session)}


async def scroll(session: BrowserSession, direction: str, pixels: int = 800) -> Any:
    await session.page.mouse.wheel(0, pixels if direction == "down" else -pixels)
    await session.page.wait_for_timeout(500)
    return await _page_state(session)


async def screenshot(session: BrowserSession, caption: str) -> list[dict]:
    if len(session.screenshots) >= MAX_SCREENSHOTS:
        raise ValueError(f"Maximum van {MAX_SCREENSHOTS} screenshots bereikt.")
    # CSS pixels (390x844), not the device's 3x: a third of the bytes and image tokens.
    image = await session.page.screenshot(type="jpeg", quality=60, full_page=False, scale="css")
    shot = Screenshot(id=session.new_screenshot_id(), image=image, caption=caption[:500], page_url=session.page.url)
    session.screenshots[shot.id] = shot
    return [
        {"type": "text", "text": json.dumps({"screenshot_id": shot.id, "url": shot.page_url})},
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(image).decode()}},
    ]


_IMPLS = {
    "goto": goto, "snapshot": snapshot, "click": click, "click_text": click_text, "select_option": select_option,
    "type_search": type_search, "scroll": scroll, "screenshot": screenshot,
}


async def execute_browser_tool(session: BrowserSession, name: str, args: dict) -> tuple[str | list[dict], bool]:
    if name not in _IMPLS:
        return f"Onbekende tool '{name}'.", True
    try:
        result = await _IMPLS[name](session, **args)
    except (ValueError, TypeError) as exc:
        return str(exc), True
    except Exception as exc:  # Playwright timeouts/interceptions are findings, not crashes
        if "intercepts pointer events" in str(exc):
            session.evidence.add(EVIDENCE_INTERCEPTED_CLICK)
        return f"{type(exc).__name__}: {str(exc)[:1500]}", True
    if isinstance(result, list):
        return result, False
    return json.dumps(result, ensure_ascii=False, default=str), False
