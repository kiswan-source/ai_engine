"""SQLAlchemy async connection pool."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from api.config import settings
from core.utils.logger import get_logger

logger = get_logger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

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
