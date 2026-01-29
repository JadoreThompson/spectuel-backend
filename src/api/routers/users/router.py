import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import depends_jwt, depends_db_sess
from api.shared.models import PaginatedResponse
from api.types import JWTPayload
from engine.services.balance_manager import BalanceManager
from db_models import AssetBalances, Instruments, Orders, OrderEvents, BalanceEvents
from engine.utils import get_asset_balance_key
from infra.redis.client import REDIS_CLIENT
from .models import AssetBalanceItem, UserOverviewResponse, OrderEventRead, BalanceEventRead


route = APIRouter(prefix="/user", tags=["user"])
balance_manager = BalanceManager("")


@route.get("/")
async def get_user_overview(
    jwt: JWTPayload = Depends(depends_jwt()),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    user_id = str(jwt.sub)
    cash_balance = balance_manager.get_cash_balance(user_id)

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


@route.get("/events")
async def get_user_events(
    type: Literal["balance", "order"] = Query(...),
    symbol: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    jwt: JWTPayload = Depends(depends_jwt(is_authenticated=True)),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    """
    Retrieves user events (order or balance) with optional symbol filtering.
    Returns events in descending order of timestamp.
    """
    user_id = jwt.sub

    if type == "order":
        query = select(OrderEvents).where(OrderEvents.user_id == user_id)

        if symbol:
            query = query.where(OrderEvents.symbol == symbol)

        query = query.order_by(OrderEvents.timestamp.desc()).offset(skip).limit(limit + 1)

        result = await db_sess.execute(query)
        events = result.scalars().all()

        has_next = len(events) > limit
        events_to_return = events[:limit]

        event_data = [
            OrderEventRead(
                event_id=event.event_id,
                order_id=event.order_id,
                user_id=event.user_id,
                command_id=event.command_id,
                type=event.type.value,
                version=event.version,
                symbol=event.symbol,
                payload=event.payload,
                timestamp=float(event.timestamp),
            )
            for event in events_to_return
        ]


    elif type == "balance":
        query = select(BalanceEvents).where(BalanceEvents.user_id == user_id)

        if symbol:
            query = query.where(BalanceEvents.symbol == symbol)

        query = query.order_by(BalanceEvents.timestamp.desc()).offset(skip).limit(limit + 1)

        result = await db_sess.execute(query)
        events = result.scalars().all()

        has_next = len(events) > limit
        events_to_return = events[:limit]

        event_data = [
            BalanceEventRead(
                event_id=event.event_id,
                user_id=event.user_id,
                command_id=event.command_id,
                type=event.type.value,
                version=event.version,
                symbol=event.symbol,
                payload=event.payload,
                timestamp=float(event.timestamp),
            )
            for event in events_to_return
        ]

    return PaginatedResponse(
        page=(skip // limit) + 1,
        size=len(event_data),
        has_next=has_next,
        data=event_data,
    )


@route.get("/asset-balances", response_model=list[AssetBalanceItem])
async def get_asset_balances(
    jwt: JWTPayload = Depends(depends_jwt(is_authenticated=True)),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    """
    Retrieves all asset balances for the authenticated user.
    Returns a list of symbol and quantity pairs.
    """
    user_id = jwt.sub

    query = (
        select(AssetBalances, Instruments.symbol)
        .join(Instruments, AssetBalances.instrument_id == Instruments.instrument_id)
        .where(AssetBalances.user_id == user_id)
    )

    result = await db_sess.execute(query)
    balances = result.all()

    return [
        AssetBalanceItem(symbol=symbol, quantity=asset_balance.balance)
        for asset_balance, symbol in balances
    ]

