import json
from pathlib import Path

_plugins: list[dict] | None = None


def load_known_plugins() -> list[dict]:
    global _plugins
    if _plugins is None:
        data_path = Path(__file__).parent.parent / "data" / "known_plugins.json"
        with open(data_path) as f:
            _plugins = json.load(f)
    return _plugins  # type: ignore[return-value]


def get_plugin_by_slug(slug: str) -> dict | None:
    plugins = load_known_plugins()
    for plugin in plugins:
        if plugin["slug"] == slug:
            return plugin
    return None
