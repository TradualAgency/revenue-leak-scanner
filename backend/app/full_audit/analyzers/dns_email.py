import asyncio
import logging
import re
from urllib.parse import urlparse

from app.full_audit.schemas import DnsEmailHealth

logger = logging.getLogger(__name__)

_DKIM_SELECTORS = [
    "default", "google", "mail", "selector1", "selector2",
    "k1", "smtp", "mandrill", "mailjet", "sendgrid", "em",
    "s1", "s2", "dkim", "email", "m1",
]

_MX_PROVIDERS = {
    "google.com": "Google Workspace",
    "googlemail.com": "Google Workspace",
    "outlook.com": "Microsoft 365",
    "office365.com": "Microsoft 365",
    "mail.protection.outlook.com": "Microsoft 365",
    "sendgrid.net": "SendGrid",
    "mailgun.org": "Mailgun",
    "amazonses.com": "Amazon SES",
    "mailchannels.net": "MailChannels",
    "klaviyo.com": "Klaviyo",
    "mxroute.com": "MXroute",
    "zoho.com": "Zoho",
    "protonmail.ch": "ProtonMail",
}


def _mx_provider(exchange: str) -> str | None:
    exchange = exchange.rstrip(".").lower()
    for suffix, provider in _MX_PROVIDERS.items():
        if exchange.endswith(suffix):
            return provider
    return None


async def _resolve(domain: str, rdtype: str) -> list[str]:
    try:
        import dns.resolver
        records = await asyncio.to_thread(dns.resolver.resolve, domain, rdtype, lifetime=5.0)
        return [r.to_text() for r in records]
    except Exception:
        return []


async def analyze_dns_email(store_url: str) -> DnsEmailHealth:
    try:
        domain = urlparse(store_url).hostname or ""
        if not domain:
            return DnsEmailHealth()

        # Run SPF, DMARC, MX concurrently; DKIM probes sequentially to avoid hammering DNS
        _gathered = await asyncio.gather(
            _resolve(domain, "TXT"),
            _resolve(f"_dmarc.{domain}", "TXT"),
            _resolve(domain, "MX"),
            return_exceptions=True,
        )
        txt_records: list[str] = _gathered[0] if not isinstance(_gathered[0], BaseException) else []
        dmarc_records: list[str] = _gathered[1] if not isinstance(_gathered[1], BaseException) else []
        mx_records: list[str] = _gathered[2] if not isinstance(_gathered[2], BaseException) else []

        # SPF
        spf_record = next((r.strip('"') for r in txt_records if "v=spf1" in r.lower()), None)
        if spf_record is None:
            spf_status = "missing"
        elif "-all" in spf_record or "~all" in spf_record:
            spf_status = "valid"
        else:
            spf_status = "misconfigured"

        # DMARC
        dmarc_record = next((r.strip('"') for r in dmarc_records if "v=DMARC1" in r), None)
        if dmarc_record is None:
            dmarc_policy = "missing"
        else:
            m = re.search(r"p=(\w+)", dmarc_record)
            raw = m.group(1).lower() if m else "none"
            dmarc_policy = raw if raw in ("none", "quarantine", "reject") else "none"

        # DKIM — probe selectors concurrently in batches of 5
        dkim_found: list[str] = []
        for i in range(0, len(_DKIM_SELECTORS), 5):
            batch = _DKIM_SELECTORS[i:i + 5]
            results = await asyncio.gather(
                *[_resolve(f"{sel}._domainkey.{domain}", "TXT") for sel in batch],
                return_exceptions=True,
            )
            for sel, recs in zip(batch, results):
                if not isinstance(recs, Exception) and recs:
                    dkim_found.append(sel)

        # MX provider
        mx_provider: str | None = None
        mx_evidence: str | None = None
        if mx_records:
            for r in mx_records:
                parts = r.split()
                exchange = parts[-1] if parts else ""
                provider = _mx_provider(exchange)
                if provider:
                    mx_provider = provider
                    break
            mx_evidence = "; ".join(mx_records[:3])

        # Risk summary
        risks = []
        if dmarc_policy in ("missing", "none"):
            risks.append(f"DMARC {dmarc_policy} — inbox placement risk")
        if spf_status != "valid":
            risks.append(f"SPF {spf_status}")
        if not dkim_found:
            risks.append("Geen DKIM selectors gevonden")

        return DnsEmailHealth(
            spf_record=spf_record,
            spf_status=spf_status,  # type: ignore[arg-type]
            dmarc_record=dmarc_record,
            dmarc_policy=dmarc_policy,  # type: ignore[arg-type]
            dkim_selectors_found=dkim_found,
            mx_provider=mx_provider,
            mx_evidence=mx_evidence,
            risk_summary="; ".join(risks) if risks else None,
        )
    except Exception as exc:
        logger.warning("dns_email analyzer failed: %s", exc)
        return DnsEmailHealth()
