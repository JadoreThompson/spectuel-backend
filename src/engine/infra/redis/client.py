from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from config import REDIS_HOST, REDIS_PORT, REDIS_USERNAME, REDIS_PASSWORD
from engine.config import (
    BACKUP_REDIS_DB,
    BACKUP_REDIS_HOST,
    BACKUP_REDIS_PASSWORD,
    BACKUP_REDIS_PORT,
    BACKUP_REDIS_USERNAME,
    ENGINE_REDIS_DB,
)


kw = {
    "host": REDIS_HOST,
    "port": REDIS_PORT,
    "username": REDIS_USERNAME,
    "password": REDIS_PASSWORD,
    "db": ENGINE_REDIS_DB,
}
REDIS_CLIENT = AsyncRedis(**kw)
REDIS_CLIENT_SYNC = Redis(**kw)

kw = {
    "host": BACKUP_REDIS_HOST,
    "port": BACKUP_REDIS_PORT,
    "username": BACKUP_REDIS_USERNAME,
    "password": BACKUP_REDIS_PASSWORD,
    "db": BACKUP_REDIS_DB,
}
BACKUP_REDIS_CLIENT = AsyncRedis(**kw)
BACKUP_REDIS_CLIENT_SYNC = Redis(**kw)
del kw
