import logging
from abc import ABC, abstractmethod


class BaseEventHandler(ABC):
    def __init__(self):
        self._logger = logging.getLogger(type(self).__name__)

    @abstractmethod
    async def run(self): ...

    @abstractmethod
    async def handle_event(self, event: dict): ...
