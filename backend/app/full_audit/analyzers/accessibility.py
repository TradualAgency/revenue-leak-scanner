import logging

from bs4 import BeautifulSoup

from app.full_audit.schemas import AccessibilityHealth, Performance

logger = logging.getLogger(__name__)


def make_accessibility_report(pages: list[dict], performance: Performance | None) -> AccessibilityHealth:
    """Synchronous rollup — runs after the parallel gather."""
    try:
        lighthouse_score = None
        if performance and performance.lighthouse:
            lighthouse_score = performance.lighthouse.accessibility

        if not pages:
            return AccessibilityHealth(lighthouse_score=lighthouse_score)

        lang_set: bool | None = None
        viewport_set: bool | None = None
        total_imgs = 0
        imgs_with_alt = 0
        landmarks: set[str] = set()

        for page in pages:
            html = page.get("html", "")
            if not html:
                continue
            try:
                soup = BeautifulSoup(html, "lxml")

                if lang_set is None:
                    html_tag = soup.find("html")
                    if html_tag and hasattr(html_tag, "get"):
                        lang_val = html_tag.get("lang")  # type: ignore[union-attr]
                        lang_set = bool(lang_val)

                if viewport_set is None:
                    viewport_set = soup.find("meta", attrs={"name": "viewport"}) is not None

                for img in soup.find_all("img"):
                    total_imgs += 1
                    if img.get("alt") is not None:
                        imgs_with_alt += 1

                for lm in ("main", "nav", "header", "footer", "aside"):
                    if soup.find(lm):
                        landmarks.add(lm)

            except Exception:
                pass

        img_alt_pct = round(imgs_with_alt / total_imgs * 100, 1) if total_imgs > 0 else None

        risks = []
        if lighthouse_score is not None and lighthouse_score < 70:
            risks.append(f"Lighthouse accessibility {lighthouse_score} — onder EU EAA drempel")
        if lang_set is False:
            risks.append("Geen lang-attribuut op <html>")
        if img_alt_pct is not None and img_alt_pct < 80:
            risks.append(f"Slechts {img_alt_pct}% van afbeeldingen heeft alt-tekst")

        return AccessibilityHealth(
            lighthouse_score=lighthouse_score,
            lang_attribute_set=lang_set,
            viewport_meta_set=viewport_set,
            img_alt_coverage_pct=img_alt_pct,
            landmarks_present=sorted(landmarks),
            eu_eaa_risk_summary="; ".join(risks) if risks else None,
        )
    except Exception as exc:
        logger.warning("accessibility rollup failed: %s", exc)
        return AccessibilityHealth()
