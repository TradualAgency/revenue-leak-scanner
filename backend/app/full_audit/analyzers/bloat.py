from app.full_audit.schemas import BloatCategory, BloatItem, CostAnalysis, ThirdPartyScripts

_BLOCKING_TIME_THRESHOLD_MS = 150.0


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
        is_hard_removable = script.necessity in ("removable", "replaceable")
        has_cost = (
            (script.monthly_cost_eur and script.monthly_cost_eur > 0)
            or script.name in cost_by_name
        )
        has_blocking = (
            script.blocking_time_ms and script.blocking_time_ms > _BLOCKING_TIME_THRESHOLD_MS
        )

        if not (is_hard_removable or has_cost or has_blocking):
            continue

        category: BloatCategory = "script"
        if is_hard_removable:
            reason = script.recommendation or (
                f"{'Remove' if script.necessity == 'removable' else 'Replace'} — {script.purpose or 'redundant'}"
            )
        else:
            parts: list[str] = []
            if script.monthly_cost_eur and script.monthly_cost_eur > 0:
                parts.append(f"€{script.monthly_cost_eur:.0f}/mo kosten")
            elif script.name in cost_by_name:
                parts.append(f"€{cost_by_name[script.name]:.0f}/mo besparing mogelijk")
            if script.blocking_time_ms and script.blocking_time_ms > _BLOCKING_TIME_THRESHOLD_MS:
                parts.append(f"{script.blocking_time_ms:.0f}ms blocking time")
            reason = (
                f"Mogelijk te vervangen — {', '.join(parts)}"
                if parts
                else (script.recommendation or script.purpose or "potentiële kostenbesparing")
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
