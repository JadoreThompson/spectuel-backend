from aiokafka import AIOKafkaProducer
from fastapi import APIRouter, Depends, HTTPException, Query
from spectuel_engine_utils.commands import NewInstrumentCommand
from spectuel_engine_utils.enums import TimeFrame
from spectuel_engine_utils.events import NewTradeEvent
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from api.shared.models import PaginatedResponse
from api.dependencies import depends_db_sess, depends_kafka_producer
from config import KAFKA_COMMANDS_TOPIC, PAGE_SIZE
from db_models import Instruments, Orders, Trades
from .controller import calculate_24h_stats, get_24h_stats_all, get_ohlc_data
from .models import InstrumentCreate, OHLC, InstrumentRead, Stats24h


route = APIRouter(prefix="/instruments", tags=["instrument"])


@route.post("/", status_code=201)
async def create_instrument(
    body: InstrumentCreate,
    db_sess: AsyncSession = Depends(depends_db_sess),
    kafka_producer: AIOKafkaProducer = Depends(depends_kafka_producer),
):
    """Creates a new tradeable instrument."""
    try:
        inst = await db_sess.scalar(
            insert(Instruments).values(**body.model_dump()).returning(Instruments)
        )
        await db_sess.commit()
        command = NewInstrumentCommand(
            instrument_id=str(inst.instrument_id), price=body.price
        )
        await kafka_producer.send(
            KAFKA_COMMANDS_TOPIC, command.model_dump_json().encode()
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Instrument already exists.")


@route.get("/{instrument_id}/ohlc", response_model=list[OHLC])
async def get_instrument_ohlc(
    instrument_id: str,
    timeframe: TimeFrame,
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    """
    Retrieves Open-High-Low-Close (OHLC) data for a given instrument.
    Requires TimescaleDB with the timescale_toolkit extension for `time_bucket`,
    `first`, and `last` functions.
    """
    try:
        data = await get_ohlc_data(db_sess, instrument_id, timeframe)
        return data
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@route.get("/{instrument_id}/24h", response_model=Stats24h)
async def get_instrument_24h_stats(
    instrument_id: str, db_sess: AsyncSession = Depends(depends_db_sess)
):
    return await calculate_24h_stats(db_sess, instrument_id)


@route.get("/{instrument_id}/trades")
async def get_recent_trades(
    instrument_id: str,
    page: int = Query(1, ge=1),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    res = await db_sess.execute(
        select(
            Trades.price, Trades.quantity, Trades.role, Trades.executed_at, Orders.side
        )
        .where(Trades.instrument_id == instrument_id)
        .join(Orders, Orders.order_id == Trades.order_id)
        .order_by(Trades.executed_at.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE + 1)
    )
    trades = res.all()

    return PaginatedResponse(
        page=page,
        size=min(PAGE_SIZE, len(trades)),
        has_next=len(trades) > PAGE_SIZE,
        data=[
            NewTradeEvent(
                price=price,
                quantity=quantity,
                side=side,
                executed_at=executed_at,
                role=role,
            )
            for price, quantity, role, executed_at, side in trades
        ],
    )


@route.get("/")
async def get_instruments(
    instrument_id: str | None = None,
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    res = await get_24h_stats_all(db_sess, instrument_id)

    return [
        InstrumentRead(
            instrument_id=r["instrument_id"],
            volume=r["volume"],
            price=r["price"],
            h24_change=r["h24_change"],
        )
        for r in res
    ]
