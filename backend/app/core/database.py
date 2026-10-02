from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


def _create_engine() -> AsyncEngine:
    settings = get_settings()
    url = settings.database_url_value()
    is_postgres = url.startswith("postgresql+asyncpg://")
    connect_args = {"ssl": "require"} if is_postgres else {}
    pool_options = (
        {"pool_size": 5, "max_overflow": 5, "pool_recycle": 1800}
        if is_postgres
        else {}
    )
    return create_async_engine(
        url,
        pool_pre_ping=True,
        connect_args=connect_args,
        echo=False,
        **pool_options,
    )


@lru_cache
def get_engine() -> AsyncEngine:
    return _create_engine()


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session


async def dispose_engine() -> None:
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
        get_session_factory.cache_clear()
        get_engine.cache_clear()
