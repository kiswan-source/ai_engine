"""SQLAlchemy async connection pool."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from api.config import settings
from core.utils.logger import get_logger

logger = get_logger(__name__)

_engine_kwargs = {"pool_pre_ping": True, "echo": settings.DEBUG}
if not settings.DATABASE_URL.startswith("sqlite"):
    # pool_size/max_overflow are Postgres-pool-specific — sqlite's aiosqlite
    # dialect uses NullPool and rejects them outright (found live, Tahap 32:
    # the MCP Server subprocess crashed at import time the first time a test
    # pointed DATABASE_URL at sqlite, since this module-level engine builds
    # unconditionally on import regardless of whether it's ever used).
    _engine_kwargs.update(pool_size=10, max_overflow=20)

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

AsyncSessionFactory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def init_db():
    # Import registers the ORM models on Base.metadata; without it create_all
    # sees an empty metadata and silently creates nothing.
    import db.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured")


async def close_db():
    await engine.dispose()


async def get_db_status() -> str:
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
        return "ok"
    except Exception as e:
        return f"error: {e}"


async def get_session() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        yield session
