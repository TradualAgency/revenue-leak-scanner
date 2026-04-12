from bs4 import BeautifulSoup

from app.analysis.plugin_costs import load_known_plugins


def detect_plugins(html: str, headers: dict[str, str], platform: str) -> list[dict]:
    """
    Detect plugins/apps from page HTML and response headers.

    Returns a list of detected plugin dicts with detection_method and confidence.
    """
    soup = BeautifulSoup(html, "lxml")
    known_plugins = load_known_plugins()
    detected: dict[str, dict] = {}

    script_srcs = [str(tag.get("src", "")) for tag in soup.find_all("script") if tag.get("src")]
    meta_names = {str(tag.get("name", "")).lower() for tag in soup.find_all("meta") if tag.get("name")}
    html_lower = html.lower()
    header_keys = {k.lower(): v.lower() for k, v in headers.items()}

    for plugin in known_plugins:
        slug = plugin["slug"]
        plug_platform = plugin["platform"]

        if plug_platform not in (platform, "universal"):
            continue

        patterns = plugin["detection_patterns"]
        found_method = None
        confidence = "low"

        # Check script URLs
        for url_pattern in patterns.get("script_urls", []):
            if any(url_pattern.lower() in src.lower() for src in script_srcs):
                found_method = "script_tag"
                confidence = "high"
                break

        # Check meta tags
        if not found_method:
            for meta_name in patterns.get("meta_names", []):
                if meta_name.lower() in meta_names:
                    found_method = "meta_tag"
                    confidence = "high"
                    break

        # Check DOM selectors (class/id presence in HTML)
        if not found_method:
            for selector in patterns.get("dom_selectors", []):
                clean = selector.lstrip(".#")
                if clean.lower() in html_lower:
                    found_method = "dom_element"
                    confidence = "medium"
                    break

        # Check HTML comments
        if not found_method:
            for comment_text in patterns.get("html_comments", []):
                if comment_text.lower() in html_lower:
                    found_method = "dom_element"
                    confidence = "medium"
                    break

        # Check response headers
        if not found_method:
            for header_name in patterns.get("headers", []):
                if header_name.lower() in header_keys:
                    found_method = "header"
                    confidence = "high"
                    break

        if found_method and slug not in detected:
            avg_cost = (plugin["monthly_cost_low"] + plugin["monthly_cost_high"]) / 2
            detected[slug] = {
                "name": plugin["name"],
                "slug": slug,
                "platform": plug_platform,
                "estimated_monthly_cost": avg_cost,
                "detection_method": found_method,
                "confidence": confidence,
            }

    return list(detected.values())
