import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.foundation.db import Base

# Load every model through the module registry so `Base.metadata` is complete
# before `create_all`.
from app.modules.registry import load_model_metadata

load_model_metadata()

from app.modules.organizations.models import Organization

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://sosnet:sosnet_dev_pw@localhost:5432/sosnet_test"
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_schema():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _ensure_storage_buckets():
    """Create the storage buckets that the app's startup event normally creates.

    Pytest has no ASGI lifespan, and upload tests need the buckets to exist in
    the real object storage."""
    from app.foundation.storage import ensure_documents_bucket, ensure_media_bucket

    ensure_media_bucket()
    ensure_documents_bucket()


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """Session wrapped in an outer transaction that is rolled back at teardown.

    The session joins via savepoints, so service-layer commits only release a
    savepoint and no data leaks between tests."""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.connect() as connection:
        await connection.begin()
        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await connection.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def organization_id(db: AsyncSession) -> uuid.UUID:
    # Optional features on, so their behaviour stays covered; tests of the
    # switched-off state turn them off explicitly.
    org = Organization(
        name=f"Test Org {uuid.uuid4()}", status="ACTIVE",
        settings={
            "feature_wallet": True, "feature_dropshipping": True, "feature_invoice_cashback": True,
            "feature_welcome_bonus": True, "feature_friend_referrals": True, "feature_profile_gate": True,
        },
    )
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org.id
