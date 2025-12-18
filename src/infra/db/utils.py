import configparser
import os
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator

from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import AsyncSession

from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USERNAME, PROJECT_PATH
from .client import DB_ENGINE, DB_ENGINE_SYNC


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


def write_db_url_alembic_ini():
    db_password = DB_PASSWORD.replace("%", "%%")
    db_url = f"postgresql+psycopg2://{DB_USERNAME}:{db_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    config = configparser.ConfigParser()
    fp = os.path.join(PROJECT_PATH, "alembic.ini")

    config.read(fp)
    config["alembic"]["sqlalchemy.url"] = db_url

    with open(fp, "w") as f:
        config.write(f)
