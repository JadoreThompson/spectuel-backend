import json
import socket
import threading
import time
from typing import Any, Callable

from engine.types import HeartbeatMessage, RegisterMessage


class HeartbeatClient:
    """
    TCP client that connects to a HeartbeatServer, registers a symbol,
    and periodically sends heartbeat messages in a background thread.
    """

    def __init__(
        self,
        host: str,
        port: int,
        symbol: str,
        timeout: float = 5.0,
        heartbeat_interval: float = 5.0,
        on_close: Callable[[], Any] | None = None,
    ) -> None:
        """
        Initialize the client and start the heartbeat thread.

        Args:
            host: Heartbeat server host.
            port: Heartbeat server port.
            symbol: Symbol to register.
            timeout: Socket connection timeout.
            heartbeat_interval: Interval in seconds between heartbeats.
            on_close: An optional callback called when the connection is closed.
        """
        self._host: str = host
        self._port: int = port
        self._symbol: str = symbol
        self._heartbeat_interval = heartbeat_interval
        self.on_close = on_close

        self._sock: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(timeout)
        self._sock.connect((self._host, self._port))

        self._th: threading.Thread | None = None
        # Only set if client calls close or the server closes
        self._hb_stop_event: threading.Event = threading.Event()
        self._closed = False
        self._register()

    def _register(self) -> None:
        """
        Send a register message to the server and start the
        background thread to send periodic heartbeats.
        """
        msg: RegisterMessage = {"type": "register", "symbol": self._symbol}
        self._send(msg)

        self._th = threading.Thread(
            target=self._hb_thread_target,
            name=f"HeartbeatThread-[{self._host}:{self._port}]",
            daemon=True,  # ensures it doesn't block program exit
        )
        self._th.start()

    def heartbeat(self) -> None:
        """
        Send a heartbeat message to the server.

        Can be called manually or via the background thread.
        """
        msg: HeartbeatMessage = {"type": "heartbeat"}
        self._send(msg)

    def _hb_thread_target(self) -> None:
        """Background thread target to send periodic heartbeats."""
        while not self._hb_stop_event.is_set():
            time.sleep(self._heartbeat_interval)
            self.heartbeat()

        if self.on_close is not None:
            self.on_close()

    def _send(self, msg: dict[str, str]) -> None:
        """
        Serialize and send a JSON message to the server.

        Args:
            msg: Dictionary representing the message.
        """
        data: bytes = json.dumps(msg).encode() + b"\n"
        try:
            self._sock.sendall(data)
        except (BrokenPipeError, ConnectionResetError):
            # Socket closed or server disconnected
            self._hb_stop_event.set()

    def close(self) -> None:
        """
        Gracefully stop the heartbeat thread and close the socket.
        """
        if self._closed:
            self._closed = True

        if self._hb_stop_event is not None:
            self._hb_stop_event.set()
        if self._th is not None:
            self._th.join(
                timeout=self._heartbeat_interval + 1
            )  # wait for thread to finish
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
