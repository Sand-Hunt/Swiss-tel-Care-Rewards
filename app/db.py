from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from .config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str | None = None):
    url = database_url or get_settings().database_url
    return create_async_engine(url, echo=False)


engine = make_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        columns = await conn.exec_driver_sql("PRAGMA table_info(redemptions)")
        column_names = {row[1] for row in columns.fetchall()}
        if column_names and 'status' not in column_names:
            await conn.exec_driver_sql(
                "ALTER TABLE redemptions ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'pending'"
            )
        review_columns = await conn.exec_driver_sql("PRAGMA table_info(guest_reviews)")
        review_names = {row[1] for row in review_columns.fetchall()}
        if review_names and 'employee_id' not in review_names:
            await conn.exec_driver_sql('ALTER TABLE guest_reviews ADD COLUMN employee_id INTEGER REFERENCES employees(id)')
