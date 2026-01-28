from typing import Any, Type

from .base import BaseRunner


class RunnerConfig:
    """Configuration for instantiating and running a BaseRunner."""

    def __init__(
        self,
        cls: Type[BaseRunner],
        name: str | None = None,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
    ):
        """Initialize RunnerConfig.

        Args:
            cls: The BaseRunner subclass to instantiate
            name: Name for the runner (used for logging/identification)
            args: Positional arguments to pass to the runner constructor
            kwargs: Keyword arguments to pass to the runner constructor
        """
        self.cls = cls
        self.name = name or cls.__name__
        self.args = args or ()
        self.kwargs = kwargs or {}
