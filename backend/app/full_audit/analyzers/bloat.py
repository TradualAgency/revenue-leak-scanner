from app.full_audit.schemas import BloatCategory, BloatItem, CostAnalysis, ThirdPartyScripts


def build_bloat_list(
    third_party: ThirdPartyScripts | None,
    cost: CostAnalysis | None,
) -> list[BloatItem]:
    if not third_party:
        return []

    items: list[BloatItem] = []
    cost_by_name: dict[str, float] = {}
    if cost:
        for row in cost.cost_breakdown:
            tools = (row.current_tool or "").split(", ")
            for tool in tools:
                if row.savings:
                    cost_by_name[tool.strip()] = row.savings

    for script in third_party.detected_scripts:
        if script.necessity not in ("removable", "replaceable"):
            continue

        category: BloatCategory = "script"
        reason = script.recommendation or (
            f"{'Remove' if script.necessity == 'removable' else 'Replace'} — {script.purpose or 'redundant'}"
        )
        est_savings = cost_by_name.get(script.name) or (
            script.monthly_cost_eur if script.monthly_cost_eur and script.monthly_cost_eur > 0 else None
        )
        est_perf_gain = script.blocking_time_ms if script.blocking_time_ms and script.blocking_time_ms > 0 else None

        items.append(BloatItem(
            item=script.name,
            category=category,
            reason=reason,
            est_savings_eur=est_savings,
            est_performance_gain_ms=est_perf_gain,
        ))

    items.sort(key=lambda i: (-(i.est_savings_eur or 0), -(i.est_performance_gain_ms or 0)))
    return items
