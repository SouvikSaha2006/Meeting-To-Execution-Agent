"""
database.py — SQLAlchemy async engine & session factory.

Supports both SQLite (default, zero-setup) and PostgreSQL via DATABASE_URL.
"""
from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

# ── Database URL ────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv(
    "DATABASE_URL", "sqlite+aiosqlite:///./meeting_agent.db"
)

# SQLite requires check_same_thread=False, but that kwarg only applies to
# the sync driver. For aiosqlite we pass connect_args to suppress the
# default warning.  PostgreSQL needs pool_pre_ping instead.
_is_sqlite = DATABASE_URL.startswith("sqlite")

_engine_kwargs: dict = {
    "echo": os.getenv("LOG_LEVEL", "INFO").upper() == "DEBUG",
}
if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _engine_kwargs["pool_pre_ping"] = True
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["max_overflow"] = 20

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    """Declarative base shared by all ORM models."""


# ── Dependency for FastAPI route injection ───────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all tables and safely migrate new columns on startup."""
    import backend.models  # noqa: F401
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Safe SQLite column migration for new feature columns
        if _is_sqlite:
            migrations = [
                ("meetings", "readiness_score", "INTEGER DEFAULT 100"),
                ("meetings", "score_breakdown_json", "TEXT"),
                ("staging_items", "blast_radius_json", "TEXT"),
                ("staging_items", "nudge_draft", "TEXT"),
                ("staging_items", "nudged", "BOOLEAN DEFAULT 0"),
                ("staging_items", "nudge_receipt_json", "TEXT"),
                ("execution_tasks", "nudge_draft", "TEXT"),
                ("execution_tasks", "nudged", "BOOLEAN DEFAULT 0"),
                ("execution_tasks", "nudge_receipt_json", "TEXT"),
                ("execution_tasks", "reminder_sent", "BOOLEAN DEFAULT 0"),
            ]
            for tbl, col, col_type in migrations:
                try:
                    res = await conn.execute(text(f"PRAGMA table_info({tbl})"))
                    cols = [row[1] for row in res.fetchall()]
                    if col not in cols:
                        await conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_type}"))
                except Exception:
                    pass
