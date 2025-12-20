import os
import sys

# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
import tempfile
import uuid

import fakeredis
import pytest

from src.engine.matching_engines import SpotEngine
from src.engine.execution_context import ExecutionContext
from src.engine.loggers import WALogger


@pytest.fixture(scope="session")
def redis_client():
    return fakeredis.FakeRedis()


@pytest.fixture(autouse=True)
def setup_teardown(mocker, redis_client):
    redis_client.flushall()
    mocker.patch("src.engine.infra.redis.client.REDIS_CLIENT_SYNC", redis_client)
    mocker.patch("src.engine.loggers.wal_logger.WALogger._write_event")
    yield


@pytest.fixture
def user_id_a() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def user_id_b() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def symbol() -> str:
    return "TEST-BTCUSD"


@pytest.fixture
def spot_engine(symbol):
    with tempfile.TemporaryDirectory() as f:
        with open(os.path.join(f, "0.log"), "a") as f:
            WALogger.set_file(f)
            yield SpotEngine(symbol)


@pytest.fixture
def test_ctx(spot_engine) -> ExecutionContext:
    return spot_engine._ctx
