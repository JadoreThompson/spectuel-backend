from engine.enums import TimeFrame
from models import CustomBaseModel


class BarData(CustomBaseModel):
    symbol: str
    timeframe: str
    timestamp: int
    open: float
    high: float
    low: float
    close: float


class BarsResponse(CustomBaseModel):
    bars: list[BarData]
    next_page_token: str | None = None


class BarSubscription(CustomBaseModel):
    symbol: str
    timeframes: list[TimeFrame]


class SubscribeRequest(CustomBaseModel):
    orderbooks: list[str] = []
    trades: list[str] = []
    bars: list[BarSubscription] = []


class SubscribeResponse(CustomBaseModel):
    type: str = "ack"
    request_type: str = "subscribe"
    subscriptions: dict


class BarUpdateEvent(CustomBaseModel):
    type: str = "bar_update"
    symbol: str
    timeframe: str
    timestamp: int
    open: float
    high: float
    low: float
    close: float


class TradeEvent(CustomBaseModel):
    type: str = "trade"
    symbol: str
    price: float
    quantity: float
    timestamp: float
    side: str


class OrderbookSnapshotEvent(CustomBaseModel):
    type: str = "orderbook_snapshot"
    symbol: str
    bids: list[list[float]]
    asks: list[list[float]]


class MarketStatsResponse(CustomBaseModel):
    symbol: str
    change_24h: float
    high_24h: float
    low_24h: float
    volume_24h: float
    last_price: float | None = None
