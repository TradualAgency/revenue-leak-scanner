"""The four v1 fix agents: which findings each owns, which audit sections it starts
from, and which tools it gets. Prompts live in skills/<name>.md."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.fix_agents.schemas import AgentName

_SKILLS_DIR = Path(__file__).parent / "skills"

_BASE_TOOLS = ["get_audit_section", "fetch_page", "run_analyzer"]
_ADMIN_TOOLS = ["list_theme_files", "read_theme_file", "get_products_sample"]


@dataclass(frozen=True)
class AgentSpec:
    name: AgentName
    # A finding belongs to this agent when its id starts with one of these.
    finding_prefixes: tuple[str, ...]
    # Pre-loaded into the first message so the agent doesn't spend turns fetching them.
    primary_sections: tuple[str, ...]
    tools: tuple[str, ...]

    @property
    def system_prompt(self) -> str:
        return (_SKILLS_DIR / "_common.md").read_text(encoding="utf-8") + "\n\n" + (
            _SKILLS_DIR / f"{self.name}.md"
        ).read_text(encoding="utf-8")

    def owns(self, finding_id: str) -> bool:
        return finding_id.startswith(self.finding_prefixes)


AGENTS: dict[str, AgentSpec] = {
    "speed_bloat": AgentSpec(
        name="speed_bloat",
        finding_prefixes=("perf.", "gap.lcp_", "gap.inp_", "adtraffic."),
        primary_sections=("performance", "third_party_scripts", "bloat_what_must_go", "shopify_apps", "cost_analysis"),
        tools=(*_BASE_TOOLS, *_ADMIN_TOOLS),
    ),
    "tracking": AgentSpec(
        name="tracking",
        finding_prefixes=("tracking.", "gap.tracking_"),
        primary_sections=("tracking_data_quality", "server_side_tracking", "detected_stack"),
        tools=(*_BASE_TOOLS, "list_theme_files", "read_theme_file"),
    ),
    "cro_pdp": AgentSpec(
        name="cro_pdp",
        finding_prefixes=("cro.", "cart.", "catalog.", "owned.", "shipping.", "gap.schema_aggregate_rating"),
        primary_sections=("cro_observations", "owned_channels", "shopify_catalog", "retention"),
        tools=(*_BASE_TOOLS, *_ADMIN_TOOLS),
    ),
    "checkout_schema": AgentSpec(
        name="checkout_schema",
        finding_prefixes=("checkout.", "gap.checkout_", "seo.", "feed.", "gap.schema_"),
        primary_sections=("checkout_flow", "rich_results", "seo_health", "product_feeds"),
        tools=(*_BASE_TOOLS, *_ADMIN_TOOLS),
    ),
}
