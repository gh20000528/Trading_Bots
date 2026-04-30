from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

enging = create_async_engine(settings.database_url)
AsyncSessionLocal = sessionmaker(enging, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


async def init_db():
    async with enging.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def migrate_db():
    """Idempotent: add new columns to existing tables."""
    new_cols = [
        "ALTER TABLE sent_signals ADD COLUMN IF NOT EXISTS grade   VARCHAR",
        "ALTER TABLE sent_signals ADD COLUMN IF NOT EXISTS session VARCHAR",
        "ALTER TABLE sent_signals ADD COLUMN IF NOT EXISTS sl      FLOAT",
        "ALTER TABLE sent_signals ADD COLUMN IF NOT EXISTS tp1     FLOAT",
        "ALTER TABLE sent_signals ADD COLUMN IF NOT EXISTS rr1     FLOAT",
    ]
    async with enging.begin() as conn:
        for stmt in new_cols:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass
