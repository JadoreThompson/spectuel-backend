import asyncio
import json
import logging
import time


from sqlalchemy import update

from db_models import Instruments
from engine.enums import InstrumentStatus
from infra.db import get_db_sess
from .conn import HeartbeatConnection
from .exc import ValidationError, HeartbeatTimeoutError


class HeartbeatServer:
    """
    Asyncio-based TCP server that tracks client heartbeat messages.

    Clients must first register with a symbol. The server monitors
    periodic heartbeat messages to ensure clients are alive. If a
    client disconnects or fails to send heartbeats, its symbol is
    unregistered and status is updated in the database.
    """

    def __init__(
        self,
        host: str,
        port: int,
        register_timeout: float = 5.0,
        heartbeat_timeout: float = 5.0,
    ) -> None:
        """
        Initialize the heartbeat server.

        Args:
            host: Address to bind the server.
            port: Port to bind the server.
            register_timeout: Max seconds to wait for registration.
            heartbeat_timeout: Max seconds between heartbeat messages.
        """
        self._host: str = host
        self._port: int = port
        self._register_timeout: float = register_timeout
        self._heartbeat_timeout: float = heartbeat_timeout
        self._server: asyncio.AbstractServer | None = None
        self._symbols: dict[str, HeartbeatConnection] = {}
        self._closed_fut: asyncio.Future | None = None

        self._logger: logging.Logger = logging.getLogger(
            f"{type(self).__name__}-[{self._host}:{self._port}]"
        )

    @property
    def host(self) -> str:
        """Returns the host the server is bound to."""
        return self._host

    @property
    def port(self) -> int:
        """Returns the port the server is bound to."""
        return self._port

    async def start(self) -> None:
        """Start the server and accept incoming client connections."""
        self._server = await asyncio.start_server(
            self._client_conn_cb,
            self._host,
            self._port,
        )

        assert self._server.sockets is not None
        addr = ", ".join(str(sock.getsockname()) for sock in self._server.sockets)
        self._logger.info(f"Heartbeat server listening on {addr}")

        try:
            async with self._server:
                await self._server.serve_forever()
        finally:
            if self._closed_fut:
                self._closed_fut.set_result(True)
        

    async def stop(self) -> None:
        self._closed_fut = asyncio.get_running_loop().create_future()
        self._server.close()
        await self._closed_fut

    async def _client_conn_cb(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a connected client: register, process heartbeats, and cleanup."""
        peer = writer.get_extra_info("peername")
        self._logger.info(f"Client connected: {peer}")

        hb_conn = await self._handle_register(reader, writer)
        if hb_conn is None:
            return

        await self._set_instrument_status(hb_conn.symbol, InstrumentStatus.ALIVE)

        try:
            while True:
                try:
                    data = await asyncio.wait_for(
                        reader.readline(),
                        timeout=self._heartbeat_timeout
                    )
                except asyncio.TimeoutError:
                    raise HeartbeatTimeoutError()

                if not data:
                    break

                raw = data.decode().strip()
                self._logger.info(f"Received from {peer}: {raw}")
                msg = json.loads(raw)

                if msg.get("type") == "heartbeat":
                    hb_conn.last_message_ts = time.time()

        except HeartbeatTimeoutError:
            self._logger.info(f"Client {peer} heartbeat timeout")
        except asyncio.CancelledError:
            pass
        finally:
            if hb_conn is not None:
                self._symbols.pop(hb_conn.symbol, None)
                await self._set_instrument_status(hb_conn.symbol, InstrumentStatus.DEAD)
            await self._close_writer(writer)

    async def _handle_register(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> HeartbeatConnection | None:
        """
        Await a registration message from the client.

        Returns:
            HeartbeatConnection if registration succeeds, otherwise None.
        """
        peer = writer.get_extra_info("peername")

        try:
            data: bytes = await asyncio.wait_for(
                reader.readline(),
                timeout=self._register_timeout,
            )
            msg: dict[str, object] = json.loads(data.decode().strip())

            if msg.get("type") != "register":
                raise ValidationError("Received invalid message.")

            symbol = msg.get("symbol")
            if not isinstance(symbol, str):
                raise ValidationError("symbol field missing in register request")

            hb_conn = HeartbeatConnection(
                symbol=symbol, reader=reader, writer=writer, last_message_ts=time.time()
            )
            self._symbols[symbol] = hb_conn

            return hb_conn

        except asyncio.CancelledError:
            await self._close_writer(writer)
        except asyncio.TimeoutError:
            self._logger.info(f"Client {peer} register timeout")
            await self._close_writer(writer)
        except ValidationError as e:
            self._logger.info(f"Client error: {e}")
            writer.write(json.dumps({"type": "error", "message": str(e)}).encode())
            await writer.drain()
            await self._close_writer(writer)

    async def _close_writer(self, writer: asyncio.StreamWriter) -> None:
        """Close the client socket safely."""
        peer = writer.get_extra_info("peername")
        self._logger.info(f"Client disconnected: {peer}")
        writer.close()


    async def _set_instrument_status(self, symbol: str, status: InstrumentStatus):
        """
        Update the database status of the given symbol.

        Args:
            symbol: Symbol to update.
            status: Status to set.
        """
        async with get_db_sess() as db_sess:
            await db_sess.execute(
                update(Instruments).values(status=status.value).where(Instruments.symbol == symbol)
            )
            await db_sess.commit()
