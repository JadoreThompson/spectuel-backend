import asyncio

from engine.services import EventHandler
from runners import BaseRunner


class EventHandlerRunner(BaseRunner):
    def run(self) -> None:
        handler = EventHandler()
        asyncio.run(handler.run())
