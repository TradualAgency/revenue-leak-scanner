import json
import logging
import re
import secrets
import uuid as _uuid
from datetime import UTC, datetime
from pathlib import Path

import anthropic

from app.config import settings
from app.full_audit.client_report import build_client_content, client_revenue_leak
from app.full_audit.schemas import FullAuditData

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
_SKILLS_DIR = Path(__file__).parent / "skills"

_TRAFFIC_TREND_NL = {
    "rising": "stijgend",
    "stable": "stabiel",
    "declining": "dalend",
    "unknown": "onbekend",
}


def _key() -> str:
    return _uuid.uuid4().hex[:12]


def _block_content(text: str | None) -> list[dict]:
    if not text:
        return []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    return [
        {
            "_type": "block",
            "_key": _key(),
            "style": "normal",
            "markDefs": [],
            "children": [{"_type": "span", "_key": _key(), "text": para, "marks": []}],
        }
        for para in paragraphs
    ]


def _secs(ms: float | None) -> float | None:
    if ms is None:
        return None
    return round(ms / 1000, 2)


def _slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    s = re.sub(r"^-+|-+$", "", s)
    return s


def _prose_payload(audit: FullAuditData) -> dict:
    """What the prose model gets to read. Everything it writes lands in the client's
    Sanity page, so internal sales material (pitch copy per CEO trigger, Stack Rebuild
    pricing and payback warnings) and contact details are kept out of its input, not
    just out of the output: the revenue leak goes in as the client projection."""
    payload = audit.model_dump(
        mode="json",
        exclude={
            "contact_email": True,
            "contact_person": True,
            "sanity_export": True,
            "revenue_leak": True,
            "seranking_traffic": {"raw_response": True},
            "pipeline_warnings": True,
        },
    )
    payload["revenue_leak"] = (
        client_revenue_leak(audit.revenue_leak).model_dump(mode="json") if audit.revenue_leak else None
    )
    return payload


async def _call_prose(client: anthropic.AsyncAnthropic, audit: FullAuditData) -> dict:
    system = (_SKILLS_DIR / "sanity_export.md").read_text(encoding="utf-8")
    payload = json.dumps(_prose_payload(audit), ensure_ascii=False)
    msg = await client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": payload}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:]).strip()
    return json.loads(raw)


async def build_sanity_export(audit: FullAuditData) -> dict:
    prose: dict = {}
    if settings.ANTHROPIC_API_KEY:
        try:
            client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
            prose = await _call_prose(client, audit)
        except Exception as exc:
            logger.warning("sanity_export prose generation failed: %s", exc)

    _existing_cro_keys = {(o.page, o.observation) for o in audit.cro_observations}
    _prose_cro = [
        obs for obs in (prose.get("croObservations") or [])
        if obs.get("page") and obs.get("observation")
        and (obs["page"], obs["observation"]) not in _existing_cro_keys
    ]

    # Revenue leak, actions, roadmap, assumptions and citations come from the same
    # client projection the /revenue-leak page reads — see client_report.py.
    client = build_client_content(audit)
    now_iso = datetime.now(UTC).isoformat()
    company = audit.company_name or audit.store_url
    pa = audit.platform_architecture
    perf = audit.performance
    mobile = perf.mobile if perf else None
    tps = audit.third_party_scripts
    tdq = audit.tracking_data_quality
    cf = audit.checkout_flow
    oc = audit.owned_channels
    seo = audit.seo_health
    sec = audit.security_compliance
    ca = audit.cost_analysis

    return {
        "title": f"{company} — Audit",
        "slug": {"_type": "slug", "current": _slugify(company)},
        "password": secrets.token_hex(4),
        "scanLevel": audit.scan_level,
        "scanDate": now_iso,
        "publishedAt": now_iso,

        "clientInfo": {
            "companyName": audit.company_name,
            "storeUrl": audit.store_url,
            "industry": audit.industry,
            "contactPerson": audit.contact_person,
            "contactEmail": audit.contact_email,
        },

        "intro": _block_content(prose.get("intro")),
        "coreThesis": audit.core_thesis,
        "auditSummary": audit.audit_summary,
        "biggestTechRisk": audit.biggest_tech_risk,
        "biggestTechOpportunity": audit.biggest_tech_opportunity,
        "methodologyNote": audit.methodology_note,

        "platformArchitecture": {
            "detectedPlatform": pa.detected_platform,
            "detectionConfidence": pa.detection_confidence,
            "detectionEvidence": pa.detection_evidence,
            "hosting": pa.hosting,
            "hostingDetectionEvidence": pa.hosting_detection_evidence,
            "cdnDetected": pa.cdn_detected,
            "cdnEvidence": pa.cdn_evidence,
            "serverLocation": pa.server_location,
            "themeOrFramework": pa.theme_or_framework,
            "architectureType": pa.architecture_type,
            "architectureRationale": pa.architecture_rationale,
            "recommendedArchitecture": pa.recommended_architecture,
            "architectureAssessment": _block_content(prose.get("architectureAssessment")),
        } if pa else None,

        "performance": {
            "mobileLCP": _secs(mobile.lcp_ms if mobile else None),
            "mobileLCPRating": mobile.lcp_rating if mobile else None,
            "mobileINP": mobile.inp_ms if mobile else None,
            "mobileINPRating": mobile.inp_rating if mobile else None,
            "mobileCLS": mobile.cls if mobile else None,
            "mobileCLSRating": mobile.cls_rating if mobile else None,
            "mobileFCP": _secs(mobile.fcp_ms if mobile else None),
            "mobileTTFB": mobile.ttfb_ms if mobile else None,
            "lighthousePerformance": perf.lighthouse.performance if (perf and perf.lighthouse) else None,
            "lighthouseAccessibility": perf.lighthouse.accessibility if (perf and perf.lighthouse) else None,
            "lighthouseBestPractices": perf.lighthouse.best_practices if (perf and perf.lighthouse) else None,
            "lighthouseSEO": perf.lighthouse.seo if (perf and perf.lighthouse) else None,
            "desktopLCP": _secs(perf.desktop_lcp_ms if perf else None),
            "renderBlockingResources": perf.render_blocking_resources if perf else [],
            "largeImagesUncompressed": perf.large_images_uncompressed if perf else [],
            "unusedJavaScriptKb": perf.unused_javascript_kb if perf else None,
            "totalPageWeightKb": perf.total_page_weight_kb if perf else None,
            "numberOfRequests": perf.number_of_requests if perf else None,
            "notesAndDiagnosis": _block_content(prose.get("performanceNotes")),
        } if perf else None,

        "thirdPartyScripts": {
            "totalThirdPartyDomains": tps.total_third_party_domains,
            "totalThirdPartyKb": tps.total_third_party_kb,
            "totalThirdPartyBlockingMs": tps.total_third_party_blocking_ms,
            "detectedScripts": [
                {
                    "_key": _key(),
                    "name": s.name,
                    "domain": s.domain,
                    "purpose": s.purpose,
                    "sizeKb": s.size_kb,
                    "blockingTimeMs": s.blocking_time_ms,
                    "necessity": s.necessity,
                    "monthlyCostEur": s.monthly_cost_eur,
                    "recommendation": s.recommendation,
                }
                for s in tps.detected_scripts
            ],
            "dangerousPatterns": tps.dangerous_patterns,
            "notesAndDiagnosis": _block_content(prose.get("thirdPartyNotes")),
        } if tps else None,

        "trackingDataQuality": {
            "analyticsStack": tdq.analytics_stack,
            "detectionEvidence": tdq.detection_evidence,
            "pixelsHealth": tdq.pixels_health,
            "capiStatus": tdq.capi_status,
            "consentModeStatus": tdq.consent_mode_status,
            "cmpProvider": tdq.cmp_provider,
            "estAttributionLossPercent": tdq.est_attribution_loss_percent,
            "serverSideTagging": tdq.server_side_tagging,
            "duplicateTrackingDetected": tdq.duplicate_tracking_detected,
            "notesAndDiagnosis": _block_content(prose.get("trackingNotes")),
        } if tdq else None,

        "checkoutFlow": {
            "testedAsMobile": cf.tested_as_mobile,
            "fieldsInAddressForm": cf.fields_in_address_form,
            "guestCheckoutAvailable": cf.guest_checkout_available,
            "paymentMethodsOrder": cf.payment_methods_order,
            "redirectsBeforePayment": cf.redirects_before_payment,
            "errorsEncountered": cf.errors_encountered,
            "totalCheckoutTimeSeconds": cf.total_checkout_time_seconds,
            "observedFriction": [
                {
                    "_key": _key(),
                    "step": f.step,
                    "issue": f.issue,
                    "estImpact": f.est_impact,
                }
                for f in cf.observed_friction
            ],
            "postPurchaseObservations": cf.post_purchase_observations,
            "notesAndDiagnosis": _block_content(prose.get("checkoutNotes")),
        } if cf else None,

        "ownedChannels": {
            "espDetected": oc.esp_detected,
            "espDetectionEvidence": oc.esp_detection_evidence,
            "newsletterSignupTested": oc.newsletter_signup_tested,
            "smsActive": oc.sms_active,
            "notesAndDiagnosis": _block_content(prose.get("channelsNotes")),
        } if oc else None,

        "seoHealth": {
            "organicTrafficTrend": _TRAFFIC_TREND_NL.get(
                seo.organic_traffic_trend, seo.organic_traffic_trend
            ) if (seo and seo.organic_traffic_trend) else None,
            "organicTrafficSource": seo.organic_traffic_source if seo else None,
            "brandedVsNonBrandedRatio": seo.branded_vs_nonbranded_ratio if seo else None,
            "hasSchemaMarkup": seo.has_schema_markup if seo else None,
            "schemaIssues": seo.schema_issues if seo else None,
            "programmaticPagesDetected": seo.programmatic_pages_detected if seo else None,
            "programmaticQuality": seo.programmatic_quality if seo else None,
            "hreflangSetup": seo.hreflang_setup if seo else None,
            "notesAndDiagnosis": _block_content(prose.get("seoNotes")),
        } if seo else None,

        "securityCompliance": {
            "sslStatus": sec.ssl_status,
            "sslDetails": sec.ssl_details,
            "cookieBannerBehavior": sec.cookie_banner_behavior,
            "gdprConcerns": sec.gdpr_concerns,
            "pciCompliance": sec.pci_compliance,
            "notesAndDiagnosis": _block_content(prose.get("securityNotes")),
        } if sec else None,

        "costAnalysis": {
            "currentMonthlyAppCostEur": ca.current_monthly_app_cost_eur,
            "recommendedMonthlyAppCostEur": ca.recommended_monthly_app_cost_eur,
            "estMonthlySavingsEur": ca.est_monthly_savings_eur,
            "costBreakdown": [
                {
                    "_key": _key(),
                    "category": r.category,
                    "currentTool": r.current_tool,
                    "currentCost": r.current_cost,
                    "recommendedTool": r.recommended_tool,
                    "recommendedCost": r.recommended_cost,
                    "savings": r.savings,
                }
                for r in ca.cost_breakdown
            ],
            "notesAndDiagnosis": _block_content(prose.get("costNotes")),
        } if ca else None,

        "croObservations": [
            {
                "_key": _key(),
                "page": o.page,
                "observation": o.observation,
                "severity": o.severity,
                "estImpact": o.est_impact,
            }
            for o in audit.cro_observations
        ] + [
            {
                "_key": _key(),
                "page": o["page"],
                "observation": o["observation"],
                "severity": o.get("severity"),
                "estImpact": o.get("estImpact"),
            }
            for o in _prose_cro
        ],

        "bloatWhatMustGo": [
            {
                "_key": _key(),
                "item": b.item,
                "category": b.category,
                "reason": b.reason,
                "estSavingsEur": b.est_savings_eur,
                "estPerformanceGainMs": b.est_performance_gain_ms,
            }
            for b in audit.bloat_what_must_go
        ],

        "prioritizedRoadmap": [
            {
                "_key": _key(),
                "phase": r.get("phase"),
                "duration": r.get("duration"),
                "outcome": r.get("outcome"),
                "items": r.get("items", []),
            }
            for r in (prose.get("prioritizedRoadmap") or [])
        ],

        "migrationApproach": _block_content(prose.get("migrationApproach")),

        "ctaSection": {
            "heading": prose.get("ctaHeading"),
            "body": prose.get("ctaBody"),
            "primaryButtonLabel": "Plan een gesprek",
            "primaryButtonUrl": settings.CONTACT_URL,
        },

        "aiAnalysis": {
            "cro": {
                "summary": audit.ai_analysis.cro.summary,
                "topActions": audit.ai_analysis.cro.top_actions,
                "signalsUsed": audit.ai_analysis.cro.signals_used,
            } if audit.ai_analysis and audit.ai_analysis.cro else None,
            "deliverability": {
                "summary": audit.ai_analysis.deliverability.summary,
                "topActions": audit.ai_analysis.deliverability.top_actions,
                "signalsUsed": audit.ai_analysis.deliverability.signals_used,
            } if audit.ai_analysis and audit.ai_analysis.deliverability else None,
            "techArchitecture": {
                "summary": audit.ai_analysis.tech_architecture.summary,
                "topActions": audit.ai_analysis.tech_architecture.top_actions,
                "signalsUsed": audit.ai_analysis.tech_architecture.signals_used,
            } if audit.ai_analysis and audit.ai_analysis.tech_architecture else None,
            "shopifyMigration": {
                "recommendation": audit.ai_analysis.shopify_migration.recommendation,
                "summary": audit.ai_analysis.shopify_migration.summary,
                "rationale": audit.ai_analysis.shopify_migration.rationale,
                "migrationComplexity": audit.ai_analysis.shopify_migration.migration_complexity,
                "estimatedTimeline": audit.ai_analysis.shopify_migration.estimated_timeline,
                "keyWins": audit.ai_analysis.shopify_migration.key_wins,
                "keyRisks": audit.ai_analysis.shopify_migration.key_risks,
                "topActions": audit.ai_analysis.shopify_migration.top_actions,
                "signalsUsed": audit.ai_analysis.shopify_migration.signals_used,
            } if audit.ai_analysis and audit.ai_analysis.shopify_migration else None,
            "adBounceRevenue": {
                "summary": audit.ai_analysis.ad_bounce_revenue.summary,
                "topActions": audit.ai_analysis.ad_bounce_revenue.top_actions,
                "signalsUsed": audit.ai_analysis.ad_bounce_revenue.signals_used,
            } if audit.ai_analysis and audit.ai_analysis.ad_bounce_revenue else None,
            "roadmap": {
                "executiveSummary": client.roadmap.executive_summary,
                "northStarMetric": client.roadmap.north_star_metric,
                "topPriorities": client.roadmap.top_priorities,
                "quickWins": client.roadmap.quick_wins,
                "totalTimeline": client.roadmap.total_timeline,
                "signalsUsed": client.roadmap.signals_used,
                "phases": [
                    {
                        "_key": _key(),
                        "phase": p.phase,
                        "name": p.name,
                        "timeframe": p.timeframe,
                        "objective": p.objective,
                        "actions": p.actions,
                        "expectedOutcome": p.expected_outcome,
                        # Summed from the registry findings the phase resolves
                        # (attach_roadmap_impact), never an LLM estimate.
                        "estMonthlyRevenueImpactEurLow": p.est_monthly_impact_eur_low,
                        "estMonthlyRevenueImpactEurHigh": p.est_monthly_impact_eur_high,
                        "findingIds": p.finding_ids,
                        "dependencies": p.dependencies,
                    }
                    for p in client.roadmap.phases
                ],
            } if client.roadmap else None,
            "crossSectionThesis": audit.ai_analysis.cross_section_thesis if audit.ai_analysis else None,
        },

        "revenueLeak": {
            "totalMonthlyLossEur": client.revenue_leak.total_monthly_loss_eur,
            "totalAnnualLossEur": client.revenue_leak.total_annual_loss_eur,
            "directMonthlyLossEur": client.revenue_leak.direct_monthly_loss_eur,
            "directAnnualLossEur": client.revenue_leak.direct_annual_loss_eur,
            "efficiencyMonthlyUpliftEur": client.revenue_leak.efficiency_monthly_uplift_eur,
            "efficiencyAnnualUpliftEur": client.revenue_leak.efficiency_annual_uplift_eur,
            "methodologyNote": client.revenue_leak.methodology_note,
            # --- funnel-model additions (Sanity's content lake is schemaless at
            # write time, so these are safe to add; the Studio schema/template that
            # RENDERS them is a separate, external concern — not covered here) ---
            "modelVersion": client.revenue_leak.model_version,
            "totalMonthlyLossEurLow": client.revenue_leak.total_monthly_loss_eur_low,
            "totalMonthlyLossEurHigh": client.revenue_leak.total_monthly_loss_eur_high,
            "totalAnnualLossEurLow": client.revenue_leak.total_annual_loss_eur_low,
            "totalAnnualLossEurHigh": client.revenue_leak.total_annual_loss_eur_high,
            "costMonthlyEur": client.revenue_leak.cost_monthly_eur,
            "leakShareOfRevenueLow": client.revenue_leak.leak_share_of_revenue_low,
            "leakShareOfRevenueHigh": client.revenue_leak.leak_share_of_revenue_high,
            "funnel": {
                "monthlySessions": client.revenue_leak.funnel.monthly_sessions,
                "conversionRate": client.revenue_leak.funnel.conversion_rate,
                "aovEur": client.revenue_leak.funnel.aov_eur,
                "monthlyRevenueEur": client.revenue_leak.funnel.monthly_revenue_eur,
                "operatorMonthlyRevenueEur": client.revenue_leak.funnel.operator_monthly_revenue_eur,
                "dataSource": client.revenue_leak.funnel.data_source,
                "methodologyNote": client.revenue_leak.funnel.methodology_note,
            } if client.revenue_leak.funnel else None,
            "dataConflicts": [
                {
                    "_key": _key(),
                    "kind": c.kind,
                    "operatorValueEur": c.operator_value_eur,
                    "modelValueEur": c.model_value_eur,
                    "ratio": c.ratio,
                    "severity": c.severity,
                    "messageNl": c.message_nl,
                }
                for c in client.revenue_leak.data_conflicts
            ],
            "modelWarnings": [
                {"_key": _key(), "kind": w.kind, "detail": w.detail}
                for w in client.revenue_leak.model_warnings
            ],
            "layers": [
                {
                    "_key": _key(),
                    "layer": l.layer,
                    "name": l.name,
                    "coreQuestion": l.core_question,
                    "estMonthlyLossEur": l.est_monthly_loss_eur,
                    "estAnnualLossEur": l.est_annual_loss_eur,
                    "estMonthlyLossEurLow": l.est_monthly_loss_eur_low,
                    "estMonthlyLossEurHigh": l.est_monthly_loss_eur_high,
                    "estAnnualLossEurLow": l.est_annual_loss_eur_low,
                    "estAnnualLossEurHigh": l.est_annual_loss_eur_high,
                    "kind": l.kind,
                    "unpricedFindingCount": l.unpriced_finding_count,
                    "metricCount": l.metric_count,
                    "leadsTo": l.leads_to,
                    "keySignals": l.key_signals,
                    "summary": l.summary,
                    "goodSignals": l.good_signals,
                    "improvementSignals": l.improvement_signals,
                    "readinessScore": l.readiness_score,
                    "metrics": [
                        {
                            "_key": _key(),
                            "metric": m.metric,
                            "whatWeMeasure": m.what_we_measure,
                            "priority": m.priority,
                            "status": m.status,
                            "monthlyLossEur": m.monthly_loss_eur,
                            "annualLossEur": m.annual_loss_eur,
                            "monthlyLossEurLow": m.monthly_loss_eur_low,
                            "monthlyLossEurHigh": m.monthly_loss_eur_high,
                            "annualLossEurLow": m.annual_loss_eur_low,
                            "annualLossEurHigh": m.annual_loss_eur_high,
                            "confidence": m.confidence,
                            "kind": m.kind,
                            "basis": m.basis,
                            "citation": m.citation,
                            "verifyManually": m.verify_manually,
                            "pagesAffected": m.pages_affected,
                            "calculationNote": m.calculation_note,
                            "signal": m.signal,
                        }
                        for m in l.metrics
                    ],
                }
                for l in client.revenue_leak.layers
            ],
            "ceoTriggers": [
                {
                    "_key": _key(),
                    "category": t.category,
                    "kpi": t.kpi,
                    "whatCeoSees": t.what_ceo_sees,
                    "benchmark": t.benchmark,
                    "realMeaning": t.real_meaning,
                    "triggered": t.triggered,
                }
                for t in client.revenue_leak.ceo_triggers
            ],
            # No "roi": it is priced against the Stack Rebuild fee — sales material that
            # stays on the internal dashboard, not in the client's report.
        } if client.revenue_leak else None,

        # Built from the client projection (client_report.py), like the web report.
        "actions": [
            {
                "_key": _key(),
                "actionKey": a.action_key,
                "title": a.title_nl,
                "whatToDo": a.what_to_do_nl,
                "effort": a.effort,
                "effortDaysLow": a.effort_days_low,
                "effortDaysHigh": a.effort_days_high,
                "owner": a.owner,
                "monthlyImpactEurLow": a.monthly_low,
                "monthlyImpactEurHigh": a.monthly_high,
                "priced": a.priced,
                "confidence": a.confidence,
                "verifyManually": a.verify_manually,
                "remeasureMetric": a.remeasure_metric,
                "remeasureAfterDays": a.remeasure_after_days,
            }
            for a in (client.revenue_leak.actions if client.revenue_leak else [])
        ],
        "assumptions": [
            {
                "_key": _key(),
                "key": x.key,
                "label": x.label_nl,
                "value": x.value,
                "unit": x.unit,
                "source": x.source,
                "explanation": x.explanation_nl,
            }
            for x in client.assumptions
        ],
        "citations": [
            {
                "_key": _key(),
                "key": c.key,
                "source": c.source,
                "figure": c.figure_nl,
                "note": c.note_nl,
                "verified": c.verified,
            }
            for c in client.citations
        ],

        "adTrafficImpact": {
            "estPostClickBouncePct": audit.ad_traffic_impact.est_post_click_bounce_pct,
            "bounceBaselinePct": audit.ad_traffic_impact.bounce_baseline_pct,
            "estDropOffPer1000Clicks": audit.ad_traffic_impact.est_drop_off_per_1000_clicks,
            "estMonthlyLostRevenueEurLow": audit.ad_traffic_impact.est_monthly_lost_revenue_eur_low,
            "estMonthlyLostRevenueEurHigh": audit.ad_traffic_impact.est_monthly_lost_revenue_eur_high,
            "estAttributionLossPct": audit.ad_traffic_impact.est_attribution_loss_pct,
            "bounceDrivers": audit.ad_traffic_impact.bounce_drivers,
            "methodologyNote": audit.ad_traffic_impact.methodology_note,
        } if audit.ad_traffic_impact else None,
    }
