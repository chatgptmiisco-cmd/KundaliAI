"""Async SQLAlchemy engine/session setup.

Works identically against SQLite (zero-setup local dev) and Postgres
(asyncpg) — just point DATABASE_URL at Postgres in any real deployment.
No model in this codebase relies on SQLite-specific behaviour.
"""
from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()
is_sqlite = "sqlite" in settings.database_url

_connect_args = {"check_same_thread": False} if is_sqlite else {}

engine = create_async_engine(
    settings.database_url,
    echo=settings.sql_echo,
    connect_args=_connect_args,
)

if is_sqlite:
    # SQLite's default (rollback-journal) mode allows only one writer at a
    # time and raises "database is locked" almost immediately under real
    # concurrency — which this app has plenty of (the frontend fires several
    # fetches in parallel right after onboarding). WAL mode lets readers
    # proceed without blocking on a writer, and busy_timeout makes a writer
    # that does need to wait actually wait instead of failing instantly.
    # Postgres (any real deployment) handles concurrent writers properly on
    # its own and needs none of this.
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def create_all_tables() -> None:
    """Dev convenience only — real deployments should use Alembic migrations
    (see backend/alembic/) instead of calling this."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
