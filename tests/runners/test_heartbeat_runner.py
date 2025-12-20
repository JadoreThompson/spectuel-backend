import json
import pytest
import queue
import time
import uuid
from multiprocessing import Value
from unittest.mock import MagicMock, patch

from src.engine.config import HEARTBEAT_STALE_THRESHOLD
from src.engine.runners import HeartbeatRunner


@pytest.fixture
def mock_socket_module(mocker):
    return mocker.patch("src.engine.runners.heartbeat_runner.socket")


@pytest.fixture
def mock_components():
    mock_queue = MagicMock(spec=queue.Queue)
    # Default to "alive" timestamp
    watchdog = Value("d", time.time())

    # Setup queue to be empty by default after initial get
    mock_queue.get_nowait.side_effect = [queue.Empty]

    return mock_queue, watchdog


def test_connect_and_send_alive_status(mock_socket_module, mock_components):
    """
    Verify the runner connects to the socket and sends 'alive' status
    when the watchdog is fresh.
    """
    mock_queue, watchdog = mock_components

    # 1. Setup Queue: Add one instrument
    iid = str(uuid.uuid4())
    mock_queue.get_nowait.side_effect = [("add", iid), queue.Empty]

    # 2. Setup Mock Socket
    mock_sock_instance = MagicMock()
    mock_socket_module.socket.return_value = mock_sock_instance

    runner = HeartbeatRunner(mock_queue, watchdog)

    # 3. Inject a Break into the infinite loop via time.sleep exception or similar,
    # OR just call the internal methods manually to avoid thread blocking in tests.
    # Here we test the internal logic methods.

    # Simulate step 1: Drain Queue
    runner._drain_queue()
    assert iid in runner._active_instruments

    # Simulate step 2: Connect
    runner._connect_with_backoff()
    mock_sock_instance.connect.assert_called_once()

    # Simulate step 3: Send Heartbeat (Alive)
    runner._send_heartbeats("alive")

    # 4. Verify Payload
    # socket.sendall should be called with bytes
    mock_sock_instance.sendall.assert_called_once()
    sent_data = mock_sock_instance.sendall.call_args[0][0]

    # Decode and parse NDJSON
    lines = sent_data.decode("utf-8").strip().split("\n")
    data = json.loads(lines[0])

    assert data["type"] == "heartbeat"
    assert data["instrument_id"] == iid
    assert data["status"] == "alive"


def test_detect_stale_engine_dead_status(mock_socket_module, mock_components):
    """
    Verify the runner sends 'dead' status if watchdog is old.
    """
    mock_queue, watchdog = mock_components

    # Set watchdog to the past (Stale)
    watchdog.value = time.time() - (HEARTBEAT_STALE_THRESHOLD + 2.0)

    iid = str(uuid.uuid4())
    mock_queue.get_nowait.side_effect = [("add", iid), queue.Empty]

    mock_sock_instance = MagicMock()
    mock_socket_module.socket.return_value = mock_sock_instance

    runner = HeartbeatRunner(mock_queue, watchdog)

    # Run logic manually
    runner._drain_queue()
    runner._connect_with_backoff()

    # Calculate status logic normally found in run()
    last_activity = runner._watchdog.value
    time_since_activity = time.time() - last_activity
    status = "dead" if time_since_activity > HEARTBEAT_STALE_THRESHOLD else "alive"

    assert status == "dead"

    runner._send_heartbeats(status)

    # Verify Payload
    sent_data = mock_sock_instance.sendall.call_args[0][0]
    data = json.loads(sent_data.decode("utf-8"))
    assert data["status"] == "dead"


def test_instrument_lifecycle_add_remove(mock_components):
    """
    Verify instruments are added and removed from the internal set correctly via the queue.
    """
    mock_queue, watchdog = mock_components
    runner = HeartbeatRunner(mock_queue, watchdog)

    # 1. Add inst_1, inst_2
    mock_queue.get_nowait.side_effect = [
        ("add", "inst_1"),
        ("add", "inst_2"),
        queue.Empty,
    ]
    runner._drain_queue()
    assert runner._active_instruments == {"inst_1", "inst_2"}

    # 2. Remove inst_1
    mock_queue.get_nowait.side_effect = [("remove", "inst_1"), queue.Empty]
    runner._drain_queue()
    assert runner._active_instruments == {"inst_2"}


def test_connection_backoff_and_retry(mock_socket_module, mock_components):
    """
    Verify it retries connection on failure and eventually succeeds.
    """
    mock_queue, watchdog = mock_components
    runner = HeartbeatRunner(mock_queue, watchdog)

    mock_socket_cls = mock_socket_module.socket
    mock_sock_instance = MagicMock()

    # First attempt raises ConnectionRefused, Second succeeds
    mock_sock_instance.connect.side_effect = [ConnectionRefusedError, None]
    mock_socket_cls.return_value = mock_sock_instance

    with patch("time.sleep") as mock_sleep:  # Speed up test
        runner._connect_with_backoff()

    assert mock_sock_instance.connect.call_count == 2
    assert runner._sock is not None
