import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.plugin_detector import detect_plugins
from app.analysis.scraper import scrape_store
from app.database import AsyncSessionLocal
from app.full_audit.analyzers.ad_traffic import calculate_ad_traffic_impact
from app.full_audit.analyzers.performance import analyze_performance, worst_mobile_lcp
from app.full_audit.analyzers.revenue_leak import calculate_revenue_leak
from app.full_audit.analyzers.rich_results import analyze_rich_results
from app.full_audit.analyzers.shipping import detect_shipping
from app.full_audit.analyzers.third_party import apply_psi_third_party_measurements, scan_third_party
from app.full_audit.client_report import client_assumptions
from app.full_audit.schemas import RevenueLeakReport
from app.reports.models import DetectedPlugin, Report

logger = logging.getLogger(__name__)

# The free scan used to run its own loss model (7% per second over 2.5s, a 65% mobile
# blend and a x1.2 "mobile penalty", in dollars, with a +-20% band invented at read
# time). It now runs the full audit's funnel model on the subset of analyzers a
# 30-second scan can afford, so a lead who later buys the audit sees the same
# performance findings priced the same way.


def _revenue_leak(
    performance, third_party, monthly_revenue: Decimal, monthly_traffic: int | None,
    shipping=None, rich_results=None,
) -> RevenueLeakReport:
    inputs = dict(
        annual_revenue_eur=float(monthly_revenue) * 12 if monthly_revenue else None,
        sessions_override=monthly_traffic or None,
    )
    ad_traffic = calculate_ad_traffic_impact(performance, third_party, None, None, **inputs)
    # No checkout probe here: it places a product in a real cart, and anyone can point
    # the free scan at any store. The paid audit runs it; the free scan doesn't.
    return calculate_revenue_leak(
        performance, third_party, None, [], rich_results, None, None, ad_traffic,
        shipping=shipping, **inputs,
    )


async def run_analysis(
    report_id: uuid.UUID,
    store_url: str,
    platform: str,
    monthly_revenue: Decimal,
    monthly_traffic: int | None = None,
) -> None:
    """Background task: scrape, detect plugins, measure speed, price the leak."""
    async with AsyncSessionLocal() as db:
        try:
            await _set_status(db, report_id, "processing")

            # 1. Scrape
            scrape_result = await scrape_store(store_url)
            pages = scrape_result["pages"]
            if not pages:
                if scrape_result.get("blocked_reason"):
                    raise RuntimeError(
                        f"De winkel blokkeerde de scan ({scrape_result['blocked_reason']}): we kregen "
                        "een foutpagina of botbeveiliging terug in plaats van de homepage."
                    )
                raise RuntimeError(f"Could not scrape {store_url} — site unreachable or blocked")

            # 2. Detect plugins — aggregate across all pages
            all_plugins: dict[str, dict] = {}
            for page in pages:
                found = detect_plugins(page["html"], page["headers"], platform)
                for p in found:
                    if p["slug"] not in all_plugins:
                        all_plugins[p["slug"]] = p
            detected = list(all_plugins.values())

            # 3. Speed — the full audit's PSI analyzer, minus the desktop run nothing
            # here reads (homepage + one money page, both mobile).
            performance, psi_third_party = await analyze_performance(store_url, pages, include_desktop=False)
            third_party = apply_psi_third_party_measurements(await scan_third_party(pages), psi_third_party)
            lcp_ms, lcp_source = worst_mobile_lcp(performance)
            performance_score = performance.lighthouse.performance if performance.lighthouse else None

            # 4. Revenue leak — same model, same findings, same ceilings as the full audit.
            # Shipping-cost info and structured data are read from the scraped HTML: no
            # extra requests.
            shipping = await detect_shipping(pages)
            rich_results = await analyze_rich_results(pages)
            leak = _revenue_leak(performance, third_party, monthly_revenue, monthly_traffic, shipping, rich_results)

            # 5. Plugin costs (EUR, converted from USD list prices in plugin_detector)
            total_plugin_cost = sum(
                Decimal(str(p.get("estimated_monthly_cost") or 0)) for p in detected
            )

            # 6. Persist
            result = await db.execute(select(Report).where(Report.id == report_id))
            report = result.scalar_one()

            report.status = "completed"
            report.pages_discovered = scrape_result["pages_discovered"]
            report.avg_load_time_ms = int(lcp_ms) if lcp_ms is not None else None
            report.performance_score = performance_score
            # Midpoint, for the legacy column only; the range lives in report_data.
            report.estimated_monthly_loss = leak.total_monthly_loss_eur  # type: ignore[assignment]
            report.total_plugin_cost_monthly = float(total_plugin_cost)  # type: ignore[assignment]
            report.completed_at = datetime.now(UTC)
            report.report_data = {
                "store_url": store_url,
                "platform": platform,
                "pages_scraped": [p["url"] for p in pages],
                "performance_score": performance_score,
                "lcp_ms": lcp_ms,
                "lcp_source": lcp_source,
                "total_plugin_cost_monthly": float(total_plugin_cost),
                "plugins": detected,
                "model_version": leak.model_version,
                "revenue_leak": leak.model_dump(mode="json"),
            }

            for p in detected:
                db.add(DetectedPlugin(
                    id=uuid.uuid4(),
                    report_id=report_id,
                    name=p["name"],
                    slug=p["slug"],
                    platform=p["platform"],
                    estimated_monthly_cost=Decimal(str(p.get("estimated_monthly_cost") or 0)),
                    detection_method=p["detection_method"],
                    confidence=p["confidence"],
                ))

            await db.commit()
            logger.info("Analysis completed for report %s", report_id)

        except Exception as exc:
            logger.exception("Analysis failed for report %s: %s", report_id, exc)
            try:
                await db.rollback()
            except Exception:
                pass
            try:
                async with AsyncSessionLocal() as db2:
                    result2 = await db2.execute(select(Report).where(Report.id == report_id))
                    row = result2.scalar_one_or_none()
                    if row:
                        row.status = "failed"
                        row.error_message = str(exc)[:2000]
                        await db2.commit()
            except Exception:
                pass


def build_free_scan_summary(report_data: dict) -> dict:
    """What the lead sees, from a stored v2 free scan: the leak range, the three biggest
    findings, the first actions, and the assumptions behind the euros. No CEO triggers
    and no ROI — those belong to the paid audit's conversation."""
    leak = RevenueLeakReport.model_validate(report_data["revenue_leak"])
    findings = sorted(
        (f for f in leak.findings if f.kind == "revenue"),
        key=lambda f: (not f.priced, -(f.monthly_high or 0)),
    )
    return {
        "model_version": leak.model_version,
        "estimated_monthly_loss_low": leak.total_monthly_loss_eur_low,
        "estimated_monthly_loss_high": leak.total_monthly_loss_eur_high,
        "findings": findings[:3],
        "actions": leak.actions[:3],
        "assumptions": client_assumptions(leak.funnel) if leak.funnel else [],
        "data_conflicts": leak.data_conflicts,
        "lcp_ms": report_data.get("lcp_ms"),
    }


async def _set_status(db: AsyncSession, report_id: uuid.UUID, status: str) -> None:
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if report:
        report.status = status
        await db.commit()
