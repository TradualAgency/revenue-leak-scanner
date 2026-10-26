import json
from pathlib import Path

from app.config import settings

_plugins: list[dict] | None = None


def load_known_plugins() -> list[dict]:
    global _plugins
    if _plugins is None:
        data_path = Path(__file__).parent.parent / "data" / "known_plugins.json"
        with open(data_path) as f:
            _plugins = json.load(f)
    return _plugins  # type: ignore[return-value]


def usd_list_price_to_eur(usd: float) -> float:
    """`known_plugins.json` holds app-store list prices in USD. Converted at a fixed
    rate and rounded to whole euros — the figure is shown as "±€X/mnd", an indication,
    not an invoice amount."""
    return float(round(usd * settings.USD_TO_EUR_RATE))


def get_plugin_by_slug(slug: str) -> dict | None:
    plugins = load_known_plugins()
    for plugin in plugins:
        if plugin["slug"] == slug:
            return plugin
    return None
