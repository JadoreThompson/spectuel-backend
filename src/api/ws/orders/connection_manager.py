import asyncio
import json
from typing import Literal
from uuid import UUID

from aiokafka import AIOKafkaConsumer
from fastapi import WebSocket, WebSocketDisconnect

from api.exc import JWTError
from api.types import JWTPayload
from config import (
    KAFKA_BALANCE_EVENTS_TOPIC,
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_ORDER_EVENTS_TOPIC,
    KAFKA_TRADE_EVENTS_TOPIC,
)
from services import JWTService
from infra.redis import REDIS_CLIENT

SubscriptionTopic = Literal["balance", "order", "trade"]


class ConnectionPayload:
    def __init__(self, ws: WebSocket, jwt: JWTPayload, topics: set[SubscriptionTopic]):
        self.ws = ws
        self.jwt = jwt
        self.topics = topics
        self.lock = asyncio.Lock()


class ConnectionManager:
    def __init__(self):
        self._conns: dict[UUID, ConnectionPayload] = {}
        self._task: asyncio.Task | None = None
        self._is_running = False

    @property
    def is_running(self):
        return self._is_running

    def launch_listener(self) -> None:
        """Start background Kafka listener task (only once)."""
        if self._task:
            return

        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._listen())

    async def _listen(self):
        """Background task: consume Kafka events and broadcast to active users."""
        consumer = AIOKafkaConsumer(
            KAFKA_ORDER_EVENTS_TOPIC,
            KAFKA_BALANCE_EVENTS_TOPIC,
            KAFKA_TRADE_EVENTS_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            enable_auto_commit=True,
        )

        await consumer.start()
        self._is_running = True

        try:
            async for msg in consumer:
                headers = dict(msg.headers)
                if "user_id" not in headers:
                    continue

                user_id = headers["user_id"].decode()
                if user_id not in self._conns:
                    continue

                conn = self._conns[user_id]
                decoded_msg = msg.value.decode()
                event: dict = json.loads(decoded_msg)
                event.pop("user_id", None)
                await conn.ws.send_text(decoded_msg)
        finally:
            await consumer.stop()
            self._is_running = False

    async def connect(self, ws: WebSocket) -> UUID:
        """Accept WS, read token, validate JWT, store connection, return user_id."""
        await ws.accept()

        try:
            token = ws.query_params.get("token")

            if not token:
                raise WebSocketDisconnect(code=1008, reason="Token missing")

            exists = await REDIS_CLIENT.get(token)
            if not exists:
                raise WebSocketDisconnect(code=1008, reason="Invalid token")

            await REDIS_CLIENT.delete(token)
            # jwt = await JWTService.validate_jwt(token, False)
            jwt = JWTService.decode_jwt(token)

            if jwt.sub in self._conns:
                old_conn = self._conns.pop(jwt.sub)
                await old_conn.ws.close()

            self._conns[jwt.sub] = ConnectionPayload(ws=ws, jwt=jwt, topics=set())
            return jwt.sub

        except asyncio.TimeoutError:
            raise WebSocketDisconnect(code=1008, reason="Authentication timeout")
        except JWTError as e:
            raise WebSocketDisconnect(code=1008, reason=str(e))
        except Exception:
            raise WebSocketDisconnect(code=1008, reason="Invalid auth payload")

    def disconnect(self, user_id: UUID):
        """Remove connection from active set."""
        self._conns.pop(user_id, None)

    def subscribe(self, user_id: UUID, topic: SubscriptionTopic):
        if user_id not in self._conns:
            raise ValueError(f"Connection for '{user_id}' not found.")
        self._conns[user_id].topics.add(topic)

    def unsubscribe(self, user_id: UUID, topic: SubscriptionTopic):
        if user_id not in self._conns:
            raise ValueError(f"Connection for '{user_id}' not found.")
        self._conns[user_id].topics.discard(topic)
