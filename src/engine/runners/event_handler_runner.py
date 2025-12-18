import asyncio

from engine.services.event_handler import EventHandler
from runners import BaseRunner


class EventHandlerRunner(BaseRunner):
    def run(self) -> None:
        handler = EventHandler()
        asyncio.run(handler.run())
