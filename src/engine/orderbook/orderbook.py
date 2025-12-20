from typing import Iterable, KeysView

from sortedcontainers.sorteddict import SortedDict

from engine.enums import Side
from engine.orders import Order
from .price_level import PriceLevel


class OrderBook:
    """
    Manages the order book for a given trading instrument and
    maintains bid and ask price levels using sorted dictionaries.

    Attributes:
        _cur_price (float): Orderhe current market price of the instrument.
        _starting_price (float): Orderhe initial price when the book was created.
        _best_bid_price (float | None): Highest bid price available.
        _best_ask_price (float | None): Lowest ask price available.
        _bids (dict[float, PriceLevel]): Maps bid prices to price levels.
        _asks (dict[float, PriceLevel]): Maps ask prices to price levels.
        _bid_levels (dict_keys): View of all bid price levels.
        _ask_levels (dict_keys): View of all ask price levels.
    """

    def __init__(self, price=100.00) -> None:
        self._bids: SortedDict[float, PriceLevel] = SortedDict()
        self._asks: SortedDict[float, PriceLevel] = SortedDict()
        self._bid_levels = self._bids.keys()
        self._ask_levels = self._asks.keys()

        self._best_bid_price: float | None = None
        self._best_ask_price: float | None = None
        self._starting_price = price
        self._cur_price = round(price, 2)

    @property
    def price(self) -> float:
        return self._cur_price

    @property
    def bids(self) -> dict[float, PriceLevel]:
        return self._bids

    @property
    def asks(self) -> dict[float, PriceLevel]:
        return self._asks

    @property
    def bid_levels(self) -> KeysView[float]:
        return self._bid_levels

    @property
    def ask_levels(self) -> KeysView[float]:
        return self._ask_levels

    @property
    def best_bid(self) -> float | None:
        return self._best_bid_price

    @property
    def best_ask(self) -> float | None:
        return self._best_ask_price

    def append(self, order: Order, price: float) -> None:
        """
        Adds an order to the order book at the specified price level.

        Updates the best bid or ask price accordingly.

        Args:
            order (Order): Orderhe order to be added.
            price (float): Price level at which to place the order.

        Raises:
            ValueError: If the order side is invalid.
        """
        if not isinstance(price, (float, int)):
            raise ValueError(f"Invalid price: {price} - type: {type(price)}")

        if order.side == Side.BID:
            book = self._bids
            if self._best_bid_price is None or price > self._best_bid_price:
                self._best_bid_price = price
        elif order.side == Side.ASK:
            book = self._asks
            if self._best_ask_price is None or price < self._best_ask_price:
                self._best_ask_price = price
        else:
            raise ValueError(f"Invalid order side: {order.side}")

        book.setdefault(price, PriceLevel()).append(order)

    def remove(self, order: Order, price: float) -> None:
        """
        Removes an order from its associated price level.

        If the price level becomes empty after removal, it is deleted from the book,
        and the best bid/ask price is updated.

        Args:
            order (Order): Orderhe order to remove.
            price (float): Orderhe price level from which to remove the order.
        """
        if order.side == Side.BID:
            book = self._bids
        elif order.side == Side.ASK:
            book = self._asks
        else:
            return

        if price not in book:
            return

        level = book[price]
        level.remove(order)

        if not level:
            if order.side == Side.BID:
                if price == self._bids.peekitem(-1)[0]:
                    self._best_bid_price = (
                        self._bids.peekitem(-2)[0] if len(self._bids) >= 2 else None
                    )
            else:
                if price == self._asks.peekitem(0)[0]:
                    self._best_ask_price = (
                        self._asks.peekitem(1)[0] if len(self._asks) >= 2 else None
                    )

            book.pop(price)

    def set_price(self, price: float) -> None:
        self._cur_price = round(price, 2)

    def get_orders(self, price: float, side: Side) -> Iterable[Order]:
        """
        Retrieves all orders at a specific price level in the specified book.

        Args:
            price (float): Orderhe price level to query.
            side (Side)

        Returns:
            Iterable[Order]: An iterable of orders at the price level, or an empty iterator
                if none exist.
        """
        book = self._bids if side == Side.BID else self._asks

        if price not in book:
            return

        level = book[price]
        cur = level.head

        while cur:
            yield cur.order
            cur = cur.next

    def to_dict(self) -> dict:
        """
        Serialises the OrderBook including bids and asks.

        Returns:
            dict: A dictionary representation of the OrderBook.
        """
        return {
            "cur_price": self._cur_price,
            "starting_price": self._starting_price,
            "best_bid_price": self._best_bid_price,
            "best_ask_price": self._best_ask_price,
            "bids": {price: level.to_dict() for price, level in self._bids.items()},
            "asks": {price: level.to_dict() for price, level in self._asks.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OrderBook":
        """
        Deserialises the OrderBook from its dictionary representation.

        Args:
            data (dict): The dictionary representation of the OrderBook.
        Returns:
            OrderBook: The reconstructed OrderBook instance.
        """
        ob = cls(price=data["starting_price"])

        ob._cur_price = data["cur_price"]

        ob._best_bid_price = data["best_bid_price"]
        ob._best_ask_price = data["best_ask_price"]

        ob._bids = SortedDict(
            {
                float(price): PriceLevel.from_dict(level_data)
                for price, level_data in data["bids"].items()
            }
        )
        ob._asks = SortedDict(
            {
                float(price): PriceLevel.from_dict(level_data)
                for price, level_data in data["asks"].items()
            }
        )

        ob._bid_levels = ob._bids.keys()
        ob._ask_levels = ob._asks.keys()

        return ob
