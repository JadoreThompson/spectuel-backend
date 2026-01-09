import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import depends_jwt, depends_db_sess
from api.types import JWTPayload
from engine.services.balance_manager import BalanceManager
from db_models import AssetBalances, Orders, Trades, Users
from engine.utils import get_asset_balance_key
from infra.redis.client import REDIS_CLIENT
from .controller import get_portfolio_history
from .models import HistoryInterval, PortfolioHistory, UserOverviewResponse


route = APIRouter(prefix="/user", tags=["user"])
balance_manager = BalanceManager("")


@route.get("/")
async def get_user_overview(
    jwt: JWTPayload = Depends(depends_jwt()),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    user_id = str(jwt.sub)
    cash_balance = await balance_manager.get_cash_balance(user_id)

    symbols = (await db_sess.scalars(select(distinct(Orders.symbol)))).all()

    portfolio_balance = 0.0
    balances = {}

    try:
        balances = await asyncio.gather(
            *[
                REDIS_CLIENT.get(get_asset_balance_key(symbol, user_id))
                for symbol in symbols
            ],
        )
        prices = await asyncio.gather(
            *[REDIS_CLIENT.get(symbol) for symbol in symbols],
        )
        for i in range(len(balances)):
            symbol, price, balance = symbols[i], prices[i], balances[i]
            total_value = price * balance
            portfolio_balance += total_value
            balances[symbol] = [balance, total_value]

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error occured fetching asset balances - {str(e)}"
        )

    return UserOverviewResponse(
        cash_balance=cash_balance,
        portfolio_balance=portfolio_balance,
        balances=balances,
    )
