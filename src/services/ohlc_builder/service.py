import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from config import KAFKA_ENGINE_EVENTS_TOPIC, KAFKA_INSTRUMENT_EVENTS_TOPIC
from db_models import OHLC
from engine.enums import EngineEventCategory, TimeFrame
from engine.events import BarUpdateEvent
from infra.db import get_db_sess
from infra.kafka import AsyncKafkaConsumer, AsyncKafkaProducer
from .models import Bar


class OHLCBuilder:
    def __init__(self):
        self._bars: dict[str, dict[TimeFrame, Bar]] = defaultdict(dict)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._consumer: AsyncKafkaConsumer | None = None
        self._producer: AsyncKafkaProducer | None = None
        self._logger = logging.getLogger("OHLCBuilder")
        self._sleeper_tasks: list[asyncio.Task] = []
        self._is_running = False

    async def start(self):
        self._is_running = True
        self._consumer = AsyncKafkaConsumer(
            KAFKA_ENGINE_EVENTS_TOPIC,
            group_id="ohlc_builder_consumer",
            enable_auto_commit=True,
            auto_offset_reset="latest",
        )
        self._producer = AsyncKafkaProducer()

        await self._consumer.start()
        await self._producer.start()

        for timeframe in TimeFrame:
            task = asyncio.create_task(self._sleeper_task(timeframe))
            self._sleeper_tasks.append(task)

        asyncio.create_task(self._consume_trades())
        self._logger.info("OHLCBuilder started")

    async def stop(self):
        self._is_running = False
        if self._consumer:
            await self._consumer.stop()
        if self._producer:
            await self._producer.stop()
        for task in self._sleeper_tasks:
            task.cancel()
        self._logger.info("OHLCBuilder stopped")

    async def _consume_trades(self):
        try:
            async for msg in self._consumer:
                try:
                    event = json.loads(msg.value.decode())
                    is_trade_event = False
                    for k, v in msg.headers:
                        if k == "event_category":
                            is_trade_event = v.decode() == EngineEventCategory.TRADE
                            break

                    if not is_trade_event:
                        continue
                    await self._handle_trade_event(event)
                except Exception as e:
                    self._logger.error(f"Error processing trade event: {e}")
        except Exception as e:
            self._logger.error(f"Consumer error: {e}")

    async def _handle_trade_event(self, event: dict):
        symbol = event.get("symbol")
        price = event.get("price")
        timestamp = event.get("timestamp")

        if not all([symbol, price, timestamp]):
            return

        lock = self._locks[symbol]
        async with lock:
            for timeframe in TimeFrame:
                bar_timestamp = self._get_bar_timestamp(timestamp, timeframe)

                if timeframe not in self._bars[symbol]:
                    self._bars[symbol][timeframe] = Bar(
                        open=price,
                        high=price,
                        low=price,
                        close=price,
                        timestamp=bar_timestamp,
                    )
                else:
                    current_bar = self._bars[symbol][timeframe]
                    if current_bar.timestamp != bar_timestamp:
                        self._bars[symbol][timeframe] = Bar(
                            open=price,
                            high=price,
                            low=price,
                            close=price,
                            timestamp=bar_timestamp,
                        )
                    else:
                        current_bar.update(price)

            snapshots = {
                tf: self._bars[symbol][tf].snapshot()
                for tf in TimeFrame
                if tf in self._bars[symbol]
            }

        for timeframe, snapshot in snapshots.items():
            await self._emit_bar_update(symbol, timeframe, snapshot)

    def _get_bar_timestamp(self, timestamp: float, timeframe: TimeFrame) -> int:
        seconds = timeframe.get_seconds()
        return int(timestamp // seconds * seconds)

    async def _sleeper_task(self, timeframe: TimeFrame):
        while self._is_running:
            try:
                await self._sleep_until_next_boundary(timeframe)
                await self._persist_and_emit_bars(timeframe)
            except asyncio.CancelledError:
                break
            except Exception as e:
                import traceback; traceback.print_exc()
                self._logger.error(f"Error in sleeper task for {timeframe}: {e}")

    async def _sleep_until_next_boundary(self, timeframe: TimeFrame):
        now = datetime.now(timezone.utc).timestamp()
        seconds = timeframe.get_seconds()
        next_boundary = ((int(now) // seconds) + 1) * seconds
        sleep_duration = next_boundary - now
        await asyncio.sleep(sleep_duration)

    async def _persist_and_emit_bars(self, timeframe: TimeFrame):
        snapshots: dict[str, dict] = {}

        for symbol in list(self._bars.keys()):
            lock = self._locks[symbol]
            async with lock:
                if timeframe in self._bars[symbol]:
                    bar = self._bars[symbol][timeframe]
                    snapshots[symbol] = bar.snapshot()
                    # Update timestamp to the next candle period after snapshotting
                    bar.timestamp += timeframe.get_seconds()
                    bar.open = bar.close
                    bar.close = bar.open
                    bar.high = bar.open
                    bar.low = bar.open

        if not snapshots:
            return

        async with get_db_sess() as db_sess:
            await self._batch_insert_bars(db_sess, timeframe, snapshots)

        for symbol, snapshot in snapshots.items():
            await self._emit_bar_update(symbol, timeframe, snapshot)

    async def _batch_insert_bars(
        self, db_sess: AsyncSession, timeframe: TimeFrame, snapshots: dict[str, dict]
    ):
        records = []
        for symbol, snapshot in snapshots.items():
            records.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe.value,
                    "timestamp": snapshot["timestamp"],
                    "open": snapshot["open"],
                    "high": snapshot["high"],
                    "low": snapshot["low"],
                    "close": snapshot["close"],
                }
            )

        if records:
            stmt = insert(OHLC).values(records)
            await db_sess.execute(stmt)

    async def _emit_bar_update(self, symbol: str, timeframe: TimeFrame, snapshot: dict):
        event = BarUpdateEvent(
            symbol=symbol,
            timeframe=timeframe,
            open=snapshot["open"],
            high=snapshot["high"],
            low=snapshot["low"],
            close=snapshot["close"],
            timestamp=snapshot["timestamp"],
        )

        await self._producer.send(
            KAFKA_INSTRUMENT_EVENTS_TOPIC,
            event.model_dump_json().encode()
        )
