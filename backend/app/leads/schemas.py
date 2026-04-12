import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, field_validator


class LeadCreate(BaseModel):
    email: EmailStr
    platform: str
    store_url: str
    monthly_revenue: Decimal
    monthly_traffic: int

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, v: str) -> str:
        allowed = {"shopify", "woocommerce", "other"}
        if v.lower() not in allowed:
            raise ValueError(f"platform must be one of {allowed}")
        return v.lower()

    @field_validator("monthly_revenue")
    @classmethod
    def validate_revenue(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("monthly_revenue must be non-negative")
        return v

    @field_validator("monthly_traffic")
    @classmethod
    def validate_traffic(cls, v: int) -> int:
        if v < 0:
            raise ValueError("monthly_traffic must be non-negative")
        return v


class LeadCreateResponse(BaseModel):
    lead_id: uuid.UUID
    report_id: uuid.UUID
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
