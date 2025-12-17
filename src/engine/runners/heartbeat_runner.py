import logging
import os
import queue
import signal
import socket
import sys
import time
from multiprocessing.queues import Queue as MPQueueT

from spectuel_engine_utils.events.instrument import InstrumentHeartbeatEvent

from config import (
    HEARTBEAT_CONNECT_TIMEOUT,
    HEARTBEAT_INTERVAL,
    HEARTBEAT_LISTENER_HOST,
    HEARTBEAT_LISTENER_PORT,
    HEARTBEAT_STALE_THRESHOLD,
)
from runners import RunnerBase


class HeartbeatRunner(RunnerBase):
    def __init__(
        self,
        instrument_queue: MPQueueT,
        watchdog_ts,  # multiprocessing.Value
    ) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)
        self._queue = instrument_queue
        self._watchdog = watchdog_ts
        self._sock = None
        self._active_instruments: set[str] = set()

    def run(self) -> None:
        self._logger.info("Heartbeat Socket Runner started.")

        while True:
            try:
                self._drain_queue()

                if self._sock is None:
                    self._connect_with_backoff()

                last_activity = self._watchdog.value
                time_since_activity = time.time() - last_activity
                self._logger.debug(f"Time since last activity {time_since_activity}")

                status = (
                    "dead"
                    if time_since_activity > HEARTBEAT_STALE_THRESHOLD
                    else "alive"
                )

                if status == "dead":
                    self._logger.warning(
                        f"Engine stalled (Lag: {time_since_activity:.2f}s). Sending 'dead' status."
                    )

                self._send_heartbeats(status)

                time.sleep(HEARTBEAT_INTERVAL)

            except (BrokenPipeError, ConnectionResetError, ConnectionRefusedError):
                self._logger.warning("Connection to Heartbeat Listener lost.")
                self._close_socket()
            except Exception as e:
                self._logger.error(f"Unexpected error in heartbeat runner: {e}")
                self._close_socket()
                time.sleep(1)

    def _drain_queue(self) -> None:
        """Non-blocking drain of new/removed instruments from the orchestrator."""
        while True:
            try:
                action, symbol = self._queue.get_nowait()
                if action == "add":
                    self._active_instruments.add(symbol)
                elif action == "remove":
                    self._active_instruments.discard(symbol)
            except queue.Empty:
                break

    def _connect_with_backoff(self) -> None:
        start_time = time.time()
        attempt = 0

        while self._sock is None:
            if time.time() - start_time > HEARTBEAT_CONNECT_TIMEOUT:
                self._logger.critical(
                    "FATAL: Unable to connect to Heartbeat Listener. Initiating node shutdown."
                )
                os.kill(os.getpid(), signal.SIGTERM)
                sys.exit(1)

            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                sock.connect((HEARTBEAT_LISTENER_HOST, HEARTBEAT_LISTENER_PORT))
                self._sock = sock
                self._logger.info(
                    f"Connected to Listener at {HEARTBEAT_LISTENER_HOST}:{HEARTBEAT_LISTENER_PORT}"
                )
                return
            except Exception as e:
                wait_time = min(30, (2**attempt))
                self._logger.warning(
                    f"Connection failed: {e}. Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
                attempt += 1

    def _send_heartbeats(self, status: str) -> None:
        if not self._active_instruments:
            return

        buffer = b""

        for symbol in self._active_instruments:
            event = InstrumentHeartbeatEvent(symbol=symbol, status=status)
            # Newline delimited JSON
            msg = event.model_dump_json() + "\n"
            buffer += msg.encode("utf-8")

        self._sock.sendall(buffer)

    def _close_socket(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
