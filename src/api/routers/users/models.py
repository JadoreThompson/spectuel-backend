from typing import Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel

from models import CustomBaseModel


HistoryInterval: TypeAlias = Literal["1d", "1w", "1m", "3m", "6m", "1y"]


class UserOverviewResponse(BaseModel):
    cash_balance: float
    portfolio_balance: float
    balances: dict[str, tuple[float, float]]


class OrderEventRead(CustomBaseModel):
    event_id: UUID
    order_id: UUID
    user_id: UUID
    command_id: UUID
    type: str
    version: int
    payload: dict
    timestamp: float


class BalanceEventRead(CustomBaseModel):
    event_id: UUID
    user_id: UUID
    command_id: UUID
    type: str
    version: int
    symbol: str | None
    payload: dict
    timestamp: float