from enum import Enum

from engine.events.enums import OrderEventType, BalanceEventType
from models import CustomBaseModel


class SubscriptionType(str, Enum):
    """Event types users can subscribe to"""

    ORDER = "order"
    BALANCE = "balance"


class RequestType(str, Enum):
    """Client request types"""

    AUTHENTICATE = "auth"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"


class ResponseType(str, Enum):
    """Server response types"""

    ACK = "ack"
    ERROR = "error"
    ORDER_EVENT = "order_event"
    BALANCE_EVENT = "balance_event"


class AuthenticateRequest(CustomBaseModel):
    """Initial authentication request"""

    type: RequestType
    token: str


class SubscribeRequest(CustomBaseModel):
    """Subscribe to order/balance events"""

    type: RequestType
    order_events: list[OrderEventType] | None = None 
    balance_events: list[BalanceEventType] | None = None


class UnsubscribeRequest(CustomBaseModel):
    """Unsubscribe from order/balance events"""

    type: RequestType
    order_events: list[str] | None = None
    balance_events: list[str] | None = None


class AckMessage(CustomBaseModel):
    """Acknowledgment message"""

    type: ResponseType
    request_type: RequestType
    subscriptions: dict


class ErrorMessage(CustomBaseModel):
    """Error message"""

    type: ResponseType
    message: str
