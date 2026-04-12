import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.pagespeed import measure_pages
from app.analysis.plugin_detector import detect_plugins
from app.analysis.revenue_calculator import calculate_revenue_loss
from app.analysis.scraper import scrape_store
from app.database import AsyncSessionLocal
from app.reports.models import DetectedPlugin, Report

logger = logging.getLogger(__name__)


async def run_analysis(
    report_id: uuid.UUID,
    store_url: str,
    platform: str,
    monthly_revenue: Decimal,
) -> None:
    """Background task: scrape, detect plugins, measure speed, calculate loss."""
    async with AsyncSessionLocal() as db:
        try:
            await _set_status(db, report_id, "processing")

            # 1. Scrape
            scrape_result = await scrape_store(store_url)
            pages = scrape_result["pages"]

            # 2. Detect plugins — aggregate across all pages
            all_plugins: dict[str, dict] = {}
            for page in pages:
                found = detect_plugins(page["html"], page["headers"], platform)
                for p in found:
                    if p["slug"] not in all_plugins:
                        all_plugins[p["slug"]] = p

            detected = list(all_plugins.values())

            # 3. PageSpeed / load time
            speed = await measure_pages(store_url, pages)
            avg_load_time_ms = speed["avg_load_time_ms"]
            performance_score = speed.get("performance_score")

            # 4. Revenue loss
            avg_load_time_seconds = avg_load_time_ms / 1000
            revenue_result = calculate_revenue_loss(monthly_revenue, avg_load_time_seconds)

            # 5. Plugin costs
            total_plugin_cost = sum(
                Decimal(str(p.get("estimated_monthly_cost") or 0)) for p in detected
            )

            # 6. Persist
            result = await db.execute(select(Report).where(Report.id == report_id))
            report = result.scalar_one()

            report.status = "completed"
            report.pages_discovered = scrape_result["pages_discovered"]
            report.avg_load_time_ms = avg_load_time_ms
            report.performance_score = performance_score
            report.estimated_monthly_loss = revenue_result["estimated_monthly_loss"]
            report.total_plugin_cost_monthly = float(total_plugin_cost)  # type: ignore[assignment]
            report.completed_at = datetime.now(UTC)
            report.report_data = {
                "store_url": store_url,
                "platform": platform,
                "pages_scraped": [p["url"] for p in pages],
                "avg_load_time_ms": avg_load_time_ms,
                "performance_score": performance_score,
                "speed_source": speed.get("source"),
                "blended_loss_rate": revenue_result["blended_loss_rate"],
                "excess_load_time": revenue_result["excess_load_time"],
                "estimated_monthly_loss": float(revenue_result["estimated_monthly_loss"]),
                "total_plugin_cost_monthly": float(total_plugin_cost),
                "plugins": detected,
            }

            # Persist detected plugins
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
            await _set_status(db, report_id, "failed")


async def _set_status(db: AsyncSession, report_id: uuid.UUID, status: str) -> None:
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if report:
        report.status = status
        await db.commit()
