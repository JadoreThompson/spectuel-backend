import uuid
import pytest

from src.engine.enums import Side, StrategyType, OrderType

from engine.orderbook import OrderBook
from src.engine.orders import Order


@pytest.fixture
def order_factory():
    def _create_order(side, price, quantity=10):
        return Order(
            id_=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            strategy_type=StrategyType.SINGLE,
            order_type=OrderType.LIMIT,
            side=side,
            quantity=quantity,
            price=price,
        )

    return _create_order


def test_orderbook_append_bid(order_factory):
    ob = OrderBook()
    order = order_factory(Side.BID, 100)
    ob.append(order, 100)

    assert ob.best_bid == 100
    assert ob.best_ask is None
    assert len(ob.bids) == 1
    assert len(ob.asks) == 0
    assert list(ob.get_orders(100, Side.BID))[0] == order


def test_orderbook_append_ask(order_factory):
    ob = OrderBook()
    order = order_factory(Side.ASK, 101)
    ob.append(order, 101)

    assert ob.best_ask == 101
    assert ob.best_bid is None
    assert len(ob.asks) == 1
    assert len(ob.bids) == 0
    assert list(ob.get_orders(101, Side.ASK))[0] == order


def test_orderbook_best_bid_ask_update(order_factory):
    ob = OrderBook()
    ob.append(order_factory(Side.BID, 99), 99)
    ob.append(order_factory(Side.BID, 100), 100)
    ob.append(order_factory(Side.ASK, 102), 102)
    ob.append(order_factory(Side.ASK, 101), 101)

    assert ob.best_bid == 100
    assert ob.best_ask == 101


def test_orderbook_remove_order(order_factory):
    ob = OrderBook()
    order1 = order_factory(Side.BID, 100)
    order2 = order_factory(Side.BID, 100)
    ob.append(order1, 100)
    ob.append(order2, 100)

    assert len(list(ob.get_orders(100, Side.BID))) == 2

    ob.remove(order1, 100)

    remaining_orders = list(ob.get_orders(100, Side.BID))
    assert len(remaining_orders) == 1
    assert remaining_orders[0] == order2


def test_orderbook_remove_last_order_on_level(order_factory):
    ob = OrderBook()
    order = order_factory(Side.BID, 100)
    ob.append(order, 100)

    assert 100 in ob.bids
    ob.remove(order, 100)
    assert 100 not in ob.bids
    assert ob.best_bid is None


def test_orderbook_get_orders_fifo(order_factory):
    ob = OrderBook()
    order1 = order_factory(Side.ASK, 101)
    order2 = order_factory(Side.ASK, 101)
    ob.append(order1, 101)
    ob.append(order2, 101)

    orders = list(ob.get_orders(101, Side.ASK))
    assert orders[0].id == order1.id
    assert orders[1].id == order2.id


def test_orderbook_serialisation(order_factory):
    ob = OrderBook()

    o1 = order_factory(Side.ASK, 101, quantity=20)
    o2 = order_factory(Side.ASK, 101, quantity=3)
    ob.append(o1, 101)
    ob.append(o2, 101)

    dumped = ob.to_dict()
    loaded_ob = OrderBook.from_dict(dumped)

    assert len(loaded_ob.asks) == 1
    assert loaded_ob.best_ask == 101

    head = loaded_ob.asks[101].head
    assert head.order.quantity == 20
    assert head.prev is None
    assert head.next is not None

    nxt = head.next
    assert nxt.order.quantity == 3
    assert nxt.prev is head
    assert nxt.next is None


def test_orderbook_serialisation_multilevels(order_factory):
    ob = OrderBook()

    o1 = order_factory(Side.ASK, 99, quantity=3)
    o2 = order_factory(Side.ASK, 101, quantity=20)
    ob.append(o1, 99)
    ob.append(o2, 101)

    dumped = ob.to_dict()
    loaded_ob = OrderBook.from_dict(dumped)

    assert len(loaded_ob.asks) == 2
    assert loaded_ob.best_ask == 99

    head = loaded_ob.asks[99].head
    assert head.prev is None and head.next is None

    head = loaded_ob.asks[101].head
    assert head.prev is None and head.next is None


def test_orderbook_serialisation_both_book_sides(order_factory):
    ob = OrderBook()

    o1 = order_factory(Side.ASK, 99, quantity=3)
    o2 = order_factory(Side.ASK, 101, quantity=20)
    ob.append(o1, 99)
    ob.append(o2, 101)

    o3 = order_factory(Side.BID, 101, quantity=3)
    o4 = order_factory(Side.BID, 99, quantity=20)
    ob.append(o3, 101)
    ob.append(o4, 99)

    dumped = ob.to_dict()
    loaded_ob = OrderBook.from_dict(dumped)

    assert len(loaded_ob.asks) == 2
    assert loaded_ob.best_ask == 99

    head = loaded_ob.asks[99].head
    assert head.prev is None and head.next is None

    head = loaded_ob.asks[101].head
    assert head.prev is None and head.next is None

    assert len(loaded_ob.bids) == 2
    assert loaded_ob.best_ask == 99

    head = loaded_ob.bids[99].head
    assert head.prev is None and head.next is None

    head = loaded_ob.bids[101].head
    assert head.prev is None and head.next is None
