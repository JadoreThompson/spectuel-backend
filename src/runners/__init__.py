from typing import Type

from .base import BaseRunner
from .heartbeat_server_runner import HeartbeatServerRunner
from .server_runner import ServerRunner
from .services_runner import ServicesRunner
from .runner_config import RunnerConfig
from .utils import run_runner, run_runner_v2


def run_runner(runner_cls: Type[BaseRunner], *args, **kw):
    runner = runner_cls(*args, **kw)
    runner.run()


def run_runner_v2(runner_config: RunnerConfig):
    runner = runner_config.cls(*runner_config.args, **runner_config.kwargs)
    runner.run()


__all__ = [
    "BaseRunner",
    "HeartbeatServerRunner",
    "ServerRunner",
    "ServicesRunner",
    "RunnerConfig",
    "run_runner",
    "run_runner_v2",
]
