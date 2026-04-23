from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

enging = create_async_engine(settings.database_url)
AsyncSessionLocal = sessionmaker(enging, class_= AsyncSession, expire_on_commit = False)
Base = declarative_base()

async def init_db():
    async with enging.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)