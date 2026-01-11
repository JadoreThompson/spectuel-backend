import os
import tempfile
import uuid

import fakeredis
import pytest
from unittest.mock import MagicMock
import kafka

# Mock KafkaProducer BEFORE EngineLogger is imported to prevent connection attempts in tests
kafka.KafkaProducer = MagicMock

from src.engine.matching_engines import SpotEngine
from src.engine.execution_context import ExecutionContext
from src.engine.loggers import EngineLogger


@pytest.fixture(scope="session")
def redis_client():
    return fakeredis.FakeRedis()


@pytest.fixture(autouse=True)
def setup_teardown(mocker, redis_client):
    redis_client.flushall()
    mocker.patch("src.engine.infra.redis.client.REDIS_CLIENT_SYNC", redis_client)
    yield


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as dir:
        yield dir


@pytest.fixture
def user_id_a() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def user_id_b() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def command_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def symbol() -> str:
    return "TEST-BTCUSD"


@pytest.fixture
def spot_engine(symbol, tmp_dir):
    yield SpotEngine(symbol)


@pytest.fixture
def test_ctx(spot_engine) -> ExecutionContext:
    return spot_engine._ctx
