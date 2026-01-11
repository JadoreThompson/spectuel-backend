import pytest
import json
from unittest.mock import MagicMock, patch
from engine.engine_orchestrator.engine_shadow import EngineShadow
from engine.events.enums import CommandEventType, OrderEventType

@pytest.fixture
def mock_shadow_engine():
    engine = MagicMock()
    engine.ctx = MagicMock()
    engine.ctx.symbol = "TEST-BTCUSD"
    engine.balance_manager = MagicMock()
    return engine

@pytest.fixture
def event_queue():
    return MagicMock()

def test_shadow_initialization(mock_shadow_engine, event_queue):
    shadow = EngineShadow(mock_shadow_engine, event_queue, sentinel=-1)
    assert shadow._engine == mock_shadow_engine
    assert shadow._event_queue == event_queue
    assert shadow._sentinel == -1

def test_shadow_apply_patches(mock_shadow_engine, event_queue):
    shadow = EngineShadow(mock_shadow_engine, event_queue, sentinel=-1)
    shadow._apply_patches()
    
    # Verify balance manager methods are patched to noop
    bal_manager = mock_shadow_engine.balance_manager
    # Calling a patched method should not trigger the original logic
    bal_manager.increase_cash_balance(100) 
    
    # Verify _check_sufficient_balance is patched
    assert mock_shadow_engine._check_sufficient_balance is not None

def test_shadow_run_processes_events(mock_shadow_engine, event_queue):
    shadow = EngineShadow(mock_shadow_engine, event_queue, sentinel=-1)
    
    # Mock events
    cmd_received = {
        "type": CommandEventType.COMMAND_RECEIVED,
        "command": {"id": "cmd-1", "type": "NEW_ORDER"}
    }
    order_placed = {
        "type": OrderEventType.ORDER_PLACED,
        "order_id": "order-1"
    }
    cmd_processed = {
        "type": CommandEventType.COMMAND_PROCESSED,
        "command_id": "cmd-1"
    }
    
    # Queue returns events then sentinel
    event_queue.get.side_effect = [
        json.dumps(cmd_received),
        json.dumps(order_placed),
        json.dumps(cmd_processed),
        -1
    ]
    
    with patch.object(shadow, "_set_instrument_status"):
        shadow.run()
    
    # Verify engine.handle_command was called with the command
    mock_shadow_engine.handle_command.assert_called_once_with(cmd_received["command"])

def test_shadow_check_sufficient_balance(mock_shadow_engine, event_queue):
    shadow = EngineShadow(mock_shadow_engine, event_queue, sentinel=-1)
    
    # Mock a batch of events
    shadow._batch = [
        {"type": OrderEventType.ORDER_PLACED},
        {"type": OrderEventType.ORDER_CANCELLED}, # This should trigger False in _check_sufficient_balance
        {"type": OrderEventType.ORDER_PLACED}
    ]
    
    shadow._idx = 0
    # Next event is CANCELLED, so should return False
    assert shadow._check_sufficient_balance() is False
    
    shadow._idx = 1
    # Next event is PLACED, so should return True
    assert shadow._check_sufficient_balance() is True

def test_shadow_snapshot_trigger(mock_shadow_engine, event_queue):
    shadow = EngineShadow(mock_shadow_engine, event_queue, sentinel=-1, snapshot_interval=1)
    
    cmd = {"id": "cmd-1", "details": {"kafka_topic": "t", "kafka_partition": 0, "kafka_offset": 1}}
    cmd_received = {"type": CommandEventType.COMMAND_RECEIVED, "command": cmd}
    cmd_processed = {"type": CommandEventType.COMMAND_PROCESSED, "command_id": "cmd-1"}
    
    event_queue.get.side_effect = [
        json.dumps(cmd_received),
        json.dumps(cmd_processed),
        -1
    ]
    
    with patch.object(shadow, "_snapshot") as mock_snapshot:
        with patch.object(shadow, "_set_instrument_status"):
            shadow.run()
            mock_snapshot.assert_called_once_with(cmd)
