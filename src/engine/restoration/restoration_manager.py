from typing import Callable


Predicate = Callable[[], bool]


class RestorationManager:
    """
    This object serves the process of letting
    the WALogger know if it should commence with logging
    the event or command.
    """

    _items: dict[str, Predicate] = {}

    @classmethod
    def is_restoring(cls, name: str) -> bool:
        if name in cls._items:
            return cls._items[name]()
        return False

    @classmethod
    def set_predicate(cls, name: str, pred: Predicate) -> None:
        cls._items[name] = pred

    @classmethod
    def remove(cls, name: str) -> None:
        if name in cls._items:
            cls._items.pop(name)
