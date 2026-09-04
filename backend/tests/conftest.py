import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.dependencies import get_db
from app.full_audit.models import FullAudit
from app.main import app

TEST_DATABASE_URL = "postgresql+asyncpg://revleak:revleak@localhost:5432/revleak_test"
STORE_URL = "https://store.nl"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session")
async def setup_database():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session(setup_database):
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def ready_audit(db_session: AsyncSession) -> FullAudit:
    """A finished audit — the precondition for starting a competitor benchmark.

    Lives here rather than in one test module because both the competitor router tests
    and the full-audit list tests need it.
    """
    audit = FullAudit(
        id=uuid.uuid4(), store_url=STORE_URL, scan_level="outside-only",
        status="ready_for_review",
        audit_data={"store_url": STORE_URL, "scan_level": "outside-only"},
    )
    db_session.add(audit)
    await db_session.commit()
    return audit
