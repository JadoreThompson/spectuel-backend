import asyncio
import json
import pytest
from unittest.mock import patch, AsyncMock

from src.engine.heartbeat.server import HeartbeatServer


@pytest.fixture
def mock_db_sess():
    session = AsyncMock()

    # Mock the context manager
    cm = AsyncMock()
    cm.__aenter__.return_value = session
    cm.__aexit__.return_value = None

    with patch("src.engine.heartbeat.server.get_db_sess", return_value=cm):
        yield session


@pytest.mark.asyncio
async def test_heartbeat_server_registration(mock_db_sess):
    server = HeartbeatServer("127.0.0.1", 0, register_timeout=1.0)

    # Start server in background
    server_task = asyncio.create_task(server.start())

    # Wait for server to start and get port
    while server._server is None or not server._server.sockets:
        await asyncio.sleep(0.1)

    port = server._server.sockets[0].getsockname()[1]

    # Connect client
    reader, writer = await asyncio.open_connection("127.0.0.1", port)

    # Register
    writer.write(json.dumps({"type": "register", "symbol": "BTCUSD"}).encode() + b"\n")
    await writer.drain()

    # Wait for registration to be processed
    await asyncio.sleep(0.2)

    if server_task.done():
        exc = server_task.exception()
        if exc:
            raise exc

    assert "BTCUSD" in server._symbols
    mock_db_sess.execute.assert_called()

    # Cleanup
    writer.close()
    await writer.wait_closed()
    await server.stop()
    server_task.cancel()


@pytest.mark.asyncio
async def test_heartbeat_server_timeout(mock_db_sess):
    # Short timeouts for testing, but not too short
    server = HeartbeatServer(
        "127.0.0.1", 0, register_timeout=1.0, heartbeat_timeout=0.5
    )

    server_task = asyncio.create_task(server.start())
    while server._server is None or not server._server.sockets:
        await asyncio.sleep(0.1)

    port = server._server.sockets[0].getsockname()[1]

    reader, writer = await asyncio.open_connection("127.0.0.1", port)

    # Register
    writer.write(json.dumps({"type": "register", "symbol": "ETHUSD"}).encode() + b"\n")
    await writer.drain()

    # Wait for registration to be processed
    await asyncio.sleep(0.2)
    assert "ETHUSD" in server._symbols

    # Wait for heartbeat timeout (0.5s)
    await asyncio.sleep(0.8)

    assert "ETHUSD" not in server._symbols

    # Cleanup
    writer.close()
    await server.stop()
    server_task.cancel()


@pytest.mark.asyncio
async def test_heartbeat_server_heartbeat_flow(mock_db_sess):
    server = HeartbeatServer("127.0.0.1", 0, heartbeat_timeout=0.5)

    server_task = asyncio.create_task(server.start())
    while server._server is None or not server._server.sockets:
        await asyncio.sleep(0.1)

    port = server._server.sockets[0].getsockname()[1]

    reader, writer = await asyncio.open_connection("127.0.0.1", port)

    # Register
    writer.write(json.dumps({"type": "register", "symbol": "BTCUSD"}).encode() + b"\n")
    await writer.drain()

    await asyncio.sleep(0.1)
    assert "BTCUSD" in server._symbols

    # Send heartbeats
    for _ in range(3):
        writer.write(json.dumps({"type": "heartbeat"}).encode() + b"\n")
        await writer.drain()
        await asyncio.sleep(0.2)
        assert "BTCUSD" in server._symbols

    # Cleanup
    writer.close()
    await server.stop()
    server_task.cancel()


@pytest.mark.asyncio
async def test_heartbeat_server_graceful_stop(mock_db_sess):
    server = HeartbeatServer("127.0.0.1", 0)

    server_task = asyncio.create_task(server.start())
    while server._server is None or not server._server.sockets:
        await asyncio.sleep(0.1)

    await server.stop()
    assert server_task.done()
