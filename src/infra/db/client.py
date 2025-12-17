from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine

from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USERNAME


DB_ENGINE = create_async_engine(
    f"postgresql+asyncpg://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
DB_ENGINE_SYNC = create_engine(
    f"postgresql+psycopg2://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
