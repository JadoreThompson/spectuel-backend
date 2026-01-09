import logging
from abc import abstractmethod
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Type

from sqlalchemy.ext.asyncio import AsyncSession

from db_models import EventLogs
from engine.events import EngineEventBase
from infra.db import get_db_sess


class BaseEventHandler:
    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    async def run(self): ...

    @abstractmethod
    async def handle_event(self, event: dict): ...

    @asynccontextmanager
    async def _log_event(
        self, event_data: dict, event_cls: Type[EngineEventBase]
    ) -> AsyncGenerator[tuple[AsyncSession, EventLogs, EngineEventBase]]:
        event = event_cls(**event_data)

        async with get_db_sess() as db_sess:
            event_log = EventLogs(
                event_id=event.id,
                event_type=event.type,
                data=event_data,
                timestamp=event.timestamp,
            )
            db_sess.add(event_log)

            yield db_sess, event_log, event

            await db_sess.commit()
