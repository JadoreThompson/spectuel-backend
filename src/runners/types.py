from dataclasses import dataclass
from typing import Any, Type

from runners import BaseRunner


@dataclass
class RunnerConfig:
    cls: Type[BaseRunner]
    args: tuple[Any]
    kwargs: dict[str, Any]
    name: str