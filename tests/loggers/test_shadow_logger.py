import pytest
import json
from unittest.mock import MagicMock, patch
from src.engine.loggers.shadow_logger import ShadowEngineLogger

@pytest.fixture(autouse=True)
def reset_engine_logger():
    from src.engine.loggers.engine_logger import EngineLogger
    EngineLogger._instances = {}
    yield

def test_shadow_logger_initialization():
    on_log_event_request = MagicMock()
    logger = ShadowEngineLogger("shadow-test", on_log_event_request=on_log_event_request)
    assert logger.name == "shadow-test"
    assert logger.on_log_event_request == on_log_event_request

def test_shadow_logger_log_event_calls_hook():
    on_log_event_request = MagicMock()
    logger = ShadowEngineLogger("shadow-test", on_log_event_request=on_log_event_request)
    
    event = {"type": "TEST_EVENT", "data": "shadow-info"}
    
    # Mock KafkaProducer to ensure it's NOT called
    with patch("src.engine.loggers.engine_logger.KafkaProducer") as producer_cls:
        producer = MagicMock()
        producer_cls.return_value = producer
        from src.engine.loggers.engine_logger import EngineLogger
        EngineLogger._producer = producer
        
        logger.log_event(event)
        
        # Verify hook was called with serialized event
        on_log_event_request.assert_called_once()
        serialized_event = on_log_event_request.call_args[0][0]
        assert json.loads(serialized_event.decode()) == event
        
        # Verify Kafka producer was NOT called
        producer.send.assert_not_called()

def test_shadow_logger_optional_hook():
    # If hook is None, it shouldn't crash
    logger = ShadowEngineLogger("shadow-test", on_log_event_request=None)
    logger.log_event({"type": "TEST"})
    # No assertion needed, just verifying it doesn't raise Exception
