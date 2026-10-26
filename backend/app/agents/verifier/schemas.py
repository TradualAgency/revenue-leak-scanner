"""The verifier's output. The model only judges whether a finding holds up; what a
verdict does to the euros is decided in revenue_leak.calculate_revenue_leak."""

from typing import Literal

from pydantic import BaseModel, Field

Verdict = Literal["confirmed", "refuted", "unverifiable"]


class FindingVerdict(BaseModel):
    finding_id: str = Field(description="Alleen ids uit de findings-lijst in de context.")
    verdict: Verdict = Field(description=(
        "confirmed: met tools bevestigd. refuted: met tools aangetoond dat het probleem er "
        "niet is. unverifiable: niet te bevestigen of te weerleggen."
    ))
    evidence_nl: str = Field(description="Wat je concreet hebt gecontroleerd: tool, URL en wat je zag.")
    reason_nl: str


class VerificationSubmission(BaseModel):
    verdicts: list[FindingVerdict] = Field(min_length=1)


class VerificationReport(BaseModel):
    """Stored on RevenueLeakReport.verification — operator-only."""
    verdicts: list[FindingVerdict] = []
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    used_admin_data: bool = False
    # Per verifier group that failed: "<group>: <error>". Its findings got no verdict
    # and stay priced as the analyzers had them.
    errors: list[str] = []

    def verdict_map(self) -> dict[str, Verdict]:
        return {v.finding_id: v.verdict for v in self.verdicts}
