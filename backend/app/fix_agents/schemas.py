import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AgentName = Literal["speed_bloat", "tracking", "cro_pdp", "checkout_schema"]
RunStatus = Literal["queued", "processing", "done", "failed"]
Risk = Literal["laag", "middel", "hoog"]


class CodeSnippet(BaseModel):
    file_path: str = Field(description="Theme-bestand of plek, bv. 'layout/theme.liquid' of 'Shopify admin > Instellingen > Checkout'.")
    language: str = Field(description="liquid, html, js, css, json of text.")
    before: str | None = Field(default=None, description="De huidige code (letterlijk), als die bekend is.")
    after: str = Field(description="De nieuwe code of instelling.")
    explanation: str


class FixItemSubmission(BaseModel):
    """What the agent writes. Euros, effort, owner and remeasure are deliberately not
    here: they come from the registry and analyzers/actions.py after submission."""
    finding_ids: list[str] = Field(default=[], description="Alleen ids uit de findings-lijst in de context.")
    title_nl: str
    steps_nl: list[str] = Field(min_length=1)
    code_snippets: list[CodeSnippet] = []
    apps_to_remove: list[str] = []
    risk: Risk
    rollback_nl: str
    verification_checklist: list[str] = Field(min_length=1)
    verify_manually: bool = Field(default=False, description="True als een aanname niet met data of tools bevestigd kon worden.")


class FixPackageSubmission(BaseModel):
    summary_nl: str
    fixes: list[FixItemSubmission] = Field(min_length=1)
    assumptions: list[str] = []


class FixItem(FixItemSubmission):
    monthly_low: float | None = None
    monthly_high: float | None = None
    priced: bool = False
    effort: Literal["S", "M", "L"] | None = None
    effort_days_low: float | None = None
    effort_days_high: float | None = None
    owner: str | None = None
    remeasure_metric: str | None = None
    remeasure_after_days: int | None = None


class FixPackage(BaseModel):
    agent: AgentName
    summary_nl: str
    fixes: list[FixItem]
    assumptions: list[str] = []
    used_admin_data: bool = False
    warnings: list[str] = []


class FixAgentRunRequest(BaseModel):
    agents: list[AgentName] = Field(min_length=1)


class FixAgentRunOut(BaseModel):
    id: uuid.UUID
    agent: AgentName
    status: RunStatus
    result: FixPackage | None = None
    error_message: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    created_at: datetime
    completed_at: datetime | None = None


class FixAgentRunsResponse(BaseModel):
    audit_id: uuid.UUID
    has_admin_token: bool
    shopify_shop_domain: str | None = None
    runs: list[FixAgentRunOut]


class AdminTokenRequest(BaseModel):
    shop_domain: str = Field(description="De myshopify-domeinnaam, bv. 'merk.myshopify.com'.")
    access_token: str = Field(min_length=10)


class AdminTokenResponse(BaseModel):
    has_admin_token: bool
    shopify_shop_domain: str | None = None
    shop_name: str | None = None
    scopes: list[str] = []
