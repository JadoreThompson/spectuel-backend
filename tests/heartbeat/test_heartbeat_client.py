import json
import time
import pytest
from unittest.mock import MagicMock, patch
from src.engine.heartbeat.client import HeartbeatClient

@pytest.fixture
def mock_socket():
    with patch("socket.socket") as mock:
        sock = MagicMock()
        mock.return_value = sock
        yield sock

def test_heartbeat_client_registration(mock_socket):
    # Mock connect to not fail
    client = HeartbeatClient("127.0.0.1", 1234, "BTCUSD", heartbeat_interval=10.0)
    
    # Verify registration message sent
    mock_socket.sendall.assert_called()
    sent_data = mock_socket.sendall.call_args[0][0]
    msg = json.loads(sent_data.decode().strip())
    assert msg["type"] == "register"
    assert msg["symbol"] == "BTCUSD"
    
    # Verify thread started
    assert client._th is not None
    assert client._th.is_alive()
    
    client.close()

def test_heartbeat_client_manual_heartbeat(mock_socket):
    client = HeartbeatClient("127.0.0.1", 1234, "BTCUSD", heartbeat_interval=10.0)
    
    # Clear registration call
    mock_socket.sendall.reset_mock()
    
    client.heartbeat()
    
    mock_socket.sendall.assert_called_once()
    sent_data = mock_socket.sendall.call_args[0][0]
    msg = json.loads(sent_data.decode().strip())
    assert msg["type"] == "heartbeat"
    
    client.close()

def test_heartbeat_client_periodic_heartbeat(mock_socket):
    # Short interval for testing
    client = HeartbeatClient("127.0.0.1", 1234, "BTCUSD", heartbeat_interval=0.1)
    
    # Wait for at least one periodic heartbeat
    time.sleep(0.2)
    
    # Should have sent registration + at least one heartbeat
    assert mock_socket.sendall.call_count >= 2
    
    client.close()

def test_heartbeat_client_connection_error(mock_socket):
    client = HeartbeatClient("127.0.0.1", 1234, "BTCUSD", heartbeat_interval=0.1)
    
    # Simulate connection error on next send
    mock_socket.sendall.side_effect = BrokenPipeError()
    
    # Wait for thread to detect error
    time.sleep(0.2)
    
    assert client._hb_stop_event.is_set()
    
    client.close()

def test_heartbeat_client_on_close_callback(mock_socket):
    on_close = MagicMock()
    client = HeartbeatClient("127.0.0.1", 1234, "BTCUSD", heartbeat_interval=0.1, on_close=on_close)
    
    client.close()
    
    # Wait for thread to finish and call callback
    time.sleep(0.2)
    on_close.assert_called_once()
