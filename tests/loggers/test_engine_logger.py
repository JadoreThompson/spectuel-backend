import pytest
import json
from unittest.mock import MagicMock, patch
from src.engine.loggers.engine_logger import EngineLogger
from src.engine.events.enums import OrderEventType, BalanceEventType
from src.engine.enums import Side, StrategyType, OrderType, EngineEventCategory

@pytest.fixture(autouse=True)
def reset_engine_logger():
    # Clear singleton instances before each test
    EngineLogger._instances = {}
    yield

@pytest.fixture
def mock_producer():
    with patch("src.engine.loggers.engine_logger.KafkaProducer") as producer_cls:
        producer = MagicMock()
        producer_cls.return_value = producer
        # Update the class attribute as well since it's initialized at class level
        EngineLogger._producer = producer
        yield producer

def test_engine_logger_singleton():
    logger1 = EngineLogger("test-logger")
    logger2 = EngineLogger("test-logger")
    assert logger1 is logger2

    logger3 = EngineLogger("different-logger")
    assert logger1 is not logger3 # Wait, the implementation uses (cls, name) as key
    # Let's re-verify the implementation:
    # 84:         key = (cls, name)
    # 85:         if key in cls._instances:
    # 86:             return cls._instances[key]
    # So logger1 and logger3 should be DIFFERENT.

def test_engine_logger_different_names():
    logger1 = EngineLogger("logger1")
    logger2 = EngineLogger("logger2")
    assert logger1 is not logger2

import uuid

def test_log_event_calls_producer(mock_producer):
    from config import KAFKA_ENGINE_EVENTS_TOPIC
    logger = EngineLogger("test")
    event = {"type": "TEST_EVENT", "data": "info"}
    logger.log_event(event)
    
    mock_producer.send.assert_called_once()
    args = mock_producer.send.call_args
    assert args[0][0] == KAFKA_ENGINE_EVENTS_TOPIC
    assert json.loads(args[0][1].decode()) == event

def test_log_order_event_validation(mock_producer, user_id_a, command_id):
    logger = EngineLogger("test")
    order_id = str(uuid.uuid4())
    
    # Valid order event
    logger.log_order_event(
        user_id_a,
        type=OrderEventType.ORDER_PLACED,
        order_id=order_id,
        command_id=command_id,
        symbol="BTCUSD",
        side=Side.BID,
        quantity=10.0,
        executed_quantity=0.0,
        price=50000.0,
        strategy_type=StrategyType.SINGLE,
        order_type=OrderType.LIMIT,
        timestamp=123456789
    )
    
    mock_producer.send.assert_called_once()
    headers = mock_producer.send.call_args[1]["headers"]
    header_dict = {k: v.decode() for k, v in headers}
    assert header_dict["user_id"] == user_id_a
    assert header_dict["event_category"] == EngineEventCategory.ORDER

def test_log_balance_event_validation(mock_producer, user_id_a, command_id):
    logger = EngineLogger("test")
    
    logger.log_balance_event(
        user_id_a,
        type=BalanceEventType.CASH_BALANCE_INCREASED,
        command_id=command_id,
        amount=1000.0,
        timestamp=123456789
    )
    
    mock_producer.send.assert_called_once()
    headers = mock_producer.send.call_args[1]["headers"]
    header_dict = {k: v.decode() for k, v in headers}
    assert header_dict["user_id"] == user_id_a
    assert header_dict["event_category"] == EngineEventCategory.BALANCE

def test_hooks_are_called(mock_producer):
    on_log_event = MagicMock()
    on_log_command_event = MagicMock()
    logger = EngineLogger("test", on_log_event=on_log_event, on_log_command_event=on_log_command_event)
    
    event = {"type": "TEST"}
    logger.log_event(event)
    on_log_event.assert_called_once()
    
    logger.log_command_event(cmd_id=str(uuid.uuid4()))
    on_log_command_event.assert_called_once()

def test_ignore_system_user(mock_producer, command_id):
    from src.engine.config import SYSTEM_USER_ID
    logger = EngineLogger("test")
    
    # Should be ignored
    logger.log_order_event(
        SYSTEM_USER_ID,
        type=OrderEventType.ORDER_PLACED,
        order_id=str(uuid.uuid4()),
        command_id=command_id,
        symbol="BTCUSD",
        side=Side.BID,
        quantity=1.0,
        executed_quantity=0.0,
        price=1.0,
        strategy_type=StrategyType.SINGLE,
        order_type=OrderType.LIMIT,
        timestamp=123
    )
    
    mock_producer.send.assert_not_called()
