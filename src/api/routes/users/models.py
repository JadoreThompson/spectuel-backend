from typing import Literal, TypeAlias

from pydantic import BaseModel


HistoryInterval: TypeAlias = Literal["1d", "1w", "1m", "3m", "6m", "1y"]


class UserOverviewResponse(BaseModel):
    cash_balance: float
    portfolio_balance: float
    balances: dict[str, tuple[float, float]]  # { BTC-USD: [100, $2000] }