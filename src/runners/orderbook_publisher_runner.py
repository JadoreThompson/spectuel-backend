import asyncio

from engine.services.order_book_publisher import OrderBookPublisher
from .base import BaseRunner


class OrderbookPublisherRunner(BaseRunner):
    def __init__(self, snapshot_interval: float = 0.5):
        self._snapshot_interval = snapshot_interval

    def run(self):
        publisher = OrderBookPublisher(self._snapshot_interval)
        asyncio.run(publisher.run())
