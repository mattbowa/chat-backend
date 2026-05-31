from urllib.parse import unquote, urlparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# asyncpg can drop the project-ref suffix from usernames like postgres.projectref
# when parsing the URL. Passing it explicitly via connect_args fixes Supabase pooler auth.
_parsed = urlparse(settings.database_url.replace("postgresql+asyncpg://", "postgresql://"))
_username = unquote(_parsed.username) if _parsed.username else None

engine = create_async_engine(
    settings.database_url,
    connect_args={"user": _username} if _username else {},
    echo=False,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
