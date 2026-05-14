from collections import defaultdict

from app.full_audit.schemas import (
    CostAnalysis,
    CostBreakdownRow,
    PlatformArchitecture,
    ThirdPartyScripts,
)

_CATEGORY_RECOMMENDATIONS: dict[str, tuple[str, float]] = {
    "reviews": ("Judge.me", 15.0),
    "ux": ("Microsoft Clarity (free)", 0.0),
    "chat": ("Gorgias", 60.0),
    "email": ("Klaviyo", 150.0),
    "sms": ("Klaviyo SMS (bundled)", 0.0),
    "cmp": ("CookieYes", 10.0),
}


def build_cost_analysis(
    third_party: ThirdPartyScripts | None,
    platform: PlatformArchitecture | None = None,
) -> CostAnalysis | None:
    if not third_party or not third_party.detected_scripts:
        return None

    # Group scripts with cost by category
    by_category: dict[str, list] = defaultdict(list)
    for script in third_party.detected_scripts:
        if script.monthly_cost_eur and script.monthly_cost_eur > 0:
            # Find category from name (heuristic)
            category = _guess_category(script.name)
            by_category[category].append(script)

    if not by_category:
        return None

    rows: list[CostBreakdownRow] = []
    current_total = 0.0
    recommended_total = 0.0

    for category, scripts in by_category.items():
        tools = [s.name for s in scripts]
        current_cost = sum(s.monthly_cost_eur or 0 for s in scripts)
        current_total += current_cost

        rec_tool, rec_cost = _CATEGORY_RECOMMENDATIONS.get(category, (None, current_cost))
        savings = max(0.0, current_cost - rec_cost)
        recommended_total += rec_cost

        rows.append(CostBreakdownRow(
            category=category.title(),
            current_tool=", ".join(tools),
            current_cost=round(current_cost, 2),
            recommended_tool=rec_tool,
            recommended_cost=round(rec_cost, 2),
            savings=round(savings, 2) if savings > 0 else None,
        ))

    rows.sort(key=lambda r: -(r.savings or 0))
    total_savings = round(current_total - recommended_total, 2)

    return CostAnalysis(
        current_monthly_app_cost_eur=round(current_total, 2),
        recommended_monthly_app_cost_eur=round(recommended_total, 2),
        est_monthly_savings_eur=max(0.0, total_savings),
        cost_breakdown=rows,
    )


def _guess_category(name: str) -> str:
    name_lower = name.lower()
    if any(k in name_lower for k in ["review", "yotpo", "loox", "judge", "stamped", "trustpilot"]):
        return "reviews"
    if any(k in name_lower for k in ["hotjar", "clarity", "lucky orange", "mouseflow"]):
        return "ux"
    if any(k in name_lower for k in ["gorgias", "tidio", "intercom", "zendesk", "chat"]):
        return "chat"
    if any(k in name_lower for k in ["klaviyo", "mailchimp", "omnisend", "privy", "drip", "activecampaign"]):
        return "email"
    if any(k in name_lower for k in ["attentive", "recart", "postscript", "smsbump", "sms"]):
        return "sms"
    if any(k in name_lower for k in ["cookiebot", "onetrust", "cookieyes", "iubenda", "consent"]):
        return "cmp"
    return "other"
