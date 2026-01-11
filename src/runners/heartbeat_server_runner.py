import asyncio

from config import (
    HEARTBEAT_ITMEOUT,
    HEARTBEAT_REGISTER_TIMEOUT,
    HEARTBEAT_SERVER_HOST,
    HEARTBEAT_SERVER_PORT,
)
from engine.heartbeat import HeartbeatServer
from .base import BaseRunner


class HeartbeatServerRunner(BaseRunner):
    def run(self):
        server = HeartbeatServer(
            host=HEARTBEAT_SERVER_HOST,
            port=HEARTBEAT_SERVER_PORT,
            register_timeout=HEARTBEAT_REGISTER_TIMEOUT,
            heartbeat_timeout=HEARTBEAT_ITMEOUT,
        )
        asyncio.run(server.start())
