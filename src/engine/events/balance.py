from typing import Literal

from pydantic import Field
from engine.enums import OrderStatus, OrderType, Side
from models import CustomBaseModel
from .base import EngineEventBase
from .enums import BalanceEventType


class BalanceEventBase(EngineEventBase):
    user_id: str
    version: int = 1


class CashBalanceIncreasedEvent(BalanceEventBase):
    type: Literal[BalanceEventType.CASH_BALANCE_INCREASED] = (
        BalanceEventType.CASH_BALANCE_INCREASED
    )
    amount: float


class CashBalanceDecreasedEvent(BalanceEventBase):
    type: BalanceEventType = BalanceEventType.CASH_BALANCE_DECREASED
    amount: float


class CashEscrowIncreasedEvent(BalanceEventBase):
    type: Literal[BalanceEventType.CASH_ESCROW_INCREASED] = (
        BalanceEventType.CASH_ESCROW_INCREASED
    )
    amount: float


class CashEscrowDecreasedEvent(BalanceEventBase):
    type: Literal[BalanceEventType.CASH_ESCROW_DECREASED] = (
        BalanceEventType.CASH_ESCROW_DECREASED
    )
    amount: float


class AssetBalanceIncreasedEvent(BalanceEventBase):
    type: Literal[BalanceEventType.ASSET_BALANCE_INCREASED] = (
        BalanceEventType.ASSET_BALANCE_INCREASED
    )
    symbol: str
    amount: float


class AssetBalanceDecreasedEvent(BalanceEventBase):
    type: Literal[BalanceEventType.ASSET_BALANCE_DECREASED] = (
        BalanceEventType.ASSET_BALANCE_DECREASED
    )
    symbol: str
    amount: float


class AssetEscrowIncreasedEvent(BalanceEventBase):
    type: Literal[BalanceEventType.ASSET_ESCROW_INCREASED] = (
        BalanceEventType.ASSET_ESCROW_INCREASED
    )
    symbol: str
    amount: float


class AssetEscrowDecreasedEvent(BalanceEventBase):
    type: Literal[BalanceEventType.ASSET_ESCROW_DECREASED] = (
        BalanceEventType.ASSET_ESCROW_DECREASED
    )
    symbol: str
    amount: float


class AssetBalanceSnapshotOrder(CustomBaseModel):
    order_id: str
    order_type: OrderType
    side: Side
    quantity: float
    executed_quantity: float
    avg_fill_price: float
    status: OrderStatus
    limit_price: float | None = Field(None, gt=0.0)
    stop_price: float | None = Field(None, gt=0.0)


class AssetBalanceSnapshotEvent(BalanceEventBase):
    type: Literal[BalanceEventType.ASSET_BALANCE_SNAPSHOT] = (
        BalanceEventType.ASSET_BALANCE_SNAPSHOT
    )
    symbol: str
    available_asset_balance: int
    available_cash_balance: float


class AskSettledEvent(BalanceEventBase):
    type: Literal[BalanceEventType.ASK_SETTLED] = BalanceEventType.ASK_SETTLED
    symbol: str
    quantity: float
    price: float
    asset_escrow_decreased: AssetEscrowDecreasedEvent
    asset_balance_decreased: AssetBalanceDecreasedEvent
    cash_balance_increased: CashBalanceIncreasedEvent


class BidSettledEvent(BalanceEventBase):
    type: Literal[BalanceEventType.BID_SETTLED] = BalanceEventType.BID_SETTLED
    symbol: str
    quantity: float
    price: float
    cash_escrow_decreased: CashEscrowDecreasedEvent
    cash_balance_decreased: CashBalanceDecreasedEvent
    asset_balance_increased: AssetBalanceIncreasedEvent
