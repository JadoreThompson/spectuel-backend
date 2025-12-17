from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar


T = TypeVar("T")


class StoreBase(ABC, Generic[T]):
    @abstractmethod
    def add(self, value: T) -> None: ...

    @abstractmethod
    def remove(self, value: T) -> T | None: ...

    @abstractmethod
    def get(self, value: Any) -> T | None: ...
