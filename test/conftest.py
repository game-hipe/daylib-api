import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine

from core.entitie import Base
from core.manager.database import ModelManager, SearchManager


@pytest_asyncio.fixture
async def db_engine(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def model_manager(db_engine):
    return ModelManager(db_engine)


@pytest_asyncio.fixture
async def search_manager(db_engine):
    return SearchManager(db_engine)