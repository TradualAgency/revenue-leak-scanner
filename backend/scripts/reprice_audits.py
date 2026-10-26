"""Re-price stored full audits with the current revenue-leak model and print the diff.

Read-only: recomputes `ad_traffic_impact` and `revenue_leak` from each audit's stored
analyzer output and business inputs, and prints old vs. new totals. Nothing is written
back. Run it after every change to the euro model to see what moved, and why, before
it reaches a client report.

    cd backend && python -m scripts.reprice_audits [--limit 50] [--audit <uuid>]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import uuid

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.full_audit.analyzers.ad_traffic import calculate_ad_traffic_impact
from app.full_audit.analyzers.revenue_leak import calculate_revenue_leak
from app.full_audit.models import FullAudit
from app.full_audit.schemas import FullAuditData


def _reprice(audit: FullAudit, data: FullAuditData):
    inputs = dict(
        annual_revenue_eur=audit.estimated_annual_revenue_eur,
        traffic=data.seranking_traffic,
        aov_override=audit.aov_eur,
        sessions_override=audit.monthly_sessions,
        cr_override_pct=audit.conversion_rate_pct,
        ad_spend_override=audit.monthly_ad_spend_eur,
        mobile_share_override_pct=audit.mobile_share_pct,
        mobile_cr_override_pct=audit.mobile_conversion_rate_pct,
    )
    ad_traffic = calculate_ad_traffic_impact(
        data.performance, data.third_party_scripts, data.tracking_data_quality,
        data.server_side_tracking, **inputs,
    )
    return calculate_revenue_leak(
        data.performance, data.third_party_scripts, data.checkout_flow,
        data.cro_observations, data.rich_results, data.product_feeds, data.accessibility,
        ad_traffic, cost=data.cost_analysis,
        shipping=data.detected_stack.shipping if data.detected_stack else None,
        catalog=data.shopify_catalog, owned=data.owned_channels, **inputs,
    )


def _range(low, high) -> str:
    if low is None and high is None:
        return "—"
    return f"€{low or 0:>9,.0f} – €{high or 0:>9,.0f}"


def _pct(old: float | None, new: float | None) -> str:
    if not old:
        return "  n/a"
    return f"{(new or 0) / old * 100 - 100:+5.0f}%"


async def main(limit: int, audit_id: str | None) -> None:
    async with AsyncSessionLocal() as db:
        query = select(FullAudit).where(FullAudit.status == "ready_for_review")
        if audit_id:
            query = query.where(FullAudit.id == uuid.UUID(audit_id))
        rows = (await db.execute(query.order_by(FullAudit.created_at.desc()).limit(limit))).scalars().all()

    old_highs, new_highs = [], []
    for audit in rows:
        try:
            data = FullAuditData.model_validate(audit.audit_data)
        except Exception as exc:  # a row too old for the current schema
            print(f"{audit.store_url:<40} skipped: {type(exc).__name__}")
            continue
        old = data.revenue_leak
        new = _reprice(audit, data)
        old_lo, old_hi = (old.total_monthly_loss_eur_low, old.total_monthly_loss_eur_high) if old else (None, None)
        if old and old_hi is None:  # v1 report: single value
            old_lo = old_hi = old.total_monthly_loss_eur
        old_cost = (old.cost_monthly_eur or 0) if old else 0
        old_highs.append(old_hi or 0)
        new_highs.append(new.total_monthly_loss_eur_high or 0)
        print(
            f"{audit.store_url:<40} {(old.model_version if old else None) or 'v1':>4} → {new.model_version}  "
            f"{_range(old_lo, old_hi)}  →  {_range(new.total_monthly_loss_eur_low, new.total_monthly_loss_eur_high)}  "
            f"{_pct(old_hi, new.total_monthly_loss_eur_high)}  "
            f"cost €{old_cost:,.0f} → €{new.cost_monthly_eur or 0:,.0f}  "
            f"[{new.data_source}]"
        )
        for w in new.model_warnings:
            print(f"{'':<42}! {w.kind}: {w.detail[:120]}")

    if old_highs:
        total_old, total_new = sum(old_highs), sum(new_highs)
        print(f"\n{len(old_highs)} audits · sum of high bounds €{total_old:,.0f} → €{total_new:,.0f} {_pct(total_old, total_new)}")


if __name__ == "__main__":
    logging.disable(logging.WARNING)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--audit", help="only this audit id")
    args = parser.parse_args()
    asyncio.run(main(args.limit, args.audit))
