import asyncio
import logging

from engine.services.event_handlers import KafkaFanout, OrderEventHandler, BalanceEventHandler
from engine.services.order_book_publisher import OrderBookPublisher
from infra.redis import REDIS_CLIENT
from runners import BaseRunner


class ServicesRunner(BaseRunner):
    def __init__(self) -> None:
        super().__init__()
        self._tasks: set[asyncio.Task] = set()
        self._logger = logging.getLogger(type(self).__name__)

    def run(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        services = (
            KafkaFanout(redis_client=REDIS_CLIENT),
            OrderBookPublisher(snapshot_interval=0.5),
            OrderEventHandler(),
            BalanceEventHandler()
        )

        self._logger.info("Starting services...")

        for service in services:
            task = asyncio.create_task(service.run(), name=type(service).__name__)
            task.add_done_callback(self._task_done_cb)
            self._tasks.add(task)
            
        self._logger.info("All services started.")
        fut = asyncio.get_running_loop().create_future()
        await fut

    def _task_done_cb(self, task: asyncio.Task) -> None:
        """Relaunches the task on failure"""
        exc = task.exception()
        if exc is not None:
            self._logger.info(f"Relaunching failed taks '{task.get_name()}'")
