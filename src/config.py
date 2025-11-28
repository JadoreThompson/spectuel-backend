import logging
import os
import sys
from multiprocessing.queues import Queue as MPQueue
from urllib.parse import quote

from dotenv import load_dotenv
from redis import Redis
from redis.asyncio import Redis as RedisAsync
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine


# Paths
BASE_PATH = os.path.dirname(__file__)
PARENT_PATH = os.path.dirname(BASE_PATH)

# Env
IS_PRODUCTION = bool(os.getenv("IS_PRODUCTION"))
PYTEST_RUNNING = bool(os.getenv("PYTEST_RUNNING"))

if PYTEST_RUNNING:
    env_file = ".env.test"
elif IS_PRODUCTION:
    ".env.prod"
else:
    ".env.dev"

load_dotenv(os.path.join(PARENT_PATH, ".env.prod" if IS_PRODUCTION else ".env.dev"))

# DB
DB_USERNAME = os.getenv("DB_USERNAME")
DB_PASSWORD = quote(os.getenv("DB_PASSWORD"))
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

# Redis
redis_kwargs = {
    "host": os.getenv("REDIS_HOST"),
    "port": int(os.getenv("REDIS_PORT")),
    "password": os.getenv("REDIS_PASSWORD"),
    "db": int(os.getenv("REDIS_DB")),
}
REDIS_CLIENT_ASYNC = RedisAsync(**redis_kwargs)
REDIS_CLIENT = Redis(**redis_kwargs)
del redis_kwargs

INSTRUMENT_EVENT_CHANNEL = os.getenv("INSTRUMENT_EVENT_QUEUE", "channel-1")
ORDER_UPDATE_CHANNEL = os.getenv("ORDER_UPDATE_QUEUE", "channel-2")
CASH_BALANCE_HKEY = os.getenv("CASH_BALANCE_HKEY", "channel-3")
CASH_ESCROW_HKEY = os.getenv("CASH_ESCROW_HKEY", "channel-4")

# Auth
COOKIE_ALIAS = "spectuel-cookie"
JWT_SECRET_KEY = os.getenv("JWT_SECRET")
JWT_ALGO = os.getenv("JWT_ALGO")
JWT_EXPIRY_SECS = int(os.getenv("JWT_EXPIRY_SECS"))

# API
PAGE_SIZE = 10

# Engine
COMMAND_QUEUE: MPQueue | None = None

# Logging
logging.basicConfig(
    filename="app.log",
    filemode="a",
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(
    logging.Formatter("%(asctime)s - [%(levelname)s] - %(name)s - %(message)s")
)
logger.addHandler(handler)
del logger
