import logging
import os
import sys
from urllib.parse import quote

from dotenv import load_dotenv


# Paths
BASE_PATH = os.path.dirname(__file__)
PROJECT_PATH = os.path.dirname(BASE_PATH)

PYTEST_RUNNING = bool(os.getenv("PYTEST_VESRION"))

load_dotenv(os.path.join(PROJECT_PATH, ".env.test" if PYTEST_RUNNING else ".env"))

IS_PRODUCTION = bool(os.getenv("IS_PRODUCTION"))
NEW_USER_COMMAND_ID = os.getenv("NEW_USER_COMMAND_ID")

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
HTTP_REDIS_DB = os.getenv("HTTP_REDIS_DB")
REDIS_CANDLE_CACHE_PREFIX = os.getenv("REDIS_CANDLE_CACHE_PREFIX")
REDIS_CHANGE_USERNAME_KEY_PREFIX = os.getenv("REDIS_CHANGE_USERNAME_KEY_PREFIX")
REDIS_CHANGE_EMAIL_KEY_PREFIX = os.getenv("REDIS_CHANGE_EMAIL_KEY_PREFIX")
REDIS_CHANGE_PASSWORD_KEY_PREFIX = os.getenv("REDIS_CHANGE_PASSWORD_KEY_PREFIX")
REDIS_EMAIL_VERIFICATION_KEY_PREFIX = os.getenv("REDIS_EMAIL_VERIFICATION_KEY_PREFIX")
REDIS_EMAIL_VERIFICATION_EXPIRY_SECS = 60
REDIS_WS_TOKEN_PREFIX = os.getenv("REDIS_WS_TOKEN_PREFIX", "ws_token:")
REDIS_WS_TOKEN_TTL_SECS = int(os.getenv("REDIS_WS_TOKEN_TTL_SECS", "10"))


# Kafka
KAFKA_HOST = os.getenv("KAFKA_HOST")
KAFKA_PORT = os.getenv("KAFKA_PORT")
KAFKA_BOOTSTRAP_SERVERS = f"{KAFKA_HOST}:{KAFKA_PORT}"
KAFKA_ENGINE_EVENTS_TOPIC = os.getenv("KAFKA_ENGINE_EVENTS_TOPIC")
KAFKA_COMMANDS_TOPIC = os.getenv("KAFKA_COMMANDS_TOPIC")
KAFKA_ORDER_EVENTS_TOPIC = os.getenv("KAFKA_ORDER_EVENTS_TOPIC")
KAFKA_INSTRUMENT_EVENTS_TOPIC = os.getenv("KAFKA_INSTRUMENT_EVENTS_TOPIC")
KAFKA_BALANCE_EVENTS_TOPIC = os.getenv("KAFKA_BALANCE_EVENTS_TOPIC")


# API
PAGE_SIZE = 10
WS_HEARTBEAT_TIMEOUT_SECS = 5.0


# Auth
COOKIE_ALIAS = "spectuel-cookie"
JWT_SECRET_KEY = os.getenv("JWT_SECRET")
JWT_ALGO = os.getenv("JWT_ALGO")
JWT_EXPIRY_SECS = int(os.getenv("JWT_EXPIRY_SECS"))
JWT_SECRET = os.getenv("JWT_SECRET")
MAX_EMAIL_VERIFICATION_ATTEMPTS = 5


# Security
PW_HASH_SALT = os.getenv("PW_HASH_SALT")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
ENCRYPTION_IV_LEN = int(os.getenv("ENCRYPTION_IV_LEN"))


# Email
CUSTOMER_SUPPORT_EMAIL = os.getenv("CUSTOMER_SUPPORT_EMAIL")
BREVO_API_KEY = os.getenv("BREVO_API_KEY")


# Services
HEARTBEAT_SERVER_HOST = os.getenv("HEARTBEAT_SERVER_HOST")
HEARTBEAT_SERVER_PORT = int(os.getenv("HEARTBEAT_SERVER_PORT"))
HEARTBEAT_ITMEOUT = float(os.getenv("HEARTBEAT_ITMEOUT"))
HEARTBEAT_REGISTER_TIMEOUT = float(os.getenv("HEARTBEAT_REGISTER_TIMEOUT"))


# Logging
aiokafka_logger = logging.getLogger("aiokafka")
aiokafka_logger.setLevel(logging.WARNING)
del aiokafka_logger

kafka_logger = logging.getLogger("kafka")
kafka_logger.setLevel(logging.WARNING)
del kafka_logger

logging.basicConfig(
    filename="app.log",
    filemode="a",
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(
    logging.Formatter("%(asctime)s - [%(levelname)s] - %(name)s - %(message)s")
)
root_logger.addHandler(stream_handler)
del root_logger
