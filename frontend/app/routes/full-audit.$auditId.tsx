import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router";
import { getFullAudit, getFullAuditSanityExport, getFullAuditStatus } from "~/lib/api";
import { eur, eurRange, severityByShare } from "~/lib/format";
import type {
  AccessibilityHealth,
  AdTrafficImpact,
  AiAnalysis,
  AiBloatInsight,
  DataConflict,
  MetricStatus,
  ModelWarning,
  RevenueLeakLayer,
  RevenueLeakMetric,
  RevenueLeakReport,
  BloatItem,
  CostBreakdownRow,
  CroObservation,
  DetectedScript,
  DnsEmailHealth,
  DomainHealth,
  FullAuditData,
  FullAuditStatusResponse,
  MarketplacePresence,
  MultiRegionHealth,
  ObservedFriction,
  ProductFeedHealth,
  ReturnsHealth,
  RichResultsHealth,
  ServerSideTracking,
  ShippingHealth,
  ShopifyMigrationInsight,
  SiteSearchHealth,
  VendorDetection,
} from "~/lib/types";
import Header from "~/components/Header";
import Footer from "~/components/Footer";

export function meta() {
  return [
    { title: "Full Audit Results — Tradual" },
    { name: "robots", content: "noindex,nofollow" },
  ];
}

const POLL_INTERVAL_MS = 3000;

const statusMessages = [
  "Scraping store pages...",
  "Detecting platform & CDN...",
  "Running PageSpeed analysis...",
  "Scanning third-party scripts...",
  "Analysing tracking & consent...",
  "Probing checkout flow...",
  "Detecting ESP & owned channels...",
  "Building cost analysis...",
  "Almost done...",
];

function SectionCard({ title, children, dark = false }: { title: string; children: React.ReactNode; dark?: boolean }) {
  return (
    <section
      className={`rounded-2xl p-6 ${dark ? "bg-[#1a1f2e] text-white" : "bg-white border border-gray-100 shadow-sm"}`}
    >
      <h2
        className={`text-lg font-semibold mb-4 ${dark ? "text-[#c5a96f]" : "text-gray-700"}`}
        style={{ fontFamily: "var(--font-serif)" }}
      >
        {title}
      </h2>
      {children}
    </section>
  );
}

function KV({ label, value, mono = false }: { label: string; value: React.ReactNode; mono?: boolean }) {
  if (value == null || value === "") return null;
  return (
    <div className="flex flex-col gap-0.5 py-2 border-b border-gray-100 last:border-0">
      <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">{label}</span>
      <span className={`text-sm text-gray-800 ${mono ? "font-mono" : ""}`}>{value}</span>
    </div>
  );
}

function Pill({ label, tone = "neutral" }: { label: string; tone?: "good" | "warn" | "bad" | "neutral" | "gold" }) {
  const colors = {
    good: "bg-emerald-50 text-emerald-700",
    warn: "bg-yellow-50 text-yellow-700",
    bad: "bg-red-50 text-red-700",
    neutral: "bg-gray-100 text-gray-600",
    gold: "bg-[#c5a96f]/15 text-[#9a7a4a]",
  };
  return (
    <span className={`inline-block text-xs font-semibold px-2 py-0.5 rounded-full ${colors[tone]}`}>{label}</span>
  );
}

function ratingTone(r: string | null | undefined): "good" | "warn" | "bad" | "neutral" {
  if (!r) return "neutral";
  if (r === "good") return "good";
  if (r === "needs-improvement") return "warn";
  if (r === "poor") return "bad";
  return "neutral";
}

function healthTone(h: string | null | undefined): "good" | "warn" | "bad" | "neutral" {
  if (!h) return "neutral";
  if (h === "healthy") return "good";
  if (h === "partial" || h === "to-validate") return "warn";
  if (h === "missing") return "bad";
  return "neutral";
}

function necessityTone(n: string | null | undefined): "good" | "warn" | "bad" | "neutral" {
  if (!n) return "neutral";
  if (n === "critical") return "good";
  if (n === "useful") return "neutral";
  if (n === "replaceable") return "warn";
  if (n === "removable") return "bad";
  return "neutral";
}

function severityTone(s: string): "good" | "warn" | "bad" | "neutral" {
  if (s === "high") return "bad";
  if (s === "medium") return "warn";
  return "neutral";
}

function PlatformSection({ data }: { data: NonNullable<FullAuditData["platform_architecture"]> }) {
  return (
    <SectionCard title="Platform & Architectuur" dark>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        <div>
          <p className="text-xs font-medium text-white/50 uppercase tracking-wide mb-2">Gedetecteerd</p>
          <KV label="Platform" value={data.detected_platform} />
          <KV label="Hosting" value={data.hosting} />
          <KV label="CDN" value={data.cdn_detected} />
          <KV label="Architectuur" value={data.architecture_type} />
          {data.detection_confidence && (
            <div className="mt-2">
              <Pill
                label={data.detection_confidence}
                tone={data.detection_confidence === "confirmed" ? "good" : "warn"}
              />
            </div>
          )}
        </div>
        <div>
          <p className="text-xs font-medium text-white/50 uppercase tracking-wide mb-2">Aanbevolen</p>
          <KV label="Architectuur" value={data.recommended_architecture} />
          {data.architecture_assessment && (
            <p className="text-xs text-white/60 mt-2 leading-relaxed">{data.architecture_assessment}</p>
          )}
        </div>
      </div>
      {data.detection_evidence && (
        <details className="mt-4 text-xs">
          <summary className="text-[#c5a96f] cursor-pointer">Hoe weten we dit?</summary>
          <p className="mt-2 font-mono text-white/60 break-all">{data.detection_evidence}</p>
        </details>
      )}
    </SectionCard>
  );
}

function PerformanceSection({ data }: { data: NonNullable<FullAuditData["performance"]> }) {
  const m = data.mobile;
  return (
    <SectionCard title="Performance">
      {m && (
        <div className="grid grid-cols-3 gap-3 mb-5">
          {m.lcp_ms != null && (
            <div className="bg-[#FAFAF8] rounded-xl p-3 text-center border border-gray-100">
              <div className="text-xl font-semibold text-gray-900">{(m.lcp_ms / 1000).toFixed(1)}s</div>
              <div className="text-xs text-gray-400 mt-0.5">LCP</div>
              {m.lcp_rating && <Pill label={m.lcp_rating} tone={ratingTone(m.lcp_rating)} />}
            </div>
          )}
          {m.inp_ms != null && (
            <div className="bg-[#FAFAF8] rounded-xl p-3 text-center border border-gray-100">
              <div className="text-xl font-semibold text-gray-900">{m.inp_ms}ms</div>
              <div className="text-xs text-gray-400 mt-0.5">INP</div>
              {m.inp_rating && <Pill label={m.inp_rating} tone={ratingTone(m.inp_rating)} />}
            </div>
          )}
          {m.cls != null && (
            <div className="bg-[#FAFAF8] rounded-xl p-3 text-center border border-gray-100">
              <div className="text-xl font-semibold text-gray-900">{m.cls.toFixed(3)}</div>
              <div className="text-xs text-gray-400 mt-0.5">CLS</div>
              {m.cls_rating && <Pill label={m.cls_rating} tone={ratingTone(m.cls_rating)} />}
            </div>
          )}
        </div>
      )}
      {data.lighthouse && (
        <div className="mb-4">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Mobiel</p>
          <div className="grid grid-cols-4 gap-2">
            {(["performance", "accessibility", "best_practices", "seo"] as const).map((key) => {
              const val = data.lighthouse![key];
              return (
                <div key={key} className="bg-[#FAFAF8] rounded-lg p-2 text-center border border-gray-100">
                  <div className={`text-lg font-semibold ${val != null && val < 50 ? "text-red-500" : val != null && val < 90 ? "text-yellow-600" : "text-emerald-600"}`}>
                    {val ?? "—"}
                  </div>
                  <div className="text-xs text-gray-400 capitalize">{key.replace("_", " ")}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
      {data.desktop_lighthouse && (
        <div className="mb-4">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Desktop</p>
          <div className="grid grid-cols-4 gap-2">
            {(["performance", "accessibility", "best_practices", "seo"] as const).map((key) => {
              const val = data.desktop_lighthouse![key];
              return (
                <div key={key} className="bg-[#FAFAF8] rounded-lg p-2 text-center border border-gray-100">
                  <div className={`text-lg font-semibold ${val != null && val < 50 ? "text-red-500" : val != null && val < 90 ? "text-yellow-600" : "text-emerald-600"}`}>
                    {val ?? "—"}
                  </div>
                  <div className="text-xs text-gray-400 capitalize">{key.replace("_", " ")}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
      {data.render_blocking_resources.length > 0 && (
        <div className="mb-3">
          <p className="text-xs font-semibold text-red-500 uppercase tracking-wide mb-1">Render-blocking</p>
          <ul className="flex flex-col gap-1">
            {data.render_blocking_resources.map((r) => (
              <li key={r} className="text-xs font-mono text-gray-600 truncate">{r}</li>
            ))}
          </ul>
        </div>
      )}
      {(data.tbt_ms != null || data.speed_index_ms != null || data.tti_ms != null || data.desktop_lcp_ms != null) && (
        <div className="grid grid-cols-4 gap-2 mb-4">
          {data.tbt_ms != null && (
            <div className="bg-[#FAFAF8] rounded-lg p-2 text-center border border-gray-100">
              <div className={`text-lg font-semibold ${data.tbt_ms > 600 ? "text-red-500" : data.tbt_ms > 200 ? "text-yellow-600" : "text-emerald-600"}`}>{Math.round(data.tbt_ms)}ms</div>
              <div className="text-xs text-gray-400 mt-0.5">TBT</div>
            </div>
          )}
          {data.speed_index_ms != null && (
            <div className="bg-[#FAFAF8] rounded-lg p-2 text-center border border-gray-100">
              <div className={`text-lg font-semibold ${data.speed_index_ms > 4300 ? "text-red-500" : data.speed_index_ms > 1800 ? "text-yellow-600" : "text-emerald-600"}`}>{(data.speed_index_ms / 1000).toFixed(1)}s</div>
              <div className="text-xs text-gray-400 mt-0.5">Speed Index</div>
            </div>
          )}
          {data.tti_ms != null && (
            <div className="bg-[#FAFAF8] rounded-lg p-2 text-center border border-gray-100">
              <div className={`text-lg font-semibold ${data.tti_ms > 7300 ? "text-red-500" : data.tti_ms > 3800 ? "text-yellow-600" : "text-emerald-600"}`}>{(data.tti_ms / 1000).toFixed(1)}s</div>
              <div className="text-xs text-gray-400 mt-0.5">TTI</div>
            </div>
          )}
          {data.desktop_lcp_ms != null && (
            <div className="bg-[#FAFAF8] rounded-lg p-2 text-center border border-gray-100">
              <div className={`text-lg font-semibold ${data.desktop_lcp_ms > 4000 ? "text-red-500" : data.desktop_lcp_ms > 2500 ? "text-yellow-600" : "text-emerald-600"}`}>{(data.desktop_lcp_ms / 1000).toFixed(1)}s</div>
              <div className="text-xs text-gray-400 mt-0.5">LCP Desktop</div>
            </div>
          )}
        </div>
      )}
      <div className="flex gap-4 flex-wrap text-sm">
        {data.total_page_weight_kb != null && <span className="text-gray-500">Page weight: <b className="text-gray-800">{data.total_page_weight_kb}KB</b></span>}
        {data.unused_javascript_kb != null && <span className="text-gray-500">Unused JS: <b className="text-red-500">{data.unused_javascript_kb}KB</b></span>}
        {data.number_of_requests != null && <span className="text-gray-500">Requests: <b className="text-gray-800">{data.number_of_requests}</b></span>}
      </div>
      {data.money_page_url && (
        <div className="mt-4 pt-4 border-t border-gray-100">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
            {data.money_page_type === "pdp" ? "Productpagina" : "Collectiepagina"} (echte omzetpagina, niet de homepage)
          </p>
          <div className="grid grid-cols-2 gap-3 mb-2">
            {data.money_page_lcp_ms != null && (
              <div className="bg-[#FAFAF8] rounded-lg p-2 text-center border border-gray-100">
                <div className={`text-lg font-semibold ${data.money_page_lcp_ms > 4000 ? "text-red-500" : data.money_page_lcp_ms > 2500 ? "text-yellow-600" : "text-emerald-600"}`}>{(data.money_page_lcp_ms / 1000).toFixed(1)}s</div>
                <div className="text-xs text-gray-400 mt-0.5">
                  LCP {data.money_page_lcp_source === "field" ? "(real users)" : data.money_page_lcp_source === "lab" ? "(lab)" : ""}
                </div>
              </div>
            )}
            {data.money_page_lighthouse?.performance != null && (
              <div className="bg-[#FAFAF8] rounded-lg p-2 text-center border border-gray-100">
                <div className={`text-lg font-semibold ${data.money_page_lighthouse.performance < 50 ? "text-red-500" : data.money_page_lighthouse.performance < 90 ? "text-yellow-600" : "text-emerald-600"}`}>{data.money_page_lighthouse.performance}</div>
                <div className="text-xs text-gray-400 mt-0.5">Performance</div>
              </div>
            )}
          </div>
          <p className="text-xs text-gray-400 font-mono truncate">{data.money_page_url}</p>
        </div>
      )}
      {data.notes && <p className="text-xs text-gray-400 mt-3 italic">{data.notes}</p>}
    </SectionCard>
  );
}

function ThirdPartySection({ data }: { data: NonNullable<FullAuditData["third_party_scripts"]> }) {
  return (
    <SectionCard title="Third-party Scripts" dark>
      <div className="grid grid-cols-3 gap-3 mb-5">
        <div className="text-center">
          <div className="text-2xl font-semibold text-[#c5a96f]">{data.total_third_party_domains ?? "—"}</div>
          <div className="text-xs text-white/50 mt-0.5">Domeinen</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-semibold text-[#c5a96f]">{data.total_third_party_kb != null ? `${data.total_third_party_kb}KB` : "—"}</div>
          <div className="text-xs text-white/50 mt-0.5">Totaal gewicht</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-semibold text-[#c5a96f]">{data.total_third_party_blocking_ms != null ? `${data.total_third_party_blocking_ms}ms` : "—"}</div>
          <div className="text-xs text-white/50 mt-0.5">Blocking time</div>
        </div>
      </div>
      {data.detected_scripts.length > 0 && (
        <div className="overflow-x-auto mb-4">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-white/10">
                {["Script", "Purpose", "Size", "Blocking", "Necessity", "Cost/mo"].map((h) => (
                  <th key={h} className="text-left py-1.5 pr-3 text-white/40 font-medium uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.detected_scripts.map((s: DetectedScript) => (
                <tr key={s.name} className="border-b border-white/5 last:border-0">
                  <td className="py-2 pr-3 font-medium text-white">{s.name}</td>
                  <td className="py-2 pr-3 text-white/60">{s.purpose ?? "—"}</td>
                  <td className="py-2 pr-3 text-white/60">{s.size_kb != null ? `${s.size_kb}KB` : "—"}</td>
                  <td className="py-2 pr-3 text-white/60">{s.blocking_time_ms != null ? `${s.blocking_time_ms}ms` : "—"}</td>
                  <td className="py-2 pr-3">{s.necessity && <Pill label={s.necessity} tone={necessityTone(s.necessity)} />}</td>
                  <td className="py-2 text-white/60">{s.monthly_cost_eur != null ? `€${s.monthly_cost_eur}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.dangerous_patterns.length > 0 && (
        <div className="bg-red-900/20 border border-red-500/20 rounded-lg p-3">
          <p className="text-xs font-semibold text-red-400 uppercase tracking-wide mb-1.5">Gevaarlijke patronen</p>
          <ul className="flex flex-col gap-1">
            {data.dangerous_patterns.map((p) => (
              <li key={p} className="text-xs text-red-300">{p}</li>
            ))}
          </ul>
        </div>
      )}
    </SectionCard>
  );
}

function TrackingSection({ data }: { data: NonNullable<FullAuditData["tracking_data_quality"]> }) {
  return (
    <SectionCard title="Tracking & Data Kwaliteit">
      {data.est_attribution_loss_percent != null && (
        <div className="mb-4 text-center bg-[#FAFAF8] rounded-xl p-4 border border-gray-100">
          <div className="text-4xl font-semibold text-[#c5a96f]">{data.est_attribution_loss_percent}%</div>
          <div className="text-xs text-gray-400 mt-1">Geschatte attribution loss</div>
        </div>
      )}
      <KV label="Analytics stack" value={data.analytics_stack} />
      <div className="flex gap-2 flex-wrap py-2 border-b border-gray-100">
        {data.pixels_health && <Pill label={`Pixels: ${data.pixels_health}`} tone={healthTone(data.pixels_health)} />}
        {data.consent_mode_status && (
          <Pill
            label={`Consent Mode: ${data.consent_mode_status}`}
            tone={data.consent_mode_status === "v2-correct" ? "good" : data.consent_mode_status === "none" ? "bad" : "warn"}
          />
        )}
        {data.server_side_tagging && (
          <Pill
            label={`sGTM: ${data.server_side_tagging}`}
            tone={data.server_side_tagging === "yes" ? "good" : "neutral"}
          />
        )}
      </div>
      <KV label="CMP provider" value={data.cmp_provider} />
      {data.duplicate_tracking_detected && (
        <p className="text-xs text-red-500 font-medium mt-2">Dubbele tracking containers gedetecteerd</p>
      )}
      {data.notes && <p className="text-xs text-gray-400 mt-3 italic">{data.notes}</p>}
    </SectionCard>
  );
}

function CheckoutSection({ data }: { data: NonNullable<FullAuditData["checkout_flow"]> }) {
  return (
    <SectionCard title="Checkout Flow (mystery shop)">
      {data.probe_status === "unreachable" ? (
        <p className="text-xs text-amber-600 mb-4">
          Checkout niet bereikbaar voor outside-only meting — geen bestelbaar product gevonden, of add-to-cart/checkout is mislukt.
        </p>
      ) : (
        <p className="text-xs text-gray-500 italic mb-4">
          Product daadwerkelijk in de winkelmand gelegd en doorgestroomd naar checkout — zonder af te rekenen.
        </p>
      )}
      <div className="grid grid-cols-3 gap-3 mb-4">
        {data.fields_in_address_form != null && (
          <div className="bg-[#FAFAF8] rounded-xl p-3 text-center border border-gray-100">
            <div className={`text-xl font-semibold ${data.fields_in_address_form > 12 ? "text-red-500" : "text-gray-900"}`}>{data.fields_in_address_form}</div>
            <div className="text-xs text-gray-400 mt-0.5">Adresvelden</div>
          </div>
        )}
        {data.redirects_before_payment != null && (
          <div className="bg-[#FAFAF8] rounded-xl p-3 text-center border border-gray-100">
            <div className="text-xl font-semibold text-gray-900">{data.redirects_before_payment}</div>
            <div className="text-xs text-gray-400 mt-0.5">Redirects</div>
          </div>
        )}
        {data.total_checkout_time_seconds != null && (
          <div className="bg-[#FAFAF8] rounded-xl p-3 text-center border border-gray-100">
            <div className="text-xl font-semibold text-gray-900">{data.total_checkout_time_seconds}s</div>
            <div className="text-xs text-gray-400 mt-0.5">Probe tijd</div>
          </div>
        )}
      </div>
      {data.guest_checkout_available != null && (
        <div className="flex items-center gap-2 mb-3">
          <span className={`text-sm font-medium ${data.guest_checkout_available ? "text-emerald-600" : "text-red-500"}`}>
            {data.guest_checkout_available ? "✓ Guest checkout beschikbaar" : "✗ Geen guest checkout gedetecteerd"}
          </span>
        </div>
      )}
      {data.payment_methods_order.length > 0 && (
        <KV label="Betaalmethoden (volgorde)" value={data.payment_methods_order.join(", ")} />
      )}
      {data.express_checkout_methods.length > 0 && (
        <KV label="Express checkout" value={data.express_checkout_methods.join(", ")} />
      )}
      {data.observed_friction.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Friction punten</p>
          <div className="flex flex-col gap-2">
            {data.observed_friction.map((f: ObservedFriction) => (
              <div key={f.step} className="border border-gray-100 rounded-lg p-3">
                <div className="text-xs font-semibold text-gray-500">{f.step}</div>
                <div className="text-sm text-gray-700 mt-0.5">{f.issue}</div>
                {f.est_impact && <div className="text-xs text-gray-400 italic mt-0.5">{f.est_impact}</div>}
              </div>
            ))}
          </div>
        </div>
      )}
      {data.errors_encountered.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-semibold text-red-500 uppercase tracking-wide mb-1">Fouten</p>
          <ul className="flex flex-col gap-1">
            {data.errors_encountered.map((e) => (
              <li key={e} className="text-xs text-red-500">{e}</li>
            ))}
          </ul>
        </div>
      )}
    </SectionCard>
  );
}

function OwnedChannelsSection({ data }: { data: NonNullable<FullAuditData["owned_channels"]> }) {
  return (
    <SectionCard title="Owned Channels">
      {data.esp_detected && (
        <>
          <KV label="ESP gedetecteerd" value={data.esp_detected} />
          {data.esp_detection_evidence && (
            <details className="mt-1 mb-2 text-xs">
              <summary className="text-[#c5a96f] cursor-pointer">Hoe weten we dit?</summary>
              <p className="mt-1 font-mono text-gray-500 break-all">{data.esp_detection_evidence}</p>
            </details>
          )}
        </>
      )}
      <div className="flex gap-2 flex-wrap mt-2">
        <Pill
          label={`Newsletter signup: ${data.newsletter_signup_tested ? "gevonden" : "niet gevonden"}`}
          tone={data.newsletter_signup_tested ? "good" : "warn"}
        />
        {data.sms_active != null && (
          <Pill label={`SMS: ${data.sms_active ? "actief" : "niet gedetecteerd"}`} tone={data.sms_active ? "good" : "neutral"} />
        )}
      </div>
      {data.notes && <p className="text-xs text-gray-400 mt-3 italic">{data.notes}</p>}
    </SectionCard>
  );
}

function SecuritySection({ data }: { data: NonNullable<FullAuditData["security_compliance"]> }) {
  return (
    <SectionCard title="Security & Compliance">
      <div className="flex gap-2 flex-wrap mb-3">
        {data.ssl_status && (
          <Pill
            label={`SSL: ${data.ssl_status}`}
            tone={data.ssl_status === "valid" ? "good" : "bad"}
          />
        )}
        {data.pci_compliance && (
          <Pill
            label={`PCI: ${data.pci_compliance}`}
            tone={data.pci_compliance === "likely" ? "good" : "warn"}
          />
        )}
      </div>
      {data.ssl_details && <p className="text-xs text-gray-500 mb-2">{data.ssl_details}</p>}
      <KV label="Cookie banner" value={data.cookie_banner_behavior} />
      {data.gdpr_concerns.length > 0 && (
        <div className="mt-2">
          <p className="text-xs font-semibold text-red-500 uppercase tracking-wide mb-1">GDPR zorgen</p>
          <ul className="flex flex-col gap-1">
            {data.gdpr_concerns.map((c) => (
              <li key={c} className="text-xs text-red-500">{c}</li>
            ))}
          </ul>
        </div>
      )}
    </SectionCard>
  );
}

function CostSection({ data }: { data: NonNullable<FullAuditData["cost_analysis"]> }) {
  return (
    <SectionCard title="Cost Analysis" dark>
      <div className="grid grid-cols-3 gap-4 mb-5 text-center">
        <div>
          <div className="text-3xl font-semibold text-white/70">
            {data.current_monthly_app_cost_eur != null ? `€${data.current_monthly_app_cost_eur}` : "—"}
          </div>
          <div className="text-xs text-white/40 mt-0.5">Huidige kosten/maand</div>
        </div>
        <div>
          <div className="text-3xl font-semibold text-[#c5a96f]">
            {data.recommended_monthly_app_cost_eur != null ? `€${data.recommended_monthly_app_cost_eur}` : "—"}
          </div>
          <div className="text-xs text-white/40 mt-0.5">Aanbevolen/maand</div>
        </div>
        <div>
          <div className="text-3xl font-semibold text-emerald-400">
            {data.est_monthly_savings_eur != null ? `€${data.est_monthly_savings_eur}` : "—"}
          </div>
          <div className="text-xs text-white/40 mt-0.5">Besparing/maand</div>
        </div>
      </div>
      {data.cost_breakdown.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-white/10">
                {["Categorie", "Huidige tool", "Nu", "Aanbevolen", "Prijs", "Besparing"].map((h) => (
                  <th key={h} className="text-left py-1.5 pr-3 text-white/40 font-medium uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.cost_breakdown.map((r: CostBreakdownRow) => (
                <tr key={r.category} className="border-b border-white/5 last:border-0">
                  <td className="py-2 pr-3 font-medium text-white">{r.category}</td>
                  <td className="py-2 pr-3 text-white/60">{r.current_tool ?? "—"}</td>
                  <td className="py-2 pr-3 text-white/60">{r.current_cost != null ? `€${r.current_cost}` : "—"}</td>
                  <td className="py-2 pr-3 text-white/60">{r.recommended_tool ?? "—"}</td>
                  <td className="py-2 pr-3 text-white/60">{r.recommended_cost != null ? `€${r.recommended_cost}` : "—"}</td>
                  <td className="py-2 text-emerald-400 font-medium">{r.savings != null ? `€${r.savings}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}

function CroSection({ items }: { items: CroObservation[] }) {
  if (!items.length) return null;
  return (
    <SectionCard title="CRO Observaties (bijrol)">
      <p className="text-xs text-gray-400 italic mb-4">
        Dit zijn observaties, geen aanbevelingen. CRO-uitvoering doet je CRO specialist.
      </p>
      <div className="flex flex-col">
        {items.map((o, i) => (
          <div key={i} className="border-t border-gray-100 py-3 first:border-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-medium text-gray-400">{o.page}</span>
              <Pill label={o.severity} tone={severityTone(o.severity)} />
            </div>
            <p className="text-sm text-gray-700">{o.observation}</p>
            {o.est_impact && <p className="text-xs text-gray-400 italic mt-0.5">{o.est_impact}</p>}
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

const SHOPIFY_RECOMMENDATION_TONE: Record<string, { label: string; color: string }> = {
  aanbevolen: { label: "Aanbevolen", color: "bg-green-500/20 text-green-300 border border-green-500/30" },
  overwegen: { label: "Overwegen", color: "bg-amber-500/20 text-amber-300 border border-amber-500/30" },
  "niet-nu": { label: "Niet nu", color: "bg-red-500/20 text-red-300 border border-red-500/30" },
  "af-te-raden": { label: "Af te raden", color: "bg-red-500/20 text-red-300 border border-red-500/30" },
  "niet-van-toepassing": { label: "Al op Shopify", color: "bg-white/10 text-white/50 border border-white/10" },
};

function ShopifyMigrationCard({ insight }: { insight: ShopifyMigrationInsight }) {
  const tone = SHOPIFY_RECOMMENDATION_TONE[insight.recommendation] ?? {
    label: insight.recommendation,
    color: "bg-white/10 text-white/50 border border-white/10",
  };
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-[#c5a96f]">Shopify-migratie</h3>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${tone.color}`}>{tone.label}</span>
      </div>
      <p className="text-sm text-white/80 leading-relaxed mb-3">{insight.summary}</p>
      <p className="text-xs text-white/60 leading-relaxed mb-3">{insight.rationale}</p>
      {(insight.key_wins.length > 0 || insight.key_risks.length > 0) && (
        <div className="grid grid-cols-2 gap-3 mb-3">
          {insight.key_wins.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-white/40 uppercase tracking-wide mb-1.5">Kansen</p>
              <ul className="flex flex-col gap-1">
                {insight.key_wins.map((w, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-xs text-green-300/80">
                    <span className="shrink-0 mt-0.5">+</span>{w}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {insight.key_risks.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-white/40 uppercase tracking-wide mb-1.5">Risico's</p>
              <ul className="flex flex-col gap-1">
                {insight.key_risks.map((r, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-xs text-red-300/80">
                    <span className="shrink-0 mt-0.5">!</span>{r}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      {insight.top_actions.length > 0 && (
        <div className="mb-3">
          <p className="text-xs font-semibold text-white/40 uppercase tracking-wide mb-2">Acties</p>
          <ul className="flex flex-col gap-1.5">
            {insight.top_actions.map((a, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-white/70">
                <span className="text-[#c5a96f] mt-0.5 shrink-0">→</span>{a}
              </li>
            ))}
          </ul>
        </div>
      )}
      {insight.signals_used.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {insight.signals_used.map((s) => (
            <span key={s} className="text-xs bg-white/10 text-white/50 px-2 py-0.5 rounded-full">{s}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function MetricPriorityBadge({ priority }: { priority: RevenueLeakMetric["priority"] }) {
  const colors: Record<RevenueLeakMetric["priority"], string> = {
    critical: "bg-red-500/20 text-red-400 border-red-500/30",
    high: "bg-orange-500/15 text-orange-400 border-orange-500/30",
    medium: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
    low: "bg-white/5 text-white/30 border-white/10",
  };
  return (
    <span className={`text-[9px] uppercase font-semibold tracking-wider px-1.5 py-0.5 rounded border ${colors[priority]}`}>
      {priority}
    </span>
  );
}

function MetricStatusIcon({ status }: { status: MetricStatus }) {
  if (status === "good") return <span className="text-emerald-400 text-xs shrink-0">✓</span>;
  if (status === "warning") return <span className="text-yellow-400 text-xs shrink-0">⚠</span>;
  if (status === "critical") return <span className="text-red-400 text-xs shrink-0">✗</span>;
  return <span className="text-white/20 text-xs shrink-0">–</span>;
}

// --- v1/v2 compatibility helpers ---------------------------------------------------
// Pre-rewrite (v1) reports only carry a single `*_loss_eur` value; post-rewrite (v2)
// reports carry a real low/high range. Returning a range either way (low === high
// for v1) lets every render site use the same range-aware formatting — `eurRange`
// collapses a v1 pair back down to a single value automatically.
function metricRange(m: RevenueLeakMetric): { low: number | null; high: number | null } {
  if (m.monthly_loss_eur_low != null && m.monthly_loss_eur_high != null) {
    return { low: m.monthly_loss_eur_low, high: m.monthly_loss_eur_high };
  }
  return { low: m.monthly_loss_eur ?? null, high: m.monthly_loss_eur ?? null };
}
function layerRange(l: RevenueLeakLayer): { low: number | null; high: number | null } {
  if (l.est_monthly_loss_eur_low != null && l.est_monthly_loss_eur_high != null) {
    return { low: l.est_monthly_loss_eur_low, high: l.est_monthly_loss_eur_high };
  }
  return { low: l.est_monthly_loss_eur ?? null, high: l.est_monthly_loss_eur ?? null };
}
function layerAnnualRange(l: RevenueLeakLayer): { low: number | null; high: number | null } {
  if (l.est_annual_loss_eur_low != null && l.est_annual_loss_eur_high != null) {
    return { low: l.est_annual_loss_eur_low, high: l.est_annual_loss_eur_high };
  }
  return { low: l.est_annual_loss_eur ?? null, high: l.est_annual_loss_eur ?? null };
}
function reportMonthlyRange(data: RevenueLeakReport): { low: number; high: number } {
  if (data.total_monthly_loss_eur_low != null && data.total_monthly_loss_eur_high != null) {
    return { low: data.total_monthly_loss_eur_low, high: data.total_monthly_loss_eur_high };
  }
  const v = data.total_monthly_loss_eur || 0;
  return { low: v, high: v };
}

function DataConflictBanner({ conflicts }: { conflicts: DataConflict[] }) {
  if (conflicts.length === 0) return null;
  return (
    <div className="space-y-2 mb-4">
      {conflicts.map((c, i) => (
        <div
          key={i}
          className={`border rounded-lg p-3 ${c.severity === "critical" ? "border-red-500/40 bg-red-500/10" : "border-amber-500/40 bg-amber-500/10"}`}
        >
          <p className={`text-[11px] font-semibold uppercase tracking-wide mb-1 ${c.severity === "critical" ? "text-red-400" : "text-amber-400"}`}>
            Tegenstrijdige invoer — {c.ratio.toFixed(1)}x verschil
          </p>
          <p className="text-xs text-white/60 leading-relaxed">{c.message_nl}</p>
        </div>
      ))}
    </div>
  );
}

function ModelWarningsList({ warnings }: { warnings: ModelWarning[] }) {
  if (warnings.length === 0) return null;
  return (
    <div className="mt-3 space-y-1">
      {warnings.map((w, i) => (
        <p key={i} className="text-[10px] text-amber-400/70 leading-relaxed">⚠ {w.detail}</p>
      ))}
    </div>
  );
}

function RevenueLeakLayerRow({ layer, funnelRevenue }: { layer: RevenueLeakLayer; funnelRevenue: number | null }) {
  const [open, setOpen] = useState(false);
  const isLayer5 = layer.layer === 5;
  const { low: layerLow, high: layerHigh } = layerRange(layer);
  const hasLoss = layerLow != null && layerHigh != null;
  const isNa = !hasLoss && !isLayer5;
  const kind = layer.kind ?? "revenue";
  const hasMetrics = layer.metrics && layer.metrics.length > 0;
  const hasSignals = (layer.good_signals?.length || 0) + (layer.improvement_signals?.length || 0) > 0;
  return (
    <>
      <tr
        className={`border-b border-white/5 last:border-0 group ${(hasMetrics || hasSignals) ? "cursor-pointer hover:bg-white/[0.02]" : ""}`}
        onClick={() => (hasMetrics || hasSignals) && setOpen((o) => !o)}
      >
        <td className="py-3 pr-3 text-white/30 text-xs font-mono">{layer.layer}</td>
        <td className="py-3 pr-4">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-white">{layer.name}</span>
            {(hasMetrics || hasSignals) && (
              <span className="text-white/20 text-xs">{open ? "▲" : "▼"}</span>
            )}
          </div>
          <p className="text-xs text-white/40 mt-0.5 leading-snug max-w-[220px]">{layer.core_question}</p>
          {layer.summary && !open && (
            <p className="text-[10px] text-white/25 mt-0.5 italic">{layer.summary}</p>
          )}
        </td>
        <td className="py-3 pr-4 tabular-nums">
          {isLayer5 ? (
            layer.readiness_score != null ? (
              <div>
                <span className={`text-base font-bold ${layer.readiness_score >= 75 ? "text-emerald-400" : layer.readiness_score >= 40 ? "text-yellow-400" : "text-red-400"}`}>
                  {layer.readiness_score}/100
                </span>
                <div className="text-[10px] text-white/30 mt-0.5">gereedheid</div>
              </div>
            ) : <span className="text-xs text-white/25 italic">n.v.t.</span>
          ) : isNa ? (
            <span className="text-xs text-white/25 italic">{kind === "diagnostic" ? "diagnose" : kind === "restatement" ? "herformulering" : "n.v.t."}</span>
          ) : (
            <span className={`text-base font-bold ${kind === "cost" ? "text-amber-400" : (layerHigh || 0) > 1000 ? "text-red-400" : (layerHigh || 0) > 0 ? "text-orange-400" : "text-white/30"}`}>
              {(layerHigh || 0) === 0 ? "—" : eurRange(layerLow, layerHigh)}
            </span>
          )}
        </td>
        <td className="py-3 pr-4 tabular-nums">
          {isLayer5 ? (
            <span className="text-xs text-white/25 italic">n.v.t.</span>
          ) : isNa ? (
            <span className="text-xs text-white/25 italic">n.v.t.</span>
          ) : (
            (() => {
              const { low: aLow, high: aHigh } = layerAnnualRange(layer);
              return (
                <span className={`text-sm font-medium ${(aHigh || 0) > 12000 ? "text-red-300/70" : "text-white/40"}`}>
                  {(aHigh || 0) === 0 ? "—" : eurRange(aLow, aHigh)}
                </span>
              );
            })()
          )}
        </td>
        <td className="py-3 pr-4 text-center">
          <span className="text-xs text-white/30">
            {layer.metric_count}
            {layer.unpriced_finding_count != null && layer.unpriced_finding_count > 0 && (
              <span className="text-slate-400"> (+{layer.unpriced_finding_count} te verifiëren)</span>
            )}
          </span>
        </td>
        <td className="py-3">
          <span className="text-xs text-[#c5a96f]/70 whitespace-nowrap">{layer.leads_to}</span>
        </td>
      </tr>
      {open && (
        <>
          {/* Good / Improvement signals */}
          {hasSignals && (
            <tr className="bg-white/[0.015] border-b border-white/5">
              <td />
              <td colSpan={5} className="py-3 pl-3 pr-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {(layer.good_signals?.length || 0) > 0 && (
                    <div>
                      <p className="text-[10px] font-semibold text-emerald-400/70 uppercase tracking-wide mb-1.5">Wat goed gaat</p>
                      <ul className="flex flex-col gap-1">
                        {layer.good_signals.map((s, i) => (
                          <li key={i} className="flex items-start gap-1.5 text-[11px] text-emerald-300/70">
                            <span className="shrink-0 mt-0.5">✓</span>{s}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {(layer.improvement_signals?.length || 0) > 0 && (
                    <div>
                      <p className="text-[10px] font-semibold text-orange-400/70 uppercase tracking-wide mb-1.5">Wat beter kan</p>
                      <ul className="flex flex-col gap-1">
                        {layer.improvement_signals.map((s, i) => (
                          <li key={i} className="flex items-start gap-1.5 text-[11px] text-orange-300/70">
                            <span className="shrink-0 mt-0.5">⚠</span>{s}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </td>
            </tr>
          )}
          {/* Metric detail rows */}
          {hasMetrics && layer.metrics.map((m) => (
            <tr key={m.metric} className="bg-white/[0.01] border-b border-white/5">
              <td />
              <td className="py-2 pr-4 pl-3" colSpan={2}>
                <div className="flex items-start gap-2">
                  <MetricStatusIcon status={m.status} />
                  <MetricPriorityBadge priority={m.priority} />
                  <div>
                    <p className="text-xs font-medium text-white/70">{m.metric}</p>
                    {m.signal && <p className="text-[11px] text-white/35 mt-0.5">{m.signal}</p>}
                  </div>
                </div>
              </td>
              <td className="py-2 pr-4 tabular-nums">
                {m.verify_manually ? (
                  <span className="text-[10px] text-slate-400 italic border border-slate-500/30 rounded px-1.5 py-0.5">handmatig verifiëren</span>
                ) : (() => {
                  const { low, high } = metricRange(m);
                  if (low == null || high == null) {
                    return <span className="text-[10px] text-white/20 italic">{m.kind === "diagnostic" ? "diagnose" : m.kind === "restatement" ? "herformulering" : "strategisch"}</span>;
                  }
                  const share = funnelRevenue ? high / funnelRevenue : null;
                  const severity = severityByShare(share, 0.01, 0.03);
                  return (
                    <span className={`text-xs font-semibold ${severity === "critical" ? "text-red-400/80" : severity === "warning" ? "text-orange-400/80" : "text-emerald-400/50"}`}>
                      {high === 0 ? "✓ geen verlies" : eurRange(low, high)}
                    </span>
                  );
                })()}
              </td>
              <td colSpan={2} className="py-2 pr-3">
                <p className="text-[10px] text-white/25 leading-snug">{m.basis || m.calculation_note}</p>
              </td>
            </tr>
          ))}
        </>
      )}
    </>
  );
}

function CeoTriggersSection({ triggers }: { triggers: RevenueLeakReport["ceo_triggers"] }) {
  if (!triggers || triggers.length === 0) return null;
  const grouped = triggers.reduce<Record<string, typeof triggers>>((acc, t) => {
    if (!acc[t.category]) acc[t.category] = [];
    acc[t.category].push(t);
    return acc;
  }, {});
  const categoryOrder = ["Omzet & Groei", "Conversie & Funnel", "Kosten & Efficiëntie", "Concurrentie & Toekomst"];
  const sorted = categoryOrder.filter((c) => grouped[c]).concat(Object.keys(grouped).filter((c) => !categoryOrder.includes(c)));
  return (
    <div className="mt-6 pt-5 border-t border-white/10">
      <p className="text-xs font-semibold text-white/40 uppercase tracking-wide mb-4">CEO trigger KPIs</p>
      <div className="flex flex-col gap-5">
        {sorted.map((cat) => (
          <div key={cat}>
            <p className="text-[10px] font-semibold text-[#c5a96f]/70 uppercase tracking-wider mb-2">{cat}</p>
            <div className="flex flex-col gap-2">
              {[...grouped[cat]].sort((a, b) => (b.triggered ? 1 : 0) - (a.triggered ? 1 : 0)).map((t) => (
                <div key={t.kpi} className={`rounded-lg p-3 border ${t.triggered ? "bg-red-900/20 border-red-500/20" : "bg-white/[0.03] border-white/5"}`}>
                  <div className="flex items-start justify-between gap-3 mb-1">
                    <p className={`text-xs font-semibold ${t.triggered ? "text-red-300" : "text-white/50"}`}>{t.kpi}</p>
                    {t.triggered && <span className="shrink-0 text-[9px] uppercase font-bold bg-red-500/30 text-red-300 px-1.5 py-0.5 rounded">Actief</span>}
                  </div>
                  {t.triggered && (
                    <>
                      <p className="text-[11px] text-white/60 leading-snug mb-1.5">{t.real_meaning}</p>
                      <p className="text-[11px] text-[#c5a96f]/70 italic leading-snug">{t.tradual_pitch}</p>
                    </>
                  )}
                  {!t.triggered && (
                    <p className="text-[10px] text-white/25 leading-snug">{t.alarm_signal}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function RevenueLeakSection({ data }: { data: RevenueLeakReport }) {
  const isV2 = data.model_version != null;
  const { low: totalLow, high: totalHigh } = reportMonthlyRange(data);
  const totalAnnual = data.total_annual_loss_eur_low != null && data.total_annual_loss_eur_high != null
    ? { low: data.total_annual_loss_eur_low, high: data.total_annual_loss_eur_high }
    : { low: data.total_annual_loss_eur || 0, high: data.total_annual_loss_eur || 0 };
  const funnelRevenue = data.funnel?.monthly_revenue_eur ?? null;
  const conflicts = data.data_conflicts ?? [];
  const warnings = data.model_warnings ?? [];

  // v1 legacy split (efficiency-as-upside framing) — kept only for reports computed
  // before the rewrite. v2 reports set `efficiency_monthly_uplift_eur` to a fixed
  // 0.0 (layer 4 no longer claims separate upside), so this split would otherwise
  // always render a redundant "+€0 extra potentieel" line.
  const direct = data.direct_monthly_loss_eur ?? null;
  const efficiency = data.efficiency_monthly_uplift_eur ?? null;
  const showLegacySplit = !isV2 && direct != null && efficiency != null && efficiency > 0;

  return (
    <SectionCard title="Revenue Leak — Wat kost het je?" dark>
      <DataConflictBanner conflicts={conflicts} />
      {totalHigh > 0 && (
        <div className="mb-6 pb-5 border-b border-white/10">
          {showLegacySplit ? (
            <div className="flex flex-col gap-1.5 mb-3">
              <div className="flex items-baseline justify-between pb-1">
                <span className="text-xs font-semibold text-white/60">Directe lek nu (Laag 1+2+3)</span>
                <span className="text-xl font-bold text-red-400">{eur(direct)}<span className="text-xs font-normal text-white/30">/mnd</span></span>
              </div>
              <div className="flex items-baseline justify-between pt-2 border-t border-white/10 mt-1">
                <span className="text-xs text-white/40">+ extra potentieel bij snellere winkel (Laag 4 — géén huidig verlies)</span>
                <span className="text-base font-semibold text-yellow-400">{eur(efficiency)}<span className="text-xs font-normal text-white/30">/mnd</span></span>
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap gap-6">
              <div>
                <p className="text-3xl font-bold text-red-400">{eurRange(totalLow, totalHigh)}</p>
                <p className="text-xs text-white/40 mt-1">geschat verlies per maand{isV2 ? " (laag 1+3)" : ""}</p>
              </div>
              <div>
                <p className="text-3xl font-bold text-red-300/70">{eurRange(totalAnnual.low, totalAnnual.high)}</p>
                <p className="text-xs text-white/40 mt-1">per jaar</p>
              </div>
              {isV2 && data.cost_monthly_eur != null && data.cost_monthly_eur > 0 && (
                <div>
                  <p className="text-3xl font-bold text-amber-400">{eur(data.cost_monthly_eur)}</p>
                  <p className="text-xs text-white/40 mt-1">tool-kosten per maand (laag 2)</p>
                </div>
              )}
            </div>
          )}
          {data.roi && (
            <div className="flex flex-wrap gap-4 mt-3 pt-3 border-t border-white/5 text-xs text-white/40">
              {(() => {
                const best = data.roi.payback_months_best ?? data.roi.payback_months;
                const worst = data.roi.payback_months_worst ?? data.roi.payback_months;
                if (best == null || worst == null) return null;
                return (
                  <span>
                    Terugverdientijd Stack Rebuild:{" "}
                    <b className="text-white/70">{best === worst ? `${best}` : `${best}–${worst}`} maanden</b>
                  </span>
                );
              })()}
              {(() => {
                const low = data.roi.year_one_net_return_eur_low ?? data.roi.year_one_net_return_eur;
                const high = data.roi.year_one_net_return_eur_high ?? data.roi.year_one_net_return_eur;
                if (high <= 0) return null;
                return (
                  <span>
                    Netto jaar 1: <b className={low < 0 ? "text-amber-400" : "text-emerald-400"}>{eurRange(low, high)}</b>
                    {low < 0 && " (bij ondergrens niet terugverdiend)"}
                  </span>
                );
              })()}
            </div>
          )}
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-white/10">
              {["#", "Naam & Kernvraag", "Verlies/mnd", "Verlies/jaar", "Metrics", "Leidt naar"].map((h) => (
                <th key={h} className="text-left py-2 pr-3 text-white/30 font-medium uppercase tracking-wide text-[10px]">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.layers.map((layer) => (
              <RevenueLeakLayerRow key={layer.layer} layer={layer} funnelRevenue={funnelRevenue} />
            ))}
          </tbody>
        </table>
      </div>
      <ModelWarningsList warnings={warnings} />
      {data.methodology_note && (
        <p className="text-xs text-white/20 italic mt-4">{data.methodology_note}</p>
      )}
      {data.funnel?.methodology_note && (
        <p className="text-xs text-white/20 italic mt-1">{data.funnel.methodology_note}</p>
      )}
      {data.ceo_triggers && data.ceo_triggers.length > 0 && (
        <CeoTriggersSection triggers={data.ceo_triggers} />
      )}
    </SectionCard>
  );
}

function AdTrafficImpactSection({ data }: { data: AdTrafficImpact }) {
  const hasWaste = data.est_wasted_ad_spend_pct != null;
  if (!data.bounce_drivers.length && !hasWaste) return null;
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl p-4">
      <p className="text-xs font-semibold text-white/40 uppercase tracking-wide mb-3">Ad-klik detail</p>
      <div className="flex gap-6 mb-3">
        {data.est_post_click_bounce_pct != null && (
          <div>
            <p className="text-2xl font-bold text-[#c5a96f]">{data.est_post_click_bounce_pct}%</p>
            <p className="text-xs text-white/40">bounce (basislijn {data.bounce_baseline_pct}%)</p>
          </div>
        )}
        {hasWaste && (
          <div>
            <p className="text-2xl font-bold text-orange-400">{data.est_wasted_ad_spend_pct}%</p>
            <p className="text-xs text-white/40">blind ad-budget</p>
          </div>
        )}
      </div>
      {data.bounce_drivers.length > 0 && (
        <ul className="flex flex-col gap-1">
          {data.bounce_drivers.map((d, i) => (
            <li key={i} className="flex items-start gap-2 text-xs text-white/50">
              <span className="text-[#c5a96f] shrink-0">↑</span>{d}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AiAnalysisSection({ data }: { data: NonNullable<AiAnalysis> }) {
  const skills = [
    { title: "CRO & Conversie", insight: data.cro },
    { title: "Deliverability & Trust", insight: data.deliverability },
    { title: "Tech-architectuur", insight: data.tech_architecture },
    { title: "Ad-klik bounce & omzetverlies", insight: data.ad_bounce_revenue },
  ];
  return (
    <SectionCard title="Analyse" dark>
      <div className="flex flex-col gap-4">
        {skills.map(({ title, insight }) =>
          insight ? (
            <div key={title} className="bg-white/5 border border-white/10 rounded-xl p-4">
              <h3 className="text-sm font-semibold text-[#c5a96f] mb-2">{title}</h3>
              <p className="text-sm text-white/80 leading-relaxed mb-3">{insight.summary}</p>
              {insight.top_actions.length > 0 && (
                <div className="mb-3">
                  <p className="text-xs font-semibold text-white/40 uppercase tracking-wide mb-2">Acties</p>
                  <ul className="flex flex-col gap-1.5">
                    {insight.top_actions.map((a, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs text-white/70">
                        <span className="text-[#c5a96f] mt-0.5 shrink-0">→</span>
                        {a}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {insight.signals_used.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {insight.signals_used.map((s) => (
                    <span key={s} className="text-xs bg-white/10 text-white/50 px-2 py-0.5 rounded-full">{s}</span>
                  ))}
                </div>
              )}
            </div>
          ) : null
        )}
        {data.shopify_migration && <ShopifyMigrationCard insight={data.shopify_migration} />}
      </div>
      {data.cross_section_thesis && (
        <blockquote className="mt-5 border-l-4 border-[#c5a96f] pl-4 text-sm text-white/70 italic">
          {data.cross_section_thesis}
        </blockquote>
      )}
    </SectionCard>
  );
}

function BloatSection({ items, aiInsight }: { items: BloatItem[]; aiInsight?: AiBloatInsight | null }) {
  const totalSavings = items.reduce((sum, i) => sum + (i.est_savings_eur || 0), 0);

  if (!items.length) {
    if (!aiInsight) return null;
    return (
      <SectionCard title="Wat moet eruit" dark>
        <p className="text-xs text-white/50 mb-3">Geen direct verwijderbare apps gedetecteerd — onderstaande kandidaten op basis van kosten en performance-signalen.</p>
        {aiInsight.summary && <p className="text-sm text-white/80 mb-3">{aiInsight.summary}</p>}
        {aiInsight.top_actions.length > 0 && (
          <ul className="text-xs text-white/60 space-y-1 list-disc list-inside">
            {aiInsight.top_actions.map((a, idx) => <li key={idx}>{a}</li>)}
          </ul>
        )}
      </SectionCard>
    );
  }

  return (
    <SectionCard title="Wat moet eruit" dark>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-white/10">
              {["Item", "Type", "Reden", "Besparing", "Perf. winst"].map((h) => (
                <th key={h} className="text-left py-1.5 pr-3 text-white/40 font-medium uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((i: BloatItem) => (
              <tr key={i.item} className="border-b border-white/5 last:border-0">
                <td className="py-2 pr-3 font-medium text-white">{i.item}</td>
                <td className="py-2 pr-3"><Pill label={i.category} tone="neutral" /></td>
                <td className="py-2 pr-3 text-white/60 max-w-[200px]">{i.reason ?? "—"}</td>
                <td className="py-2 pr-3 text-emerald-400">{i.est_savings_eur != null ? `€${i.est_savings_eur}/mo` : "—"}</td>
                <td className="py-2 text-white/60">{i.est_performance_gain_ms != null ? `${i.est_performance_gain_ms}ms` : "—"}</td>
              </tr>
            ))}
            {totalSavings > 0 && (
              <tr className="border-t-2 border-white/20">
                <td colSpan={3} className="pt-2 text-white/60 font-semibold">Totaal</td>
                <td colSpan={2} className="pt-2 text-emerald-400 font-bold">€{totalSavings.toFixed(0)}/mo</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}

function StatusPill({ ok, labelOk, labelBad }: { ok: boolean | null; labelOk: string; labelBad: string }) {
  if (ok == null) return null;
  return <Pill label={ok ? labelOk : labelBad} tone={ok ? "good" : "bad"} />;
}

function VendorList({ vendors }: { vendors: VendorDetection[] }) {
  if (!vendors.length) return null;
  return (
    <div className="flex flex-wrap gap-2 mt-2">
      {vendors.map((v) => (
        <span key={v.name} className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded-full">{v.name}</span>
      ))}
    </div>
  );
}

function DnsEmailSection({ data }: { data: NonNullable<FullAuditData["dns_email"]> }) {
  const dmarcTone = (p: DnsEmailHealth["dmarc_policy"]) => {
    if (p === "reject") return "good";
    if (p === "quarantine") return "warn";
    return "bad";
  };
  return (
    <SectionCard title="E-mail Deliverability (DNS)" dark>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        <div>
          {data.dmarc_policy && (
            <div className="mb-3">
              <Pill label={`DMARC: ${data.dmarc_policy}`} tone={dmarcTone(data.dmarc_policy)} />
            </div>
          )}
          {data.spf_status && (
            <div className="mb-2">
              <Pill label={`SPF: ${data.spf_status}`} tone={data.spf_status === "valid" ? "good" : "bad"} />
            </div>
          )}
          <KV label="DKIM selectors" value={data.dkim_selectors_found.length > 0 ? data.dkim_selectors_found.join(", ") : "geen gevonden"} />
          <KV label="MX provider" value={data.mx_provider} />
        </div>
        <div>
          {data.risk_summary && (
            <div className="bg-red-900/20 border border-red-500/20 rounded-lg p-3">
              <p className="text-xs font-semibold text-red-400 uppercase tracking-wide mb-1">Risico</p>
              <p className="text-xs text-red-300">{data.risk_summary}</p>
            </div>
          )}
        </div>
      </div>
      {data.mx_evidence && (
        <details className="mt-4 text-xs">
          <summary className="text-[#c5a96f] cursor-pointer">MX records</summary>
          <p className="mt-2 font-mono text-white/60">{data.mx_evidence}</p>
        </details>
      )}
    </SectionCard>
  );
}

function DomainHealthSection({ data }: { data: NonNullable<FullAuditData["domain_health"]> }) {
  return (
    <SectionCard title="Domein & TLS Gezondheid">
      <div className="flex flex-wrap gap-2 mb-4">
        <StatusPill ok={data.hsts_enabled} labelOk="HSTS actief" labelBad="Geen HSTS" />
        <StatusPill ok={data.http_to_https_forced} labelOk="HTTP→HTTPS ✓" labelBad="HTTP→HTTPS niet geforceerd" />
        <StatusPill ok={data.ipv6_enabled} labelOk="IPv6 ✓" labelBad="Geen IPv6" />
      </div>
      {data.hsts_max_age_days != null && (
        <KV label="HSTS max-age" value={`${data.hsts_max_age_days} dagen`} />
      )}
      <KV label="www redirect" value={data.www_redirect_status} />
      {data.redirect_chain_length != null && (
        <KV
          label="Redirect chain"
          value={
            <span className={data.redirect_chain_length > 2 ? "text-red-500 font-semibold" : ""}>
              {data.redirect_chain_length} {data.redirect_chain_length > 2 ? "⚠ te lang" : ""}
            </span>
          }
        />
      )}
      {data.evidence && (
        <details className="mt-3 text-xs">
          <summary className="text-[#c5a96f] cursor-pointer">Hoe weten we dit?</summary>
          <p className="mt-2 font-mono text-gray-500">{data.evidence}</p>
        </details>
      )}
    </SectionCard>
  );
}

function RichResultsSection({ data }: { data: NonNullable<FullAuditData["rich_results"]> }) {
  return (
    <SectionCard title="Rich Results & Schema Markup">
      <div className="flex flex-wrap gap-2 mb-4">
        <StatusPill ok={data.has_product_schema} labelOk="Product schema ✓" labelBad="Geen Product schema" />
        <StatusPill ok={data.has_aggregate_rating} labelOk="AggregateRating ✓" labelBad="Geen sterren in Google" />
        <StatusPill ok={data.has_breadcrumb} labelOk="Breadcrumb ✓" labelBad="Geen Breadcrumb" />
        <StatusPill ok={data.has_faq} labelOk="FAQ schema ✓" labelBad={""} />
      </div>
      {data.schemas_detected.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {data.schemas_detected.map((s) => (
            <span key={s} className="text-xs bg-[#c5a96f]/10 text-[#9a7a4a] px-2 py-0.5 rounded-full">{s}</span>
          ))}
        </div>
      )}
      {data.recommendations.length > 0 && (
        <div className="mt-3">
          <p className="text-xs font-semibold text-amber-600 uppercase tracking-wide mb-2">Aanbevelingen</p>
          <ul className="flex flex-col gap-1">
            {data.recommendations.map((r) => (
              <li key={r} className="text-xs text-amber-700 flex gap-2">
                <span>→</span>{r}
              </li>
            ))}
          </ul>
        </div>
      )}
    </SectionCard>
  );
}

function ServerSideTrackingSection({ data }: { data: NonNullable<FullAuditData["server_side_tracking"]> }) {
  const capiTone = (s: ServerSideTracking["meta_capi_status"]) =>
    s === "detected" ? "good" : s === "browser-only" ? "warn" : "bad";
  const riskTone = (r: ServerSideTracking["attribution_loss_risk"]) =>
    r === "low" ? "good" : r === "medium" ? "warn" : "bad";
  return (
    <SectionCard title="Server-side Conversions">
      {data.attribution_loss_risk && (
        <div className="mb-4 text-center bg-[#FAFAF8] rounded-xl p-4 border border-gray-100">
          <Pill label={`Attribution loss risk: ${data.attribution_loss_risk}`} tone={riskTone(data.attribution_loss_risk)} />
        </div>
      )}
      <div className="flex flex-wrap gap-2 mb-3">
        <Pill label={`sGTM: ${data.sgtm_detected ? "gevonden" : "niet gevonden"}`} tone={data.sgtm_detected ? "good" : "warn"} />
        {data.meta_capi_status && (
          <Pill label={`Meta CAPI: ${data.meta_capi_status}`} tone={capiTone(data.meta_capi_status)} />
        )}
        {data.google_enhanced_conv_status && (
          <Pill
            label={`GEC: ${data.google_enhanced_conv_status}`}
            tone={data.google_enhanced_conv_status === "detected" ? "good" : "warn"}
          />
        )}
        {data.tiktok_capi_status && (
          <Pill
            label={`TikTok API: ${data.tiktok_capi_status}`}
            tone={data.tiktok_capi_status === "detected" ? "good" : "warn"}
          />
        )}
      </div>
      {data.sgtm_endpoint && <KV label="sGTM endpoint" value={data.sgtm_endpoint} mono />}
    </SectionCard>
  );
}

function AccessibilitySection({ data }: { data: NonNullable<FullAuditData["accessibility"]> }) {
  const score = data.lighthouse_score;
  const scoreColor = score == null ? "text-gray-400" : score >= 90 ? "text-emerald-600" : score >= 70 ? "text-yellow-600" : "text-red-500";
  return (
    <SectionCard title="Accessibility (EU EAA)">
      {score != null && (
        <div className="text-center bg-[#FAFAF8] rounded-xl p-4 border border-gray-100 mb-4">
          <div className={`text-4xl font-semibold ${scoreColor}`}>{score}</div>
          <div className="text-xs text-gray-400 mt-1">Lighthouse accessibility score</div>
        </div>
      )}
      <div className="flex flex-wrap gap-2 mb-3">
        <StatusPill ok={data.lang_attribute_set} labelOk="lang attribuut ✓" labelBad="Geen lang attribuut" />
        <StatusPill ok={data.viewport_meta_set} labelOk="viewport meta ✓" labelBad="Geen viewport meta" />
      </div>
      {data.img_alt_coverage_pct != null && (
        <KV
          label="Alt-tekst dekking"
          value={
            <span className={data.img_alt_coverage_pct < 80 ? "text-red-500 font-semibold" : "text-emerald-600"}>
              {data.img_alt_coverage_pct}%
            </span>
          }
        />
      )}
      {data.landmarks_present.length > 0 && (
        <KV label="HTML landmarks" value={data.landmarks_present.join(", ")} />
      )}
      {data.eu_eaa_risk_summary && (
        <div className="mt-3 bg-amber-50 border border-amber-200 rounded-lg p-3">
          <p className="text-xs font-semibold text-amber-600 uppercase tracking-wide mb-1">EU EAA risico</p>
          <p className="text-xs text-amber-700">{data.eu_eaa_risk_summary}</p>
        </div>
      )}
    </SectionCard>
  );
}

function ProductFeedsSection({ data }: { data: NonNullable<FullAuditData["product_feeds"]> }) {
  const estimateTone = (e: ProductFeedHealth["google_merchant_ready_estimate"]) =>
    e === "ready" ? "good" : e === "partial" ? "warn" : "bad";
  return (
    <SectionCard title="Product Feed Gezondheid">
      {data.google_merchant_ready_estimate && (
        <div className="mb-4">
          <Pill
            label={`Google Merchant: ${data.google_merchant_ready_estimate}`}
            tone={estimateTone(data.google_merchant_ready_estimate)}
          />
        </div>
      )}
      <div className="flex flex-wrap gap-2 mb-3">
        <StatusPill ok={data.feed_endpoint_reachable} labelOk="Feed endpoint bereikbaar" labelBad="Feed endpoint niet bereikbaar" />
        <StatusPill ok={data.og_product_tags_present} labelOk="OG product tags ✓" labelBad="Geen OG product tags" />
        <StatusPill ok={data.jsonld_product_complete} labelOk="JSON-LD Product compleet" labelBad="JSON-LD Product incompleet" />
      </div>
      {data.missing_fields.length > 0 && (
        <div className="mt-2">
          <p className="text-xs font-semibold text-red-500 uppercase tracking-wide mb-1">Ontbrekende velden</p>
          <div className="flex flex-wrap gap-1">
            {data.missing_fields.map((f) => (
              <span key={f} className="text-xs bg-red-50 text-red-600 px-2 py-0.5 rounded-full">{f}</span>
            ))}
          </div>
        </div>
      )}
      {data.platform_feed_endpoint && (
        <details className="mt-3 text-xs">
          <summary className="text-[#c5a96f] cursor-pointer">Feed endpoint</summary>
          <p className="mt-1 font-mono text-gray-500 break-all">{data.platform_feed_endpoint}</p>
        </details>
      )}
    </SectionCard>
  );
}

function CompetitorBenchmarkSection({ data }: { data: NonNullable<FullAuditData["competitor_benchmark"]> }) {
  const fmtNum = (n: number | null) => (n == null ? "—" : Math.round(n).toLocaleString("nl-NL"));
  return (
    <SectionCard title="Concurrentie-benchmark" dark>
      <p className="text-xs text-white/40 mb-4">
        Organische zoekprestatie t.o.v. de dichtstbijzijnde concurrenten (via DataForSEO, {data.language_code.toUpperCase()}-markt) — {data.notes}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-white/10">
              {["Domein", "Org. zoekwoorden", "Geschatte verkeerswaarde ($)", "Gedeelde zoekwoorden"].map((h) => (
                <th key={h} className="text-left py-2 pr-3 text-white/30 font-medium uppercase tracking-wide text-[10px]">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-white/5 bg-[#c5a96f]/5">
              <td className="py-2 pr-3 font-semibold text-[#c5a96f]">{data.store_domain} (jij)</td>
              <td className="py-2 pr-3 tabular-nums text-white/80">{fmtNum(data.store_organic_keywords_count)}</td>
              <td className="py-2 pr-3 tabular-nums text-white/80">{fmtNum(data.store_est_organic_traffic_value_usd)}</td>
              <td className="py-2 pr-3 text-white/30">—</td>
            </tr>
            {data.competitors.map((c) => (
              <tr key={c.domain} className="border-b border-white/5 last:border-0">
                <td className="py-2 pr-3 text-white/70">{c.domain}</td>
                <td className="py-2 pr-3 tabular-nums text-white/60">{fmtNum(c.organic_keywords_count)}</td>
                <td className="py-2 pr-3 tabular-nums text-white/60">{fmtNum(c.est_organic_traffic_value_usd)}</td>
                <td className="py-2 pr-3 tabular-nums text-white/60">{fmtNum(c.intersecting_keywords)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.competitors.length === 0 && (
        <p className="text-xs text-white/30 mt-3">Geen vergelijkbare concurrenten gevonden voor dit domein.</p>
      )}
    </SectionCard>
  );
}

function ShopifyPlatformSection({
  catalog,
  apps,
}: {
  catalog: FullAuditData["shopify_catalog"];
  apps: FullAuditData["shopify_apps"];
}) {
  return (
    <SectionCard title="Shopify Platform Diepte">
      {catalog && (
        <div className="mb-5 pb-5 border-b border-gray-100 last:border-0 last:pb-0 last:mb-0">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Catalogus</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-2">
            {catalog.product_count_sampled != null && (
              <div className="bg-[#FAFAF8] rounded-lg p-2 text-center border border-gray-100">
                <div className="text-lg font-semibold text-gray-900">{catalog.product_count_sampled}</div>
                <div className="text-xs text-gray-400">Producten (sample)</div>
              </div>
            )}
            {catalog.out_of_stock_ratio_pct != null && (
              <div className="bg-[#FAFAF8] rounded-lg p-2 text-center border border-gray-100">
                <div className={`text-lg font-semibold ${catalog.out_of_stock_ratio_pct > 15 ? "text-red-500" : "text-gray-900"}`}>{catalog.out_of_stock_ratio_pct}%</div>
                <div className="text-xs text-gray-400">Uitverkocht</div>
              </div>
            )}
            {!!catalog.products_missing_images && (
              <div className="bg-[#FAFAF8] rounded-lg p-2 text-center border border-gray-100">
                <div className="text-lg font-semibold text-amber-600">{catalog.products_missing_images}</div>
                <div className="text-xs text-gray-400">Zonder foto</div>
              </div>
            )}
            {!!catalog.products_missing_description && (
              <div className="bg-[#FAFAF8] rounded-lg p-2 text-center border border-gray-100">
                <div className="text-lg font-semibold text-amber-600">{catalog.products_missing_description}</div>
                <div className="text-xs text-gray-400">Zonder omschrijving</div>
              </div>
            )}
          </div>
          {catalog.theme_name && <KV label="Thema" value={catalog.theme_name} />}
          {catalog.collection_count_sampled != null && <KV label="Collecties (sample)" value={`${catalog.collection_count_sampled}`} />}
        </div>
      )}
      {apps && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Apps</p>
          {apps.app_extension_count != null && apps.app_extension_count > 0 ? (
            <KV label="Gedetecteerde app-extensies" value={`${apps.app_extension_count}`} />
          ) : (
            <p className="text-sm text-gray-500">Geen app-extensies gedetecteerd</p>
          )}
          {apps.notes && <p className="text-xs text-gray-400 mt-2 italic">{apps.notes}</p>}
        </div>
      )}
    </SectionCard>
  );
}

function RetentionComplianceSection({
  retention,
  compliance,
}: {
  retention: FullAuditData["retention"];
  compliance: FullAuditData["eu_compliance"];
}) {
  const hasRetention = !!retention && (
    retention.subscription_detected.length > 0 ||
    retention.loyalty_detected.length > 0 ||
    retention.bundling_detected.length > 0
  );
  return (
    <SectionCard title="Retentie & EU Compliance">
      <div className="mb-5 pb-5 border-b border-gray-100 last:border-0 last:pb-0 last:mb-0">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Retentie-infrastructuur</p>
        {hasRetention && retention ? (
          <>
            <VendorList vendors={retention.subscription_detected} />
            <VendorList vendors={retention.loyalty_detected} />
            <VendorList vendors={retention.bundling_detected} />
          </>
        ) : (
          <p className="text-sm text-gray-500">Geen abonnement-, loyalty- of bundeltool gedetecteerd</p>
        )}
      </div>
      {compliance && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">EU Compliance-signalen</p>
          <p className="text-[11px] text-gray-400 mb-2 italic">Heuristische signalen, geen juridisch oordeel.</p>
          <div className="flex flex-wrap gap-2 mb-2">
            {compliance.omnibus_risk_signal != null && (
              <Pill
                label={compliance.omnibus_risk_signal ? "Omnibus: mogelijk risico" : "Omnibus: geen signaal"}
                tone={compliance.omnibus_risk_signal ? "bad" : "good"}
              />
            )}
            {compliance.gpsr_responsible_person_mentioned != null && (
              <Pill label="GPSR: verantwoordelijke partij vermeld" tone="good" />
            )}
          </div>
          {compliance.evidence && <p className="text-xs text-gray-500">{compliance.evidence}</p>}
          {compliance.notes && <p className="text-[11px] text-gray-400 mt-2 italic">{compliance.notes}</p>}
        </div>
      )}
    </SectionCard>
  );
}

function DetectedStackSection({ data }: { data: NonNullable<FullAuditData["detected_stack"]> }) {
  const { site_search, shipping, returns, multi_region, marketplaces } = data;
  return (
    <SectionCard title="Gedetecteerde stack">
      <p className="text-xs text-gray-400 mb-4">
        Losse vendor-signalen zonder benchmark of kostenclaim — puur wat er gedetecteerd is.
      </p>

      {site_search && (
        <div className="mb-5 pb-5 border-b border-gray-100 last:border-0 last:pb-0 last:mb-0">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Zoekfunctie</p>
          {site_search.provider_detected ? (
            <div className="mb-2">
              <span className="text-sm font-semibold text-gray-800">{site_search.provider_detected}</span>
              <Pill label="gedetecteerd" tone="good" />
            </div>
          ) : (
            <p className="text-sm text-gray-500 mb-2">Geen bekende search provider gedetecteerd</p>
          )}
          <VendorList vendors={site_search.detected_vendors} />
          <StatusPill ok={site_search.native_search_present} labelOk="Native search aanwezig" labelBad="Geen search gevonden" />
        </div>
      )}

      {shipping && (
        <div className="mb-5 pb-5 border-b border-gray-100 last:border-0 last:pb-0 last:mb-0">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Shipping & Carriers</p>
          {shipping.providers_detected.length > 0 ? (
            <div className="flex flex-wrap gap-2 mb-2">
              {shipping.providers_detected.map((p) => (
                <Pill key={p} label={p} tone="neutral" />
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-500 mb-2">Geen carrier integratie gedetecteerd</p>
          )}
          <VendorList vendors={shipping.detected_vendors} />
        </div>
      )}

      {returns && (
        <div className="mb-5 pb-5 border-b border-gray-100 last:border-0 last:pb-0 last:mb-0">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Returns</p>
          {returns.providers_detected.length > 0 ? (
            <div className="flex flex-wrap gap-2 mb-2">
              {returns.providers_detected.map((p) => (
                <Pill key={p} label={p} tone="good" />
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-500 mb-2">Geen returns platform gedetecteerd</p>
          )}
          <VendorList vendors={returns.detected_vendors} />
          {returns.returns_portal_url && (
            <KV label="Returns portal" value={returns.returns_portal_url} mono />
          )}
        </div>
      )}

      {multi_region && (
        <div className="mb-5 pb-5 border-b border-gray-100 last:border-0 last:pb-0 last:mb-0">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Multi-currency & Regio</p>
          <div className="flex flex-wrap gap-2 mb-3">
            <StatusPill ok={multi_region.currency_switcher_detected} labelOk="Currency switcher ✓" labelBad="Geen currency switcher" />
            <StatusPill ok={multi_region.vary_accept_language} labelOk="Vary: Accept-Language ✓" labelBad="Geen taal-vary header" />
            {multi_region.geo_redirect_detected != null && (
              <Pill label={`Geo redirect: ${multi_region.geo_redirect_detected ? "ja" : "nee"}`} tone={multi_region.geo_redirect_detected ? "good" : "neutral"} />
            )}
          </div>
          {multi_region.currencies_detected.length > 0 && (
            <KV label="Valuta gedetecteerd" value={multi_region.currencies_detected.join(", ")} />
          )}
          {multi_region.hreflang_count != null && (
            <KV label="Hreflang tags" value={`${multi_region.hreflang_count}`} />
          )}
        </div>
      )}

      {marketplaces && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Marketplace & Reviews</p>
          {marketplaces.platforms_detected.length > 0 && (
            <div className="mb-2">
              <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Marketplaces</p>
              <div className="flex flex-wrap gap-2">
                {marketplaces.platforms_detected.map((p) => (
                  <Pill key={p} label={p} tone="neutral" />
                ))}
              </div>
            </div>
          )}
          {marketplaces.review_platforms_detected.length > 0 && (
            <div className="mb-2">
              <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Review platforms</p>
              <div className="flex flex-wrap gap-2">
                {marketplaces.review_platforms_detected.map((p) => (
                  <Pill key={p} label={p} tone="good" />
                ))}
              </div>
            </div>
          )}
          {marketplaces.platforms_detected.length === 0 && marketplaces.review_platforms_detected.length === 0 && (
            <p className="text-sm text-gray-500">Geen marketplace of review platform gedetecteerd</p>
          )}
        </div>
      )}
    </SectionCard>
  );
}

function SanityExportSection({ data }: { data: Record<string, unknown> }) {
  const [copied, setCopied] = useState(false);
  const json = JSON.stringify(data, null, 2);

  function handleCopy() {
    navigator.clipboard.writeText(json).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <SectionCard title="Sanity Export — Copy-Paste Klaar" dark>
      <div className="flex justify-end mb-3">
        <button
          onClick={handleCopy}
          className="text-xs px-4 py-2 rounded-lg bg-[#c5a96f] text-[#1a1f2e] font-semibold hover:opacity-90 transition-opacity"
        >
          {copied ? "Gekopieerd!" : "Kopieer JSON"}
        </button>
      </div>
      <pre className="overflow-auto max-h-96 text-xs text-gray-300 font-mono leading-relaxed">
        {json}
      </pre>
    </SectionCard>
  );
}

export default function FullAuditResults() {
  const { auditId } = useParams<{ auditId: string }>();
  const [statusData, setStatusData] = useState<FullAuditStatusResponse | null>(null);
  const [auditData, setAuditData] = useState<FullAuditData | null>(null);
  const [sanityExport, setSanityExport] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msgIndex, setMsgIndex] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const msgIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const isReady = statusData?.status === "ready_for_review";
  const isFailed = statusData?.status === "failed";
  const isPending = !isReady && !isFailed;

  useEffect(() => {
    if (!isPending) return;
    msgIntervalRef.current = setInterval(() => {
      setMsgIndex((i) => (i + 1) % statusMessages.length);
    }, 3000);
    return () => { if (msgIntervalRef.current) clearInterval(msgIntervalRef.current); };
  }, [isPending]);

  useEffect(() => {
    if (!auditId) return;
    async function poll() {
      try {
        const s = await getFullAuditStatus(auditId!);
        setStatusData(s);
        if (s.status === "ready_for_review") {
          if (intervalRef.current) clearInterval(intervalRef.current);
          const full = await getFullAudit(auditId!);
          setAuditData(full.data);
          getFullAuditSanityExport(auditId!).then(setSanityExport);
        } else if (s.status === "failed") {
          if (intervalRef.current) clearInterval(intervalRef.current);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch status");
        if (intervalRef.current) clearInterval(intervalRef.current);
      }
    }
    poll();
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [auditId]);

  if (error) {
    return (
      <div className="min-h-screen bg-[#FAFAF8] flex flex-col">
        <Header />
        <div className="flex-1 flex items-center justify-center px-4">
          <div className="max-w-md w-full bg-white rounded-2xl p-10 text-center flex flex-col gap-4 shadow-sm border border-gray-100">
            <h2 className="text-xl font-semibold text-gray-900" style={{ fontFamily: "var(--font-serif)" }}>Error</h2>
            <p className="text-gray-500 text-sm">{error}</p>
            <Link to="/full-audit" className="bg-[#1a1f2e] text-white font-medium px-6 py-3 rounded-xl">Terug</Link>
          </div>
        </div>
        <Footer />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#FAFAF8] flex flex-col">
      <Header />
      <main className="flex-1 py-12 px-4">
        <div className="max-w-4xl mx-auto flex flex-col gap-6">

          {/* Header */}
          <div>
            <Link to="/full-audit" className="text-xs text-[#c5a96f] hover:underline">← Nieuwe audit</Link>
            <h1 className="text-2xl font-semibold text-[#1a1f2e] mt-2" style={{ fontFamily: "var(--font-serif)" }}>
              {auditData?.company_name || statusData?.store_url || "Full Audit"}
            </h1>
            {statusData && (
              <div className="flex items-center gap-2 mt-1">
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                  isReady ? "bg-emerald-50 text-emerald-700" :
                  isFailed ? "bg-red-50 text-red-700" :
                  "bg-yellow-50 text-yellow-700"
                }`}>
                  {statusData.status.replace("_", " ")}
                </span>
                {statusData.scan_level && <span className="text-xs text-gray-400">{statusData.scan_level}</span>}
              </div>
            )}
          </div>

          {/* Processing */}
          {isPending && (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-10 flex flex-col items-center gap-6">
              <svg className="w-10 h-10 text-[#c5a96f] animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <div className="text-center">
                <h2 className="text-xl font-semibold text-gray-800" style={{ fontFamily: "var(--font-serif)" }}>
                  Audit loopt...
                </h2>
                <p className="text-sm text-[#c5a96f] font-medium animate-pulse mt-1">
                  {statusMessages[msgIndex]}
                </p>
              </div>
            </div>
          )}

          {/* Failed */}
          {isFailed && (
            <div className="bg-white rounded-2xl shadow-sm border border-red-100 p-8 text-center">
              <h2 className="text-lg font-semibold text-red-600 mb-2">Audit mislukt</h2>
              <p className="text-sm text-gray-500">De store kon niet gescraped worden of er trad een fout op.</p>
              <Link to="/full-audit" className="mt-4 inline-block bg-[#1a1f2e] text-white px-5 py-2.5 rounded-xl text-sm font-medium">
                Opnieuw proberen
              </Link>
            </div>
          )}

          {/* Results */}
          {isReady && auditData && (
            <>
              {/* Top summary */}
              {(auditData.core_thesis || auditData.biggest_tech_risk) && (
                <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6">
                  {auditData.core_thesis && (
                    <blockquote className="border-l-4 border-[#c5a96f] pl-4 text-lg font-medium text-gray-800 italic mb-4" style={{ fontFamily: "var(--font-serif)" }}>
                      {auditData.core_thesis}
                    </blockquote>
                  )}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {auditData.biggest_tech_risk && (
                      <div className="bg-red-50 rounded-xl p-3">
                        <p className="text-xs font-semibold text-red-400 uppercase tracking-wide mb-1">Grootste risico</p>
                        <p className="text-sm text-red-700">{auditData.biggest_tech_risk}</p>
                      </div>
                    )}
                    {auditData.biggest_tech_opportunity && (
                      <div className="bg-emerald-50 rounded-xl p-3">
                        <p className="text-xs font-semibold text-emerald-500 uppercase tracking-wide mb-1">Grootste kans</p>
                        <p className="text-sm text-emerald-700">{auditData.biggest_tech_opportunity}</p>
                      </div>
                    )}
                  </div>
                  {auditData.audit_summary && (
                    <p className="text-xs text-gray-400 mt-3 italic">{auditData.audit_summary}</p>
                  )}
                </div>
              )}

              {/* Top stats */}
              {(auditData.est_performance_lift_percent != null ||
                auditData.cost_analysis?.est_monthly_savings_eur != null ||
                auditData.third_party_scripts?.total_third_party_domains != null) && (
                <div className="grid grid-cols-3 gap-3">
                  {auditData.est_performance_lift_percent != null && (
                    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 text-center">
                      <div className="text-3xl font-semibold text-[#c5a96f]">{auditData.est_performance_lift_percent}%</div>
                      <div className="text-xs text-gray-400 mt-1">Performance lift potentieel</div>
                    </div>
                  )}
                  {auditData.cost_analysis?.est_monthly_savings_eur != null && (
                    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 text-center">
                      <div className="text-3xl font-semibold text-emerald-500">€{auditData.cost_analysis.est_monthly_savings_eur}</div>
                      <div className="text-xs text-gray-400 mt-1">Besparing/maand mogelijk</div>
                    </div>
                  )}
                  {auditData.third_party_scripts?.total_third_party_domains != null && (
                    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 text-center">
                      <div className="text-3xl font-semibold text-[#1a1f2e]">{auditData.third_party_scripts.total_third_party_domains}</div>
                      <div className="text-xs text-gray-400 mt-1">Externe domeinen</div>
                    </div>
                  )}
                </div>
              )}

              {/* Sections */}
              {auditData.platform_architecture && <PlatformSection data={auditData.platform_architecture} />}
              {auditData.performance && <PerformanceSection data={auditData.performance} />}
              {auditData.revenue_leak && (
                <>
                  {auditData.seranking_traffic ? (
                    <div className="flex items-center gap-2 px-1 mb-1">
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 border border-emerald-200 px-3 py-1 text-xs font-medium text-emerald-700">
                        <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd"/></svg>
                        Gemeten via SE Ranking — {(auditData.seranking_traffic.monthly_organic_sessions + auditData.seranking_traffic.monthly_paid_sessions).toLocaleString("nl-NL")} bezoekers/mnd
                      </span>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 px-1 mb-1">
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 border border-amber-200 px-3 py-1 text-xs font-medium text-amber-700">
                        <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd"/></svg>
                        Schatting — traffic niet beschikbaar via SE Ranking
                      </span>
                    </div>
                  )}
                  <RevenueLeakSection data={auditData.revenue_leak} />
                </>
              )}
              {auditData.competitor_benchmark && <CompetitorBenchmarkSection data={auditData.competitor_benchmark} />}
              {auditData.third_party_scripts && <ThirdPartySection data={auditData.third_party_scripts} />}
              {auditData.tracking_data_quality && <TrackingSection data={auditData.tracking_data_quality} />}
              {auditData.checkout_flow && <CheckoutSection data={auditData.checkout_flow} />}
              {auditData.owned_channels && <OwnedChannelsSection data={auditData.owned_channels} />}
              {auditData.security_compliance && <SecuritySection data={auditData.security_compliance} />}
              {auditData.cost_analysis && <CostSection data={auditData.cost_analysis} />}
              {auditData.dns_email && <DnsEmailSection data={auditData.dns_email} />}
              {auditData.domain_health && <DomainHealthSection data={auditData.domain_health} />}
              {auditData.rich_results && <RichResultsSection data={auditData.rich_results} />}
              {auditData.server_side_tracking && <ServerSideTrackingSection data={auditData.server_side_tracking} />}
              {auditData.product_feeds && <ProductFeedsSection data={auditData.product_feeds} />}
              {auditData.detected_stack && <DetectedStackSection data={auditData.detected_stack} />}
              {(auditData.shopify_catalog || auditData.shopify_apps) && (
                <ShopifyPlatformSection catalog={auditData.shopify_catalog} apps={auditData.shopify_apps} />
              )}
              {(auditData.retention || auditData.eu_compliance) && (
                <RetentionComplianceSection retention={auditData.retention} compliance={auditData.eu_compliance} />
              )}
              {auditData.accessibility && <AccessibilitySection data={auditData.accessibility} />}
              {auditData.cro_observations.length > 0 && <CroSection items={auditData.cro_observations} />}
              {(auditData.bloat_what_must_go.length > 0 || auditData.ai_analysis?.bloat) && <BloatSection items={auditData.bloat_what_must_go} aiInsight={auditData.ai_analysis?.bloat} />}
              {auditData.ai_analysis && (auditData.ai_analysis.cro || auditData.ai_analysis.deliverability || auditData.ai_analysis.tech_architecture || auditData.ai_analysis.ad_bounce_revenue) && <AiAnalysisSection data={auditData.ai_analysis} />}
              {sanityExport && <SanityExportSection data={sanityExport} />}

              {auditData.methodology_note && (
                <p className="text-xs text-gray-400 italic text-center px-4">{auditData.methodology_note}</p>
              )}
            </>
          )}
        </div>
      </main>
      <Footer />
    </div>
  );
}
