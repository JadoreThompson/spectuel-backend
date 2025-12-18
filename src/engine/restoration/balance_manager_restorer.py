import logging
from datetime import datetime, timedelta
from typing import Generator

from sqlalchemy import select

from db_models import EventLogs
from engine.events.enums import BalanceEventType
from engine.events.balance import (
    CashBalanceIncreasedEvent,
    CashBalanceDecreasedEvent,
    CashEscrowIncreasedEvent,
    CashEscrowDecreasedEvent,
    AssetBalanceIncreasedEvent,
    AssetBalanceDecreasedEvent,
    AssetEscrowIncreasedEvent,
    AssetEscrowDecreasedEvent,
    AskSettledEvent,
    BidSettledEvent,
)
from engine.infra.redis import REDIS_CLIENT_SYNC, BACKUP_REDIS_CLIENT_SYNC
from engine.loggers import WALogger
from engine.restoration.restoration_manager import RestorationManager
from engine.services.balance_manager import BalanceManager
from infra.db import get_db_sess


class BalanceManagerRestorer:
    """
    Restores the state of Redis in the event of a Redis failure.
    """

    def __init__(self) -> None:
        self._name = self.__class__.__name__
        self._bm = BalanceManager(WALogger(self._name), BACKUP_REDIS_CLIENT_SYNC)
        self._logger = logging.getLogger(self._name)

    def _get_all_redis_keys(self) -> list[str]:
        """Get all keys from the main Redis instance."""
        return REDIS_CLIENT_SYNC.keys("*")

    def _restore_to_backup_redis(self, keys: list[str]) -> bool:
        """Restore keys from main Redis to backup Redis."""
        BACKUP_REDIS_CLIENT_SYNC.flushdb()

        restored_count = 0

        for key in keys:
            key_type = REDIS_CLIENT_SYNC.type(key).decode()

            if key_type == "string":
                value = REDIS_CLIENT_SYNC.get(key)
                BACKUP_REDIS_CLIENT_SYNC.set(key, value)

            elif key_type == "hash":
                hash_data = REDIS_CLIENT_SYNC.hgetall(key)
                if hash_data:
                    BACKUP_REDIS_CLIENT_SYNC.hset(key, mapping=hash_data)
            else:
                raise NotImplementedError(
                    f"Restoration for keytype '{key_type}' hasn't been implemeted."
                )

            restored_count += 1

        self._logger.info(
            f"Successfully restored {restored_count} keys to backup Redis"
        )
        return True

    def _yield_logs(
        self, start_epoch: int, batch_size: int = 1000
    ) -> Generator[EventLogs, None, None]:
        with get_db_sess() as db_sess:
            res = db_sess.execute(
                select(EventLogs).where(EventLogs.timestamp >= start_epoch)
            )

            for row in res.yield_per(batch_size):
                for r in row:
                    yield r

    def _replay_logs(self, start_epoch: int) -> bool:
        """
        Replay all balance-related logs from the database starting from start_epoch.
        """
        for log in self._yield_logs(start_epoch):
            event_type = log.data.get("type")
            data = log.data

            try:
                # Cash Balance Events
                if event_type == BalanceEventType.CASH_BALANCE_INCREASED:
                    event = CashBalanceIncreasedEvent(**data)
                    self._bm.increase_cash_balance(
                        user_id=event.user_id, amount=event.amount, event=event
                    )
                elif event_type == BalanceEventType.CASH_BALANCE_DECREASED:
                    event = CashBalanceDecreasedEvent(**data)
                    self._bm.decrease_cash_balance(
                        user_id=event.user_id, amount=event.amount, event=event
                    )

                # Cash Escrow Events
                elif event_type == BalanceEventType.CASH_ESCROW_INCREASED:
                    event = CashEscrowIncreasedEvent(**data)
                    self._bm.increase_cash_escrow(
                        user_id=event.user_id, amount=event.amount, event=event
                    )
                elif event_type == BalanceEventType.CASH_ESCROW_DECREASED:
                    event = CashEscrowDecreasedEvent(**data)
                    self._bm.decrease_cash_escrow(
                        user_id=event.user_id, amount=event.amount, event=event
                    )

                # Asset Balance Events
                elif event_type == BalanceEventType.ASSET_BALANCE_INCREASED:
                    event = AssetBalanceIncreasedEvent(**data)
                    self._bm.increase_asset_balance(
                        user_id=event.user_id,
                        symbol=event.symbol,
                        amount=event.amount,
                        event=event,
                    )
                elif event_type == BalanceEventType.ASSET_BALANCE_DECREASED:
                    event = AssetBalanceDecreasedEvent(**data)
                    self._bm.decrease_asset_balance(
                        user_id=event.user_id,
                        symbol=event.symbol,
                        amount=event.amount,
                        event=event,
                    )

                # Asset Escrow Events
                elif event_type == BalanceEventType.ASSET_ESCROW_INCREASED:
                    event = AssetEscrowIncreasedEvent(**data)
                    self._bm.increase_asset_escrow(
                        user_id=event.user_id,
                        symbol=event.symbol,
                        amount=event.amount,
                        event=event,
                    )
                elif event_type == BalanceEventType.ASSET_ESCROW_DECREASED:
                    event = AssetEscrowDecreasedEvent(**data)
                    self._bm.decrease_asset_escrow(
                        user_id=event.user_id,
                        symbol=event.symbol,
                        amount=event.amount,
                        event=event,
                    )

                # Settlement Events
                elif event_type == BalanceEventType.ASK_SETTLED:
                    event = AskSettledEvent(**data)
                    self._bm.settle_ask(
                        user_id=event.user_id,
                        symbol=event.symbol,
                        quantity=event.quantity,
                        price=event.price,
                        event=event,
                    )
                elif event_type == BalanceEventType.BID_SETTLED:
                    event = BidSettledEvent(**data)
                    self._bm.settle_bid(
                        user_id=event.user_id,
                        symbol=event.symbol,
                        quantity=event.quantity,
                        price=event.price,
                        event=event,
                    )

                else:
                    continue

            except Exception as e:
                self._logger.error(
                    f"Failed to replay event {log.event_id} ({event_type}): {e}"
                )

        self._logger.info("Finished replaying all balance logs")
        return True

    def restore_balance_manager(self) -> bool:
        """
        Fetch the latest snapshot from Redis and load it into the backup Redis server.

        Returns:
            bool: True if restoration was successful, False otherwise
        """
        try:
            RestorationManager.set_predicate(self._name, lambda: True)

            try:
                last_save: datetime = REDIS_CLIENT_SYNC.lastsave()
            except Exception as e:
                self._logger.warning(
                    f"Could not get lastsave from Main Redis: {e}. Defaulting to 1 day ago."
                )
                last_save = datetime.now() - timedelta(days=1)

            self._logger.info(f"Main Redis last save: {last_save}")

            keys = self._get_all_redis_keys()
            if not keys:
                self._logger.info("No keys found in main Redis")
                # Even if main redis is empty, we might have logs to replay if it crashed and lost data
            else:
                self._logger.info(f"Found {len(keys)} keys in main Redis")
                self._restore_to_backup_redis(keys)

            # Replay logs from slightly before the snapshot to ensure continuity
            self._replay_logs((last_save - timedelta(minutes=5)).timestamp())

            backup_keys_count = BACKUP_REDIS_CLIENT_SYNC.dbsize()
            self._logger.info(f"Backup Redis now contains {backup_keys_count} keys")

            return True
        finally:
            RestorationManager.remove(self._name)
