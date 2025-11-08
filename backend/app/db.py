from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import PathConfig


def build_engine(paths: PathConfig) -> AsyncEngine:
    database_url = f"sqlite+aiosqlite:///{paths.database_path}"
    return create_async_engine(database_url, future=True, echo=False)


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_models(engine: AsyncEngine, base_model: type) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(base_model.metadata.create_all)


@asynccontextmanager
async def session_scope(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    session = session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
