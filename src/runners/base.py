from abc import ABC, abstractmethod


class RunnerBase(ABC):
    @abstractmethod
    def run(self) -> None: ...
