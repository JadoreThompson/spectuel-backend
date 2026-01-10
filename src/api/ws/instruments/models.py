from enum import Enum

from engine.enums import TimeFrame
from models import CustomBaseModel


class RequestType(str, Enum):
    """Client request types"""

    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"


class ResponseType(str, Enum):
    """Server response types"""

    ACK = "ack"
    ERROR = "error"
    TRADE = "trade"
    OHLC_SNAPSHOT = "ohlc_snapshot"
    OHLC_UPDATE = "ohlc_update"
    ORDERBOOK_SNAPSHOT = "orderbook_snapshot"


class BarsItem(CustomBaseModel):
    """OHLC subscription item"""

    symbol: str
    timeframes: list[TimeFrame]


class SubscribeRequest(CustomBaseModel):
    """Client subscribe/unsubscribe request"""

    type: RequestType
    trades: list[str] | None = None
    orderbook: list[str] | None = None
    bars: list[BarsItem] | None = None


class OHLCData(CustomBaseModel):
    """OHLC candle data"""

    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: int


class TradeMessage(CustomBaseModel):
    """Trade event message"""

    type: str
    symbol: str
    price: float
    quantity: float
    timestamp: int
    command_id: str | None = None
    order_id: str | None = None
    role: str | None = None


class OHLCMessage(CustomBaseModel):
    """OHLC update message"""

    type: str
    symbol: str
    timeframe: str
    ohlc: OHLCData


class AckMessage(CustomBaseModel):
    """Acknowledgment message"""

    type: ResponseType
    request_type: RequestType
    subscriptions: dict


class ErrorMessage(CustomBaseModel):
    """Error message"""

    type: ResponseType
    message: str
