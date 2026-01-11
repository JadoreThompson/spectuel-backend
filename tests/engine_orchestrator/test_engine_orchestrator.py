import pytest
import json
from unittest.mock import MagicMock, patch
from engine.engine_orchestrator.engine_orchestrator import EngineOrchestrator
from engine.enums import EngineEventCategory
from engine.restoration.engine_loader import EngineLoadContext

@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine._ctx = MagicMock()
    engine._ctx.symbol = "TEST-BTCUSD"
    engine._ctx.to_dict.return_value = {
        "symbol": "TEST-BTCUSD",
        "orderbook": {
            "starting_price": 100.0,
            "cur_price": 100.0,
            "best_bid_price": None,
            "best_ask_price": None,
            "bids": {},
            "asks": {}
        },
        "order_store": {},
        "cur_command_id": None
    }
    return engine

@pytest.fixture
def mock_loader(mock_engine):
    with patch("engine.engine_orchestrator.engine_orchestrator.EngineLoader") as loader:
        load_ctx = EngineLoadContext(
            engine=mock_engine,
            topic="test-topic",
            partition=0,
            offset=100
        )
        loader.load_engines.return_value = [load_ctx]
        yield loader

@pytest.fixture
def mock_kafka():
    with patch("engine.engine_orchestrator.engine_orchestrator.KafkaConsumer") as consumer_cls:
        consumer = MagicMock()
        consumer_cls.return_value = consumer
        yield consumer

def test_orchestrator_initialization(symbol):
    orchestrator = EngineOrchestrator(symbol, shadow=False)
    assert orchestrator._symbol == symbol
    assert orchestrator._shadow is False

def test_orchestrator_run_dispatches_commands(mock_loader, mock_kafka, mock_engine, symbol):
    orchestrator = EngineOrchestrator(symbol, shadow=False)
    
    # Mock Kafka messages
    msg = MagicMock()
    msg.headers = [
        ("event_category", EngineEventCategory.COMMAND.encode()),
        ("symbol", symbol.encode())
    ]
    msg.value = b'{"id": "cmd-1", "type": "NEW_ORDER"}'
    msg.topic = "test-topic"
    msg.partition = 0
    msg.offset = 101
    
    # We need to make the iterator stop after one message to avoid infinite loop
    mock_kafka.__iter__.return_value = iter([msg])
    
    orchestrator.run()
    
    mock_engine.handle_command.assert_called_once()
    cmd = mock_engine.handle_command.call_args[0][0]
    assert cmd["id"] == "cmd-1"
    assert cmd["details"]["kafka_offset"] == 101

def test_orchestrator_creates_shadow(mock_loader, mock_kafka, mock_engine, symbol):
    with patch("engine.engine_orchestrator.engine_orchestrator.mp.Process") as mock_process:
        mock_ps = MagicMock()
        mock_process.return_value = mock_ps
        
        orchestrator = EngineOrchestrator(symbol, shadow=True, shadow_kwargs={})
        
        # Mock Kafka to exit immediately
        mock_kafka.__iter__.return_value = iter([])
        
        orchestrator.run()
        
        assert orchestrator._shadow_ps is not None
        mock_process.assert_called_once()
        mock_ps.start.assert_called_once()

def test_orchestrator_handles_shadow_death(mock_loader, mock_kafka, mock_engine, symbol):
    with patch("engine.engine_orchestrator.engine_orchestrator.mp.Process") as mock_process:
        mock_ps = MagicMock()
        mock_ps.is_alive.return_value = False
        mock_process.return_value = mock_ps
        
        orchestrator = EngineOrchestrator(symbol, shadow=True, shadow_kwargs={})
        
        # Mock Kafka message
        msg = MagicMock()
        msg.headers = [
            ("event_category", EngineEventCategory.COMMAND.encode()),
            ("symbol", symbol.encode())
        ]
        msg.value = b'{"id": "cmd-1"}'
        msg.topic = "test-topic"
        msg.partition = 0
        msg.offset = 101
        
        mock_kafka.__iter__.return_value = iter([msg])
        
        with pytest.raises(RuntimeError, match="Shadow process has died"):
            orchestrator.run()
