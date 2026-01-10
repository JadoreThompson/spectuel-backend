from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from api.dependencies import depends_db_sess
from api.shared.models import PaginatedResponse
from api.utils import put_command
from config import KAFKA_COMMANDS_TOPIC, PAGE_SIZE
from db_models import Instruments, Orders, Trades
from engine.commands import NewInstrumentCommand
from engine.enums import TimeFrame
from engine.events import NewTradeEvent
from .controller import calculate_24h_stats, get_24h_stats_all, get_ohlc_data
from .models import InstrumentCreate, OHLC, InstrumentRead, Stats24h


route = APIRouter(prefix="/instruments", tags=["instrument"])


@route.post("/", status_code=201)
async def create_instrument(
    body: InstrumentCreate,
    db_sess: AsyncSession = Depends(depends_db_sess),
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
        await put_command(command)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Instrument already exists.")
