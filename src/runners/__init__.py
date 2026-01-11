from typing import Type

from .base import BaseRunner
from .heartbeat_server_runner import HeartbeatServerRunner
from .server_runner import ServerRunner
from .services_runner import ServicesRunner
from .types import RunnerConfig


def run_runner(runner_cls: Type[BaseRunner], *args, **kw):
    runner = runner_cls(*args, **kw)
    runner.run()


__all__ = [
    "BaseRunner",
    "HeartbeatServerRunner",
    "ServerRunner",
    "ServicesRunner",
    "RunnerConfig",
    "run_runner",
]
