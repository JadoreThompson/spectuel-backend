import asyncio
import json
import logging

from sqlalchemy import update

from config import HEARTBEAT_LISTENER_PORT
from db_models import Instruments
from engine.enums import InstrumentStatus
from infra.db import get_db_sess, get_db_sess_sync
from runners.base import BaseRunner


class EngineHeartbeatRunner(BaseRunner):
    def __init__(self, host: str = "0.0.0.0", port: int = HEARTBEAT_LISTENER_PORT):
        self._host = host
        self._port = port

        # Mapping: socket_fileno -> Set[instrument_id]
        # We use file descriptor as key because the socket object itself changes or is recreated
        # but logically we need to map a "session" to instruments.
        # In asyncio, we map the StreamWriter object (transport) to instruments.
        self._connection_map: dict[asyncio.Transport, set[str]] = {}
        self._logger = logging.getLogger(self.__class__.__name__)

    def run(self) -> None:
        """Entry point for the multiprocessing.Process target."""
        asyncio.run(self._start_server())

    async def _start_server(self):
        server = await asyncio.start_server(self._handle_client, self._host, self._port)

        addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets)
        self._logger.info(f"Heartbeat Server serving on {addrs}")

        async with server:
            await server.serve_forever()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        transport = writer.transport
        addr = transport.get_extra_info("peername")
        self._logger.info(f"New engine connection from {addr}")

        self._connection_map[transport] = set()

        try:
            # Buffer for partial reads
            buffer = b""

            while not reader.at_eof():
                # Read chunks
                chunk = await reader.read(4096)
                if not chunk:
                    break

                buffer += chunk

                # Process complete messages (newline delimited)
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue

                    await self._process_message(transport, line)

        except ConnectionResetError:
            self._logger.warning(f"Connection reset by peer {addr}")
        except Exception as e:
            self._logger.error(f"Error handling client {addr}: {e}")
        finally:
            self._logger.info(f"Connection closed for {addr}")
            self._handle_disconnection(transport)
            writer.close()
            await writer.wait_closed()

    async def _process_message(self, transport: asyncio.Transport, raw_data: bytes):
        try:
            data = json.loads(raw_data.decode())
            inst_id = str(data.get("instrument_id"))
            status = data.get("status")

            # Track that this connection handles this instrument
            if transport in self._connection_map:
                self._connection_map[transport].add(inst_id)

            # If status is dead, we mark it immediately
            if status == "dead":
                await self._update_instrument_status(inst_id, InstrumentStatus.DOWN)
            else:
                # Ideally we only update DB if it was previously DOWN, to save writes.
                # For now, we assume "alive" means healthy.
                # Optimization: Cache current status in memory and only write on change.
                await self._update_instrument_status(inst_id, InstrumentStatus.UP)

        except (json.JSONDecodeError, ValueError) as e:
            self._logger.error(f"Invalid heartbeat message: {e}")

    def _handle_disconnection(self, transport: asyncio.Transport):
        """When a node disconnects, mark all its instruments as DOWN."""
        instruments = self._connection_map.pop(transport, set())

        if not instruments:
            return

        self._logger.warning(
            f"Node disconnected. Marking {len(instruments)} instruments DOWN: {instruments}"
        )

        # Bulk update in DB
        # Note: We use synchronous DB access here because it's simple and effective inside
        # the asyncio loop for this specific "cleanup" task, or we can use run_in_executor.
        # Given this is a critical state change, blocking briefly is acceptable or use async db session.
        # Since smaker_sync is available:

        try:
            with get_db_sess_sync() as db_sess:
                stmt = (
                    update(Instruments)
                    .where(Instruments.instrument_id.in_(instruments))
                    .values(status=InstrumentStatus.DOWN.value)
                )
                db_sess.execute(stmt)
                db_sess.commit()
        except Exception as e:
            self._logger.error(f"Failed to update DB on disconnection: {e}")

    async def _update_instrument_status(
        self, instrument_id: str, status: InstrumentStatus
    ):
        # To avoid hammering the DB on every heartbeat (e.g. 1000/sec),
        # we should ideally cache the last known state.
        # For this implementation, we will write direct to DB but wrapped in a try/except
        # to ensure the server doesn't crash.

        # Optimization: We can run this in a thread pool to avoid blocking the event loop
        # loop = asyncio.get_running_loop()
        # await loop.run_in_executor(None, self._db_write, instrument_id, status)

        # Simple Sync write for correctness first:
        try:
            async with get_db_sess() as db_sess:
                # Only update if changed (SQL optimization usually handles this but explicit is good)
                stmt = (
                    update(Instruments)
                    .where(Instruments.instrument_id == instrument_id)
                    .values(status=status.value)
                )
                await db_sess.execute(stmt)
                await db_sess.commit()
        except Exception as e:
            self._logger.error(f"DB Update failed for {instrument_id}: {e}")
