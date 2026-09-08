"""Test-wide fixtures. Sets an isolated SQLite file DB *before* any app
module is imported, since app.core.config.get_settings() is lru_cached and
app.db.base creates the engine at import time based on it."""
import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_kundaliai.db"
os.environ["ENVIRONMENT"] = "test"
# The app ships with ALL_FEATURES_FREE=true (paywalls off "for now"), but the
# tier-gating/quota logic itself still needs real coverage for whenever it's
# switched back on — so tests run with it explicitly off, and
# test_feature_gating.py separately verifies the ALL_FEATURES_FREE bypass.
os.environ["ALL_FEATURES_FREE"] = "false"

import pathlib

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_db():
    yield
    db_path = pathlib.Path("test_kundaliai.db")
    try:
        if db_path.exists():
            db_path.unlink()
    except PermissionError:
        pass  # Windows may still hold the file handle briefly; not worth failing the suite over


@pytest_asyncio.fixture
async def client():
    # Import app.main (and therefore every app.db.models module, transitively)
    # BEFORE create_all_tables() — otherwise Base.metadata is still empty on
    # the very first call and create_all() silently creates nothing.
    from app.main import app

    from app.db.base import Base, create_all_tables, engine

    await create_all_tables()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Clean all tables between tests so each test starts from a blank slate
    # without needing to recreate the whole engine.
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
