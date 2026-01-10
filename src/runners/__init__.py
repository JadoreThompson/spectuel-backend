from typing import Type

from .base import BaseRunner
from .engine_heartbeat_runner import EngineHeartbeatRunner
from .orderbook_publisher_runner import OrderbookPublisherRunner
from .server_runner import ServerRunner
from .types import RunnerConfig


def run_runner(runner_cls: Type[BaseRunner], *args, **kw):
    runner = runner_cls(*args, **kw)
    runner.run()


__all__ = [
    "BaseRunner",
    "EngineHeartbeatRunner",
    "OrderbookPublisherRunner",
    "ServerRunner",
    "RunnerConfig",
    "run_runner",
]
