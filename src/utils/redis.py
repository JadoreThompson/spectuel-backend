from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from config import REDIS_HOST, REDIS_PASSWORD, REDIS_PORT


kw = {"host": REDIS_HOST, "port": REDIS_PORT, "password": REDIS_PASSWORD}
REDIS_CLIENT = AsyncRedis(**kw)
REDIS_CLIENT_SYNC = Redis(**kw)
del kw
