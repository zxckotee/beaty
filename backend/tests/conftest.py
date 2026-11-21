import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://beaty:beaty@localhost:5432/beaty")
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "test-key")
os.environ.setdefault("JWT_SECRET", "test-jwt")


import asyncio  # noqa: E402
import secrets  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402
from datetime import UTC, datetime, time, timedelta  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402


@pytest.fixture(autouse=True)
async def _reset_redis_between_tests() -> AsyncIterator[None]:
    """Redis client is process-global; pytest-asyncio uses a new loop per test."""
    yield
    from app.core.redis_client import close_redis

    await close_redis()


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Real Postgres session (NullPool: every test runs in its own event loop); skipped when the DB is down."""
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    try:
        async with asyncio.timeout(3):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1 FROM time_cell LIMIT 1"))
    except Exception as exc:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f"database with migrations is not available: {exc}")
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


def tomorrow_at(hhmm: str, days: int = 1) -> datetime:
    tz = ZoneInfo("Europe/Moscow")
    day = datetime.now(tz).date() + timedelta(days=days)
    return datetime.combine(day, time.fromisoformat(hhmm), tzinfo=tz).astimezone(UTC)


def next_open_weekday_moscow(*, days_ahead: int = 1) -> date:
    """Next calendar date in Europe/Moscow on a weekday (Mon–Fri), at least `days_ahead` from today."""
    tz = ZoneInfo("Europe/Moscow")
    day = datetime.now(tz).date() + timedelta(days=days_ahead)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def random_telegram_id() -> int:
    return secrets.randbelow(10**12) + 10**10
