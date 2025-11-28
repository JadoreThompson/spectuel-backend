from multiprocessing.queues import Queue as MPQueue

from core.events import (
    Event,
    EventType,
    OrderEventType,
    TradeEventType,
    OrderPlacedEvent,
    OrderPartiallyFilledEvent,
    OrderFilledEvent,
    OrderModifiedEvent,
    OrderCancelledEvent,
    NewTradeEvent,
)


class EventLogger:
    queue: MPQueue | None = None

    @classmethod
    def _push(cls, ev: Event) -> None:
        if cls.queue is not None:
            cls.queue.put_nowait(ev)

    # @classmethod
    # def _log_event(cls, etype: EventType, data) -> None:
    #     ev = Event(type=etype, data=data)
    #     cls._push(ev)

    @classmethod
    def _log_event(cls, etype: EventType, data) -> None:
        ev = Event(type=etype, data=data)
        cls._push(ev)

    @classmethod
    def log_order_placed(cls, **kw) -> None:
        data = OrderPlacedEvent(**kw)
        cls._log_event(EventType.ORDER_EVENT, data)

    @classmethod
    def log_order_partially_filled(cls, **kw) -> None:
        data = OrderPartiallyFilledEvent(**kw)
        cls._log_event(EventType.ORDER_EVENT, data)

    @classmethod
    def log_order_filled(cls, **kw) -> None:
        data = OrderFilledEvent(**kw)
        cls._log_event(EventType.ORDER_EVENT, data)

    @classmethod
    def log_order_modified(cls, **kw) -> None:
        data = OrderModifiedEvent(**kw)
        cls._log_event(EventType.ORDER_EVENT, data)

    @classmethod
    def log_order_cancelled(cls, **kw) -> None:
        data = OrderCancelledEvent(**kw)
        cls._log_event(EventType.ORDER_EVENT, data)

    @classmethod
    def log_new_trade(cls, **kw) -> None:
        data = NewTradeEvent(**kw)
        cls._log_event(EventType.TRADE_EVENT, data)
