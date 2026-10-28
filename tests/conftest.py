import os
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from app.db import Base

os.environ.setdefault('DATABASE_URL', 'sqlite+aiosqlite:///./test_swissotel.db')

@pytest.fixture
async def db_engine():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:', poolclass=StaticPool, connect_args={'check_same_thread': False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.fixture
async def db(db_engine):
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as session:
        yield session
