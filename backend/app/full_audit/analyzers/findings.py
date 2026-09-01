"""Findings registry: turns detector output into priced (or deliberately unpriced)
euro figures, with two guarantees the old model didn't have:

1. Deduplication. The same underlying issue can be detected by more than one
   analyzer (e.g. the checkout probe's own friction rule and the generic CRO scan
   both fire on "address form has >12 fields"). Registering findings under a
   stable `finding_id` means the second registration merges into the first instead
   of adding a second euro figure for the same problem.

2. Ceilings that scale instead of clamp. The old model capped a metric's loss at
   `min(monthly_revenue * X%, raw)` — once the cap bound, adding more findings
   stopped changing the total at all (3 findings and 30 findings produced an
   identical number). Here, when a funnel stage's claimed uplift exceeds its
   ceiling, every finding in that stage is scaled down by the same factor
   (so more findings still means more euros, just compressed), and a
   `ModelWarning` records that it happened — binding a ceiling is treated as a
   sign the rule table over-claimed, not as a silent fallback value.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from app.full_audit.analyzers.benchmarks import GLOBAL_UPLIFT_CEILING, STAGE_UPLIFT_CEILINGS
from app.full_audit.schemas import Confidence, FunnelModel, FunnelStage, MetricKind, ModelWarning

logger = logging.getLogger(__name__)


@dataclass
class PricedFinding:
    finding_id: str
    owning_layer: int
    stage: FunnelStage | None
    kind: MetricKind
    metric: str
    what_we_measure: str
    priority: Literal["critical", "high", "medium", "low"]
    status: Literal["good", "warning", "critical", "not-measured"]
    calculation_note: str
    signal: str | None = None
    exposure_share: float | None = None
    uplift_low: float | None = None
    uplift_high: float | None = None
    confidence: Confidence = "medium"
    citation: str | None = None
    basis: str | None = None
    verify_manually: bool = False
    pages_affected: list[str] = field(default_factory=list)
    # Set when a finding's euro range is computed upstream (e.g. ad_traffic.py's own
    # sessions x bounce-delta x CR x AOV chain) rather than via exposure_share x uplift
    # here. It still competes for its funnel stage's ceiling — a pre-priced finding
    # stacked on top of exposure*uplift findings in the same stage could otherwise
    # blow past what the stage ceiling is meant to guard against.
    fixed_low_eur: float | None = None
    fixed_high_eur: float | None = None
    sources: list[str] = field(default_factory=list)

    @property
    def is_priceable(self) -> bool:
        if self.kind != "revenue" or self.verify_manually or self.confidence == "low":
            return False
        if self.fixed_low_eur is not None and self.fixed_high_eur is not None:
            return self.stage is not None
        return (
            self.stage is not None
            and self.exposure_share is not None
            and self.uplift_low is not None
            and self.uplift_high is not None
        )


class FindingsRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, PricedFinding] = {}
        self.warnings: list[ModelWarning] = []

    def register(self, finding: PricedFinding, source: str) -> PricedFinding:
        """Idempotent: registering the same finding_id twice merges page/source
        metadata into the first registration rather than creating a second entry
        that would be priced (and counted) twice."""
        existing = self._by_id.get(finding.finding_id)
        if existing is None:
            finding.sources = [source]
            self._by_id[finding.finding_id] = finding
            return finding

        existing.pages_affected = sorted(set(existing.pages_affected) | set(finding.pages_affected))
        if source not in existing.sources:
            existing.sources.append(source)
        if (finding.uplift_high or 0) != (existing.uplift_high or 0) or (
            finding.exposure_share or 0
        ) != (existing.exposure_share or 0):
            logger.warning(
                "Duplicate finding %s registered by %s with a different uplift/exposure "
                "(%s/%s) than the existing registration by %s (%s/%s) — kept the first",
                finding.finding_id, source, finding.uplift_high, finding.exposure_share,
                existing.sources[0], existing.uplift_high, existing.exposure_share,
            )
            self.warnings.append(ModelWarning(
                kind="duplicate_finding",
                detail=(
                    f"'{finding.finding_id}' werd door meerdere detectors gemeld met "
                    f"afwijkende waarden — alleen de eerste registratie ({existing.sources[0]}) "
                    "is meegeteld."
                ),
            ))
        return existing

    def get(self, finding_id: str) -> PricedFinding | None:
        return self._by_id.get(finding_id)

    def all(self) -> list[PricedFinding]:
        return list(self._by_id.values())

    def for_layer(self, layer: int) -> list[PricedFinding]:
        return [f for f in self._by_id.values() if f.owning_layer == layer]


def price_findings(registry: FindingsRegistry, funnel: FunnelModel) -> dict[str, tuple[float, float]]:
    """Price every revenue-kind finding, applying per-stage ceilings (proportional
    scale-down, never a silent clamp) and a report-wide backstop. Returns
    finding_id -> (monthly_loss_eur_low, monthly_loss_eur_high). Findings that
    aren't priceable (cost/diagnostic/restatement kind, low confidence, or flagged
    verify_manually) are simply absent from the result."""
    findings_by_stage: dict[str, list[PricedFinding]] = {}
    raw_high_by_stage: dict[str, float] = {}

    for f in registry.all():
        if not f.is_priceable:
            continue
        findings_by_stage.setdefault(f.stage, []).append(f)
        if f.fixed_high_eur is not None:
            share_high = (f.fixed_high_eur / funnel.monthly_revenue_eur) if funnel.monthly_revenue_eur > 0 else 0.0
        else:
            share_high = f.exposure_share * f.uplift_high
        raw_high_by_stage[f.stage] = raw_high_by_stage.get(f.stage, 0.0) + share_high

    stage_factor: dict[str, float] = {}
    for stage, raw in raw_high_by_stage.items():
        ceiling = STAGE_UPLIFT_CEILINGS.get(stage)
        if ceiling and raw > ceiling > 0:
            factor = ceiling / raw
            stage_factor[stage] = factor
            registry.warnings.append(ModelWarning(
                kind="stage_ceiling_bound",
                detail=(
                    f"'{stage}': som van bevindingen ({raw:.0%} relatieve impact) overschrijdt "
                    f"het plafond voor deze stap ({ceiling:.0%}); alle bevindingen in deze stap "
                    f"zijn met factor {factor:.2f} geschaald."
                ),
            ))
        else:
            stage_factor[stage] = 1.0

    priced: dict[str, tuple[float, float]] = {}
    for stage, findings in findings_by_stage.items():
        factor = stage_factor[stage]
        for f in findings:
            if f.fixed_low_eur is not None:
                low, high = f.fixed_low_eur * factor, f.fixed_high_eur * factor
            else:
                low = funnel.monthly_revenue_eur * f.exposure_share * f.uplift_low * factor
                high = funnel.monthly_revenue_eur * f.exposure_share * f.uplift_high * factor
            priced[f.finding_id] = (low, high)

    total_high = sum(hi for _, hi in priced.values())
    global_ceiling_eur = funnel.monthly_revenue_eur * GLOBAL_UPLIFT_CEILING
    if priced and total_high > global_ceiling_eur > 0:
        g_factor = global_ceiling_eur / total_high
        registry.warnings.append(ModelWarning(
            kind="global_ceiling_bound",
            detail=(
                f"Totaal geclaimd verlies (€{total_high:,.0f}/mnd) overschrijdt het "
                f"rapportplafond van {GLOBAL_UPLIFT_CEILING:.0%} van de gemodelleerde omzet "
                f"(€{global_ceiling_eur:,.0f}/mnd); alle bedragen zijn met factor "
                f"{g_factor:.2f} geschaald."
            ),
        ))
        priced = {fid: (lo * g_factor, hi * g_factor) for fid, (lo, hi) in priced.items()}

    return priced


# --- CRO observation -> finding_id mapping -----------------------------------------
# `make_cro_observations` (cro.py) and the checkout/performance analyzers can flag the
# same underlying issue independently. Mapping a CroObservation's free text to the
# same finding_id the owning analyzer uses is what makes the registry's dedup work
# across that boundary — without it, "address form has 21 fields" would be priced
# once by the checkout analyzer and again as a "high" CRO finding.

def cro_finding_id(observation_text: str) -> str | None:
    text = observation_text.lower()
    if "lcp" in text:
        return "perf.lcp_mobile"
    if "address form" in text and "field" in text:
        return "checkout.address_fields"
    if "geen reviews" in text or "vertrouwenssignalen" in text:
        return "cro.social_proof"
    return None
