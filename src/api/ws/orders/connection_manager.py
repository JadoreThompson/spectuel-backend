import asyncio
import json
import logging
from typing import Optional
from uuid import UUID

from aiokafka import AIOKafkaConsumer
from fastapi import WebSocket
from fastapi.websockets import WebSocketState
from pydantic import ValidationError
from sqlalchemy import select

from api.ws.exc import AuthenticationError
from config import (
    KAFKA_BALANCE_EVENTS_TOPIC,
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_INSTRUMENT_EVENTS_TOPIC,
    KAFKA_ORDER_EVENTS_TOPIC,
    REDIS_WS_TOKEN_PREFIX,
)
from db_models import Users
from engine.events.enums import OrderEventType, BalanceEventType
from infra.db.utils import get_db_sess
from infra.kafka import AsyncKafkaConsumer
from infra.redis import REDIS_CLIENT
from services import JWTService
from .models import AuthenticateRequest, ResponseType

logger = logging.getLogger(__name__)


class ConnectionMeta:
    """Metadata for a user's WebSocket connection"""

    def __init__(self, ws: WebSocket, user_id: str):
        self.ws = ws
        self.user_id = user_id
        self.lock = asyncio.Lock()
        self.order_events: set[OrderEventType] = set()
        self.balance_events: set[BalanceEventType] = set()


class ConnectionManager:
    """
    Manages WebSocket connections and broadcasts order/balance events to users.
    Only sends events to users who are subscribed to them.
    """

    def __init__(self):
        self._conns: dict[str, ConnectionMeta] = {}
        self._task: asyncio.Task | None = None
        self._closed_connections: asyncio.Queue[str] = asyncio.Queue()
        self._launch()

    def _launch(self) -> None:
        if self._task is not None:
            return

        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._listen())
            loop.create_task(self._cleanup_closed_connections())
        except RuntimeError:
            logger.warning("No running event loop to launch listener")

    async def connect(self, ws: WebSocket) -> str:
        """Accept and register a new WebSocket connection"""
        await ws.accept()

        try:
            msg = await asyncio.wait_for(ws.receive_text(), timeout=10.0)
            data = json.loads(msg)
            token = data.get("token")

            if not token:
                raise AuthenticationError("Token is required")

            redis_key = f"{REDIS_WS_TOKEN_PREFIX}{token}"
            jwt_string = await REDIS_CLIENT.get(redis_key)

            if not jwt_string:
                raise AuthenticationError("Invalid or expired token")

            await REDIS_CLIENT.delete(redis_key)

            jwt_payload = await JWTService.validate_jwt(
                jwt_string.decode(), is_authenticated=True
            )
            user_id = str(jwt_payload.sub)

            if user_id in self._conns:
                old_conn = self._conns[user_id]
                try:
                    await old_conn.ws.close(code=1000, reason="Reconnected")
                except Exception:
                    pass

            self._conns[user_id] = ConnectionMeta(ws=ws, user_id=user_id)
            logger.info(f"User {user_id} authenticated and connected")
            return user_id

        except (ValidationError, json.JSONDecodeError):
            raise AuthenticationError("Invalid authentication request")
        except asyncio.TimeoutError:
            raise AuthenticationError("Authentication timeout")
        except Exception as e:
            logger.error(f"Connection error: {e}")
            raise AuthenticationError(str(e))

    def disconnect(self, user_id: str) -> None:
        """Mark connection for cleanup"""
        self._closed_connections.put_nowait(user_id)

    def subscribe_order_events(
        self, user_id: str, event_types: list[OrderEventType]
    ) -> None:
        """Subscribe user to specific order event types"""
        if user_id not in self._conns:
            raise ValueError(f"Connection for user '{user_id}' not found")

        conn = self._conns[user_id]
        for event_type in event_types:
            conn.order_events.add(event_type)

    def subscribe_balance_events(self, user_id: str, event_types: list[str]) -> None:
        """Subscribe user to specific balance event types"""
        if user_id not in self._conns:
            raise ValueError(f"Connection for user '{user_id}' not found")

        conn = self._conns[user_id]
        for event_type in event_types:
            conn.balance_events.add(event_type)

    def unsubscribe_order_events(self, user_id: str, event_types: list[str]) -> None:
        """Unsubscribe user from specific order event types"""
        if user_id not in self._conns:
            raise ValueError(f"Connection for user '{user_id}' not found")

        conn = self._conns[user_id]
        for event_type in event_types:
            conn.order_events.discard(event_type)

    def unsubscribe_balance_events(self, user_id: str, event_types: list[str]) -> None:
        """Unsubscribe user from specific balance event types"""
        if user_id not in self._conns:
            raise ValueError(f"Connection for user '{user_id}' not found")

        conn = self._conns[user_id]
        for event_type in event_types:
            conn.balance_events.discard(event_type)

    async def _listen(self) -> None:
        """Background task: consume Kafka events and broadcast to subscribed users."""
        consumer = AIOKafkaConsumer(
            KAFKA_ORDER_EVENTS_TOPIC,
            KAFKA_BALANCE_EVENTS_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            enable_auto_commit=True,
            group_id="ws_orders_consumer",
        )

        await consumer.start()
        self._is_running = True
        logger.info("Order events listener started")

        try:
            async for msg in consumer:
                try:
                    decoded_msg = msg.value.decode().strip()
                    event = json.loads(decoded_msg)

                    # Extract user_id and event type from event
                    event_type = event.get("type")
                    user_id: str | None = None
                    for k, v in msg.headers:
                        if k == "user_id":
                            user_id = v.decode()
                            break

                    if not user_id or not event_type:
                        continue

                    # Check if user is connected
                    if user_id not in self._conns:
                        continue

                    conn = self._conns[user_id]

                    if (
                        event_type in conn.order_events
                        or event_type in conn.balance_events
                    ):
                        await self._send_to_client(conn, decoded_msg)

                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                except Exception as e:
                    logger.error(f"Event processing error: {e}")

        except Exception as e:
            logger.error(f"Kafka listener error: {e}")
        finally:
            await consumer.stop()
            self._is_running = False

    async def _send_to_client(self, conn: ConnectionMeta, msg: str) -> None:
        """Send message to client with connection check"""
        try:
            if conn.ws.client_state != WebSocketState.CONNECTED:
                await self._closed_connections.put(conn.user_id)
                return

            await asyncio.wait_for(conn.ws.send_text(msg), timeout=5.0)

        except asyncio.TimeoutError:
            logger.warning(f"Send timeout for user {conn.user_id}")
            await self._closed_connections.put(conn.user_id)
        except Exception as e:
            logger.error(f"Send error for user {conn.user_id}: {e}")
            await self._closed_connections.put(conn.user_id)

    async def _cleanup_closed_connections(self) -> None:
        """Background worker that removes closed connections from the active set"""
        while True:
            try:
                user_id = await self._closed_connections.get()
                self._conns.pop(user_id, None)
                logger.info(f"Cleaned up connection for user {user_id}")
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
