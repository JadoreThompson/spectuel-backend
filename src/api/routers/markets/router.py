import base64
import json
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import depends_jwt, depends_jwt_ws, depends_db_sess
from api.types import JWTPayload
from db_models import OHLC
from engine.enums import TimeFrame
from services.ohlc_builder import OHLCBuilder
from utils import get_datetime
from .connection_manager import connection_manager
from .models import BarsResponse, BarData, SubscribeRequest, SubscribeResponse


PREFIX = "/markets"
route = APIRouter(tags=["markets"])

TIMEFRAME_LOOKBACK = {
    TimeFrame.M1: 7 * 24 * 60 * 60,
    TimeFrame.M5: 14 * 24 * 60 * 60,
    TimeFrame.M15: 30 * 24 * 60 * 60,
    TimeFrame.H1: 90 * 24 * 60 * 60,
    TimeFrame.H4: 180 * 24 * 60 * 60,
    TimeFrame.D1: 365 * 24 * 60 * 60,
}


@route.get(PREFIX + "/{symbol}/bars", response_model=BarsResponse)
async def get_market_bars(
    symbol: str,
    timeframe: TimeFrame = Query(...),
    start_date: int | None = Query(None),
    end_date: int | None = Query(None),
    next_page_token: str | None = Query(None),
    jwt: JWTPayload = Depends(depends_jwt(is_authenticated=False)),
    db_sess: AsyncSession = Depends(depends_db_sess),
):
    """
    Retrieves OHLC bars for a given symbol and timeframe.
    Supports pagination via next_page_token.
    """
    now = int(get_datetime().timestamp())

    if end_date is None:
        end_date = now
    elif end_date > now:
        raise HTTPException(
            status_code=400, detail="end_date cannot be later than the current time"
        )

    max_lookback = TIMEFRAME_LOOKBACK.get(timeframe)
    if max_lookback is None:
        raise HTTPException(status_code=400, detail="Invalid timeframe")

    earliest_allowed = now - max_lookback

    if start_date is None:
        start_date = earliest_allowed
    elif start_date < earliest_allowed:
        raise HTTPException(
            status_code=400,
            detail=f"start_date exceeds maximum lookback window for {timeframe.value}",
        )

    if next_page_token:
        try:
            decoded = base64.b64decode(next_page_token).decode()
            token_data = json.loads(decoded)
            start_date = token_data.get("start_date", start_date)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid next_page_token")

    bar_limit = 500
    query = (
        select(OHLC)
        .where(
            OHLC.symbol == symbol,
            OHLC.timeframe == timeframe.value,
            OHLC.timestamp >= start_date,
            OHLC.timestamp <= end_date,
        )
        .order_by(OHLC.timestamp.asc())
        .limit(bar_limit + 1)
    )

    result = await db_sess.execute(query)
    bars = result.scalars().all()

    has_next = len(bars) > bar_limit
    bars_to_return = bars[:bar_limit]

    next_token = None
    if has_next and bars_to_return:
        last_timestamp = bars_to_return[-1].timestamp
        token_data = {"start_date": last_timestamp + 1}
        token_json = json.dumps(token_data)
        next_token = base64.b64encode(token_json.encode()).decode()

    bar_data_list = [
        BarData(
            symbol=bar.symbol,
            timeframe=bar.timeframe,
            timestamp=bar.timestamp,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
        )
        for bar in bars_to_return
    ]

    return BarsResponse(bars=bar_data_list, next_page_token=next_token)


@route.websocket("/ws" + PREFIX)
async def market_websocket(
    ws: WebSocket,
    # symbol: str,
    # jwt: JWTPayload = Depends(depends_jwt_ws(is_authenticated=False)),
):
    """
    WebSocket endpoint for real-time market data.
    Accepts subscription requests for trades, bars, and orderbook snapshots.
    """
    await connection_manager.connect(ws)

    try:
        while True:
            data = await ws.receive_text()
            try:
                request = json.loads(data)
                request_type = request.get("type")

                if request_type == "subscribe":
                    connection_manager.subscribe(ws, request)

                    response = SubscribeResponse(
                        subscriptions=connection_manager._conn_subscriptions.get(ws, {})
                    )
                    await ws.send_text(response.model_dump_json())
                else:
                    await ws.send_text(
                        json.dumps({"type": "error", "message": "Unknown request type"})
                    )
            except json.JSONDecodeError:
                await ws.send_text(
                    json.dumps({"type": "error", "message": "Invalid JSON"})
                )
            except Exception as e:
                await ws.send_text(json.dumps({"type": "error", "message": str(e)}))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        connection_manager.disconnect(ws)
