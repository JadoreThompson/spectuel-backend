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
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT"))
REDIS_USERNAME = os.getenv("REDIS_USERNAME")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

# Kafka
KAFKA_HOST = os.getenv("KAFKA_HOST")
KAFKA_PORT = os.getenv("KAFKA_PORT")
KAFKA_BOOTSTRAP_SERVERS = f"{KAFKA_HOST}:{KAFKA_PORT}"
KAFKA_COMMANDS_TOPIC = os.getenv("KAFKA_COMMANDS_TOPIC")
KAFKA_ORDER_EVENTS_TOPIC = os.getenv("KAFKA_ORDER_EVENTS_TOPIC")
KAFKA_TRADE_EVENTS_TOPIC = os.getenv("KAFKA_TRADE_EVENTS_TOPIC")
KAFKA_INSTRUMENT_EVENTS_TOPIC = os.getenv("KAFKA_INSTRUMENT_EVENTS_TOPIC")

# Auth
COOKIE_ALIAS = "spectuel-cookie"
JWT_SECRET_KEY = os.getenv("JWT_SECRET")
JWT_ALGO = os.getenv("JWT_ALGO")
JWT_EXPIRY_SECS = int(os.getenv("JWT_EXPIRY_SECS"))

# API
PAGE_SIZE = 10

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
