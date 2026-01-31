from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import depends_jwt, depends_db_sess, depends_convert_csv
from api.shared.models import PaginatedResponse
from api.types import JWTPayload
from engine.services.balance_manager import BalanceManager
from db_models import AssetBalances, Instruments, OrderEvents, BalanceEvents
from .models import (
    AssetBalanceItem,
    UserOverviewResponse,
    OrderEventRead,
    BalanceEventRead,
)


route = APIRouter(prefix="/user", tags=["user"])
balance_manager = BalanceManager("")


@route.get("/")
async def get_user_overview(
    jwt: JWTPayload = Depends(depends_jwt()),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    user_id = str(jwt.sub)
    cash_balance = balance_manager.get_cash_balance(user_id)
    escrow_balance = balance_manager.get_cash_escrow(user_id)

    query = (
        select(AssetBalances, Instruments.symbol)
        .join(Instruments, AssetBalances.instrument_id == Instruments.instrument_id)
        .where(AssetBalances.user_id == jwt.sub)
    )

    result = await db_sess.execute(query)
    asset_balances = result.all()

    portfolio_balance = 0.0

    for asset_balance, symbol in asset_balances:
        if asset_balance.balance <= 0:
            continue

        price_query = (
            select(OrderEvents.payload)
            .where(
                OrderEvents.symbol == symbol,
                OrderEvents.type.in_(["partially_filled", "filled"]),
            )
            .order_by(OrderEvents.timestamp.desc())
            .limit(1)
        )

        price_result = await db_sess.scalar(price_query)

        if price_result:
            price = price_result.get("price", 0.0)
            portfolio_balance += asset_balance.balance * price

    return UserOverviewResponse(
        cash_balance=cash_balance,
        cash_escrow_balance=escrow_balance,
        portfolio_balance=portfolio_balance,
    )


@route.get(
    "/events",
    response_model=PaginatedResponse[OrderEventRead]
    | PaginatedResponse[BalanceEventRead],
)
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

        query = (
            query.order_by(OrderEvents.timestamp.desc()).offset(skip).limit(limit + 1)
        )

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
                type=event.type,
                version=event.version,
                symbol=event.symbol,
                payload=event.payload,
                timestamp=float(event.timestamp),
            )
            for event in events_to_return
        ]

        return PaginatedResponse[OrderEventRead](
            page=(skip // limit) + 1,
            size=len(event_data),
            has_next=has_next,
            data=event_data,
        )

    elif type == "balance":
        query = select(BalanceEvents).where(BalanceEvents.user_id == user_id)

        if symbol:
            query = query.where(BalanceEvents.symbol == symbol)

        query = (
            query.order_by(BalanceEvents.timestamp.desc()).offset(skip).limit(limit + 1)
        )

        result = await db_sess.execute(query)
        events = result.scalars().all()

        has_next = len(events) > limit
        events_to_return = events[:limit]

        event_data = [
            BalanceEventRead(
                event_id=event.event_id,
                user_id=event.user_id,
                command_id=event.command_id,
                type=event.type,
                version=event.version,
                symbol=event.symbol,
                payload=event.payload,
                timestamp=float(event.timestamp),
            )
            for event in events_to_return
        ]

        return PaginatedResponse[BalanceEventRead](
            page=(skip // limit) + 1,
            size=len(event_data),
            has_next=has_next,
            data=event_data,
        )


@route.get("/asset-balances", response_model=list[AssetBalanceItem])
async def get_asset_balances(
    symbols: str | None = Query(
        None, description="Comma-separated list of symbols (e.g., BTCUSD,ETHUSD)"
    ),
    jwt: JWTPayload = Depends(depends_jwt(is_authenticated=True)),
    db_sess: AsyncSession = Depends(depends_db_sess),
    symbols_list: list[str] = Depends(depends_convert_csv("symbols", str, default=[])),
):
    """
    Retrieves asset balances for the authenticated user.
    Optionally filter by comma-separated list of symbols.

    Example: /user/asset-balances?symbols=BTCUSD,ETHUSD
    """
    user_id = jwt.sub

    query = (
        select(AssetBalances, Instruments.symbol)
        .join(Instruments, AssetBalances.instrument_id == Instruments.instrument_id)
        .where(AssetBalances.user_id == user_id)
    )

    if symbols_list:
        query = query.where(Instruments.symbol.in_(symbols_list))

    result = await db_sess.execute(query)
    balances = result.all()

    return [
        AssetBalanceItem(
            symbol=symbol,
            balance=asset_balance.balance,
            escrow_balance=asset_balance.escrow_balance,
        )
        for asset_balance, symbol in balances
    ]
