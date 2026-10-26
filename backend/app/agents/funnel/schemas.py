"""The funnel agent's output. The model picks an `issue_key` from a fixed list; which
keys are priced, and how, lives in full_audit/analyzers/benchmarks.py
(FUNNEL_WALK_RULES) — the model never writes a euro."""

from typing import Literal

from pydantic import BaseModel, Field

FunnelStage = Literal["session", "product_view", "add_to_cart", "reach_checkout", "purchase"]

FunnelIssueKey = Literal[
    # priced (FUNNEL_WALK_RULES), only with machine evidence
    "atc_blocked_by_overlay",
    "atc_no_feedback",
    "checkout_unreachable",
    # shares the analyzers' shipping.cost_clarity finding (priced there, counted once)
    "shipping_cost_late",
    # unpriced
    "variant_picker_broken",
    "search_no_results",
    "intrusive_mobile_interstitial",
    "slow_cart_feedback",
    "price_mismatch_pdp_cart",
    "tap_target_too_small",
    "other",
]

StepName = Literal["home", "search", "collection", "product", "variant", "add_to_cart", "cart", "checkout"]
WalkStatus = Literal["ok", "blocked", "failed", "skipped"]


class FunnelStep(BaseModel):
    step: StepName
    reached: bool
    url: str | None = None
    duration_ms: int | None = Field(default=None, description="Gemeten wachttijd voor deze stap, uit de tool-output. Niet schatten.")
    note_nl: str | None = None


class FunnelIssueSubmission(BaseModel):
    issue_key: FunnelIssueKey
    step: StepName
    description_nl: str = Field(description="Wat een klant ervaart, in gewone taal. Geen eurobedragen.")
    evidence_nl: str = Field(description="Wat je concreet deed en zag: tool, element, URL.")
    page_url: str | None = None
    screenshot_id: str | None = Field(default=None, description="Id uit een eerdere screenshot-tool-call die dit laat zien.")


class FunnelWalkSubmission(BaseModel):
    blocked: bool = Field(default=False, description="True als bot-bescherming, een wachtwoordpagina of een landkeuze de walk onmogelijk maakte.")
    steps: list[FunnelStep] = Field(min_length=1)
    issues: list[FunnelIssueSubmission] = []
    summary_nl: str


class FunnelIssue(FunnelIssueSubmission):
    # True when the browser layer recorded the fact this issue key needs to be priced
    # (PRICED_EVIDENCE in service.py). False: shown, never priced.
    machine_confirmed: bool = False


class FunnelWalk(BaseModel):
    """Stored on FullAuditData.funnel_walk."""
    status: WalkStatus
    steps: list[FunnelStep] = []
    issues: list[FunnelIssue] = []
    summary_nl: str | None = None
    warnings: list[str] = []
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
