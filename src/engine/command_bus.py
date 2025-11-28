from multiprocessing.queues import Queue as MPQueueT


class CommandBus:
    _queue: MPQueueT | None = None

    @classmethod
    def initialise(cls, queue: MPQueueT) -> None:
        cls._queue = queue

    @classmethod
    def push(cls, command)