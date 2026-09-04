import hmac
from collections.abc import AsyncGenerator

from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


def require_operator_key(x_operator_key: str = Header(default="")) -> None:
    """Gates operator-only data (e.g. the Sanity CMS export, or a competitor
    benchmark run's discovery audit trail) behind a shared key. Everything else on
    these endpoints is reachable by anyone holding the (unguessable) resource UUID,
    matching the shareable-report-link model used elsewhere in the app — this key
    exists only to keep operator-only data from leaking through that same link."""
    if not settings.OPERATOR_API_KEY or not hmac.compare_digest(x_operator_key, settings.OPERATOR_API_KEY):
        raise HTTPException(status_code=403, detail="Not authorized")
