from contextlib import contextmanager
from typing import AsyncGenerator, Generator, Optional

import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlmodel import SQLModel
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from core.config import settings


# Async engine — used by FastAPI endpoints and graph nodes
engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
    pool_pre_ping=True,
)

AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Sync engine — used by MCP tool functions (FastMCP runs tools synchronously)
sync_engine = create_engine(
    settings.sync_database_url,
    echo=False,
    pool_pre_ping=True,
)

SyncSessionFactory = sessionmaker(
    sync_engine,
    class_=Session,
    expire_on_commit=False,
)

# Module-level checkpointer — initialised in lifespan, reused for all runs
_checkpointer: Optional[AsyncPostgresSaver] = None
_pool = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends generator — use with Depends(get_session)."""
    async with AsyncSessionFactory() as session:
        yield session


from contextlib import asynccontextmanager

@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager — use with `async with get_async_session() as session:`."""
    async with AsyncSessionFactory() as session:
        yield session


@contextmanager
def get_sync_session() -> Generator[Session, None, None]:
    session = SyncSessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.execute(sqlalchemy.text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(SQLModel.metadata.create_all)
        # Add embedding column to existing menu_items tables that pre-date this migration.
        # create_all only creates missing tables; it never ALTERs existing ones.
        await conn.execute(sqlalchemy.text(
            "ALTER TABLE menu_items ADD COLUMN IF NOT EXISTS embedding vector(1536)"
        ))


async def init_checkpointer() -> AsyncPostgresSaver:
    """Create a long-lived AsyncPostgresSaver backed by a psycopg connection pool."""
    global _checkpointer, _pool
    import psycopg_pool

    # conn_string for psycopg (sync DSN format without +psycopg driver prefix)
    conn_str = (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )
    _pool = psycopg_pool.AsyncConnectionPool(
        conn_str,
        min_size=1,
        max_size=5,
        kwargs={"autocommit": True, "row_factory": __import__("psycopg.rows", fromlist=["dict_row"]).dict_row},
        open=False,
    )
    await _pool.open()
    _checkpointer = AsyncPostgresSaver(conn=_pool)
    await _checkpointer.setup()
    return _checkpointer


async def close_checkpointer() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_checkpointer() -> AsyncPostgresSaver:
    if _checkpointer is None:
        raise RuntimeError("Checkpointer not initialised — call init_checkpointer() first")
    return _checkpointer
