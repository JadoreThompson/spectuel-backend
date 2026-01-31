from typing import Type

from .base import BaseRunner
from .runner_config import RunnerConfig


def run_runner(runner_cls: Type[BaseRunner], *args, **kw):
    runner = runner_cls(*args, **kw)
    runner.run()


def run_runner_v2(runner_config: RunnerConfig):
    runner = runner_config.cls(*runner_config.args, **runner_config.kwargs)
    runner.run()