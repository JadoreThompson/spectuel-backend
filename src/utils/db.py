import configparser
import os
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from typing import AsyncGenerator, Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, Session

from config import DB_USERNAME, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME, PARENT_PATH


DB_ENGINE = create_async_engine(
    f"postgresql+asyncpg://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
DB_ENGINE_SYNC = create_engine(
    f"postgresql+psycopg2://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

smaker = sessionmaker(bind=DB_ENGINE, class_=AsyncSession, expire_on_commit=False)
smaker_sync = sessionmaker(bind=DB_ENGINE_SYNC, class_=Session, expire_on_commit=False)


@asynccontextmanager
async def get_db_sess() -> AsyncGenerator[AsyncSession, None]:
    global smaker

    async with smaker.begin() as session:
        try:
            yield session
        except:
            await session.rollback()
            raise


@contextmanager
def get_db_sess_sync() -> Generator[Session, None, None]:
    global smaker_sync

    with smaker_sync.begin() as sess:
        yield sess


def write_db_url_alembic():
    db_password = DB_PASSWORD.replace("%", "%%")
    db_url = f"postgresql+psycopg2://{DB_USERNAME}:{db_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    config = configparser.ConfigParser()
    fp = os.path.join(PARENT_PATH, "alembic.ini")
    config.read(fp)
    config["alembic"]["sqlalchemy.url"] = db_url
    with open(fp, "w") as f:
        config.write(f)
