from typing import Type

from .base import BaseRunner
from .engine_heartbeat_runner import EngineHeartbeatRunner
from .orderbook_snapshot_runner import OrderBookSnapshotRunner
from .server_runner import ServerRunner


def run_runner(runner_cls: Type[BaseRunner], *args, **kw):
    runner = runner_cls(*args, **kw)
    runner.run()
