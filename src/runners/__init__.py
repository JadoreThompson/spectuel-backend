from typing import Type

from .base import BaseRunner
from .server_runner import ServerRunner
from .services_runner import ServicesRunner
from .types import RunnerConfig


def run_runner(runner_cls: Type[BaseRunner], *args, **kw):
    runner = runner_cls(*args, **kw)
    runner.run()


__all__ = [
    "BaseRunner",
    "ServerRunner",
    "ServicesRunner",
    "RunnerConfig",
    "run_runner",
]
