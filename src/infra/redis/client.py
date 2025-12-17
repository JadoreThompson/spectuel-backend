from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from config import REDIS_HOST, REDIS_PORT, REDIS_USERNAME, REDIS_PASSWORD, HTTP_REDIS_DB


kw = {
    "host": REDIS_HOST,
    "port": REDIS_PORT,
    "username": REDIS_USERNAME,
    "password": REDIS_PASSWORD,
    "db": HTTP_REDIS_DB,
}
REDIS_CLIENT = AsyncRedis(**kw)
REDIS_CLIENT_SYNC = Redis(**kw)
del kw
