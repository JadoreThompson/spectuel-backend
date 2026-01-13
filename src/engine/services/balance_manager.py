import logging
from typing import TYPE_CHECKING

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

from engine.config import (
    REDIS_CASH_ESCROW_HKEY_PREFIX,
    REDIS_CASH_ESCROW_PREFIX,
    REDIS_CASH_BALANCE_HKEY_PREFIX,
    REDIS_CASH_BALANCE_PREFIX,
)
from engine.decorators import ignore_system_user
from engine.events.balance import (
    BalanceEventBase,
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
from engine.infra.redis import REDIS_CLIENT, REDIS_CLIENT_SYNC
from engine.utils import get_asset_balance_key
from utils import get_default_cash_balance

if TYPE_CHECKING:
    from engine.loggers import EngineLogger


# Script for simple Increase/Decrease of any balance/escrow
# KEYS[1]: Value Key (e.g. user:123:balance)
# KEYS[2]: Log Key (e.g. user:123:balance:log)
# ARGV[1]: Event ID
# ARGV[2]: Amount Delta (Positive or Negative float)
LUA_UPDATE_BALANCE = f"""
if redis.call('HEXISTS', KEYS[2], ARGV[1]) == 1 then
    local val = redis.call('GET', KEYS[1])
    return val and tonumber(val) or 0
end

local new_val = redis.call('INCRBYFLOAT', KEYS[1], ARGV[2])
redis.call('HSET', KEYS[2], ARGV[1], ARGV[2])
return new_val
"""

# Script for Atomic Ask Settlement
# KEYS[1]: Asset Escrow Value Key
# KEYS[2]: Asset Escrow Log Key
# KEYS[3]: Asset Balance Value Key
# KEYS[4]: Asset Balance Log Key
# KEYS[5]: Cash Balance Value Key
# KEYS[6]: Cash Balance Log Key
# ARGV[1]: Quantity (Positive float)
# ARGV[2]: Price (Positive float)
# ARGV[3]: Escrow Event ID
# ARGV[4]: Asset Balance Event ID
# ARGV[5]: Cash Balance Event ID
LUA_SETTLE_ASK = """
local qty = tonumber(ARGV[1])
local price = tonumber(ARGV[2])
local cash_amt = qty * price

-- 1. Decrease Asset Escrow
if redis.call('HEXISTS', KEYS[2], ARGV[3]) == 0 then
    redis.call('INCRBYFLOAT', KEYS[1], -qty)
    redis.call('HSET', KEYS[2], ARGV[3], qty)
end

-- 2. Decrease Asset Balance
if redis.call('HEXISTS', KEYS[4], ARGV[4]) == 0 then
    redis.call('INCRBYFLOAT', KEYS[3], -qty)
    redis.call('HSET', KEYS[4], ARGV[4], qty)
end

-- 3. Increase Cash Balance
if redis.call('HEXISTS', KEYS[6], ARGV[5]) == 0 then
    redis.call('INCRBYFLOAT', KEYS[5], cash_amt)
    redis.call('HSET', KEYS[6], ARGV[5], cash_amt)
end

return 1
"""

# Script for Atomic Bid Settlement
# KEYS[1]: Cash Escrow Value Key
# KEYS[2]: Cash Escrow Log Key
# KEYS[3]: Cash Balance Value Key
# KEYS[4]: Cash Balance Log Key
# KEYS[5]: Asset Balance Value Key
# KEYS[6]: Asset Balance Log Key
# ARGV[1]: Quantity (Positive float)
# ARGV[2]: Price (Positive float)
# ARGV[3]: Escrow Event ID
# ARGV[4]: Cash Balance Event ID
# ARGV[5]: Asset Balance Event ID
LUA_SETTLE_BID = """
local qty = tonumber(ARGV[1])
local price = tonumber(ARGV[2])
local total_cash = qty * price

-- 1. Decrease Cash Escrow
if redis.call('HEXISTS', KEYS[2], ARGV[3]) == 0 then
    redis.call('INCRBYFLOAT', KEYS[1], -total_cash)
    redis.call('HSET', KEYS[2], ARGV[3], total_cash)
end

-- 2. Decrease Cash Balance
if redis.call('HEXISTS', KEYS[4], ARGV[4]) == 0 then
    redis.call('INCRBYFLOAT', KEYS[3], -total_cash)
    redis.call('HSET', KEYS[4], ARGV[4], total_cash)
end

-- 3. Increase Asset Balance
if redis.call('HEXISTS', KEYS[6], ARGV[5]) == 0 then
    redis.call('INCRBYFLOAT', KEYS[5], qty)
    redis.call('HSET', KEYS[6], ARGV[5], qty)
end

return 1
"""


class BalanceManager:
    def __init__(
        self,
        symbol: str,
        engine_logger: "EngineLogger | None" = None,
        redis_client: Redis = REDIS_CLIENT_SYNC,
        rediss_client_async: AsyncRedis = REDIS_CLIENT,
    ) -> None:
        self._symbol = symbol
        self._logger = logging.getLogger(f"{self.__class__.__name__}-{self._symbol}")
        self.engine_logger = engine_logger
        if engine_logger is None:
            self._logger.warning("BalanceManager initialised with no EngineLogger")

        self._redis_client = redis_client
        self._redis_async_client = rediss_client_async

        self._script_update_balance = self._redis_client.register_script(
            LUA_UPDATE_BALANCE
        )
        self._script_settle_ask = self._redis_client.register_script(LUA_SETTLE_ASK)
        self._script_settle_bid = self._redis_client.register_script(LUA_SETTLE_BID)

        self._script_update_balance_async = self._redis_async_client.register_script(
            LUA_UPDATE_BALANCE
        )
        self._script_settle_ask_async = self._redis_async_client.register_script(
            LUA_SETTLE_ASK
        )
        self._script_settle_bid_async = self._redis_async_client.register_script(
            LUA_SETTLE_BID
        )

    def _wal(self, user_id: str, event: BalanceEventBase) -> None:
        self.engine_logger.log_balance_event(user_id, event, {"key": self._symbol})

    def get_asset_balance_hkey(self, user_id: str) -> str:
        return f"{self._symbol}:{user_id}:balance:log"

    def get_asset_escrow_hkey(self, user_id: str) -> str:
        return f"{self._symbol}:{user_id}:escrow:log"

    def get_asset_escrow_key(self, user_id: str) -> str:
        return f"{self._symbol}:{user_id}:escrow"

    @staticmethod
    def get_cash_balance_key(user_id: str) -> str:
        return f"{REDIS_CASH_BALANCE_PREFIX}{user_id}"

    @staticmethod
    def get_cash_balance_hkey(user_id: str) -> str:
        return f"{REDIS_CASH_BALANCE_HKEY_PREFIX}{user_id}"

    @staticmethod
    def get_cash_escrow_key(user_id: str) -> str:
        return f"{REDIS_CASH_ESCROW_PREFIX}{user_id}"

    @staticmethod
    def get_cash_escrow_hkey(user_id: str) -> str:
        return f"{REDIS_CASH_ESCROW_HKEY_PREFIX}{user_id}"

    def get_cash_balance(self, user_id: str) -> float:
        key = self.get_cash_balance_key(user_id)
        balance = self._redis_client.get(key)
        if balance is None:
            balance = get_default_cash_balance()
            self._redis_client.set(key, str(balance))
            return balance
        return float(balance)

    def get_cash_escrow(self, user_id: str) -> float:
        key = self.get_cash_escrow_key(user_id)
        escrow = self._redis_client.get(key)
        if escrow is None:
            self._redis_client.set(key, "0")
            return 0.0
        return float(escrow)

    def get_available_cash_balance(self, user_id: str) -> float:
        balance = self.get_cash_balance(user_id)
        escrow = self.get_cash_escrow(user_id)

        return float(balance) - float(escrow)

    def get_available_asset_balance(self, user_id: str) -> float:
        bal_key = get_asset_balance_key(self._symbol, user_id)
        esc_key = self.get_asset_escrow_key(user_id)

        balance = self._redis_client.get(bal_key)
        escrow = self._redis_client.get(esc_key)

        if balance is None:
            self._redis_client.set(bal_key, "0")
            balance = "0"

        if escrow is None:
            self._redis_client.set(esc_key, "0")
            escrow = "0"

        return float(balance) - float(escrow)

    @ignore_system_user
    def increase_cash_balance(
        self,
        user_id: str,
        amount: float,
        command_id: str,
    ) -> float:
        event = CashBalanceIncreasedEvent(
            user_id=user_id, amount=amount, command_id=command_id
        )
        self._wal(user_id, event)

        val_key = self.get_cash_balance_key(user_id)
        log_key = self.get_cash_balance_hkey(user_id)

        return float(
            self._script_update_balance(
                keys=[val_key, log_key], args=[str(event.id), amount]
            )
        )

    @ignore_system_user
    def decrease_cash_balance(
        self,
        user_id: str,
        amount: float,
        command_id: str,
    ) -> float:
        event = CashBalanceDecreasedEvent(
            user_id=user_id, amount=amount, command_id=command_id
        )
        self._wal(user_id, event)

        val_key = self.get_cash_balance_key(user_id)
        log_key = self.get_cash_balance_hkey(user_id)

        return float(
            self._script_update_balance(
                keys=[val_key, log_key], args=[str(event.id), -amount]
            )
        )

    @ignore_system_user
    def increase_cash_escrow(
        self,
        user_id: str,
        amount: float,
        command_id: str,
    ) -> float:
        event = CashEscrowIncreasedEvent(
            user_id=user_id, amount=amount, command_id=command_id
        )
        self._wal(user_id, event)

        val_key = self.get_cash_escrow_key(user_id)
        log_key = self.get_cash_escrow_hkey(user_id)

        return float(
            self._script_update_balance(
                keys=[val_key, log_key], args=[str(event.id), amount]
            )
        )
    


    @ignore_system_user
    def decrease_cash_escrow(
        self,
        user_id: str,
        amount: float,
        command_id: str,
    ) -> float:
        event =  CashEscrowDecreasedEvent(
            user_id=user_id, amount=amount, command_id=command_id
        )
        self._wal(user_id, event)

        val_key = self.get_cash_escrow_key(user_id)
        log_key = self.get_cash_escrow_hkey(user_id)

        return float(
            self._script_update_balance(
                keys=[val_key, log_key], args=[str(event.id), -amount]
            )
        )

    @ignore_system_user
    def increase_asset_balance(
        self,
        user_id: str,
        amount: float,
        command_id: str,
    ) -> float:
        event = AssetBalanceIncreasedEvent(
            user_id=user_id, symbol=self._symbol, amount=amount, command_id=command_id
        )
        self._wal(user_id, event)

        val_key = get_asset_balance_key(self._symbol, user_id)
        log_key = self.get_asset_balance_hkey(user_id)

        return float(
            self._script_update_balance(
                keys=[val_key, log_key], args=[str(event.id), amount]
            )
        )

    @ignore_system_user
    def decrease_asset_balance(
        self,
        user_id: str,
        amount: float,
        command_id: str,
    ) -> float:
        event =  AssetBalanceDecreasedEvent(
            user_id=user_id, symbol=self._symbol, amount=amount, command_id=command_id
        )
        self._wal(user_id, event)

        val_key = get_asset_balance_key(self._symbol, user_id)
        log_key = self.get_asset_balance_hkey(user_id)

        return float(
            self._script_update_balance(
                keys=[val_key, log_key], args=[str(event.id), -amount]
            )
        )

    @ignore_system_user
    def increase_asset_escrow(
        self,
        user_id: str,
        amount: float,
        command_id: str,
    ) -> float:
        event = AssetEscrowIncreasedEvent(
            user_id=user_id, symbol=self._symbol, amount=amount, command_id=command_id
        )
        self._wal(user_id, event)

        val_key = self.get_asset_escrow_key(user_id)
        log_key = self.get_asset_escrow_hkey(user_id)

        return float(
            self._script_update_balance(
                keys=[val_key, log_key], args=[str(event.id), amount]
            )
        )

    @ignore_system_user
    def decrease_asset_escrow(
        self,
        user_id: str,
        amount: float,
        command_id: str,
    ) -> float:
        event = AssetEscrowDecreasedEvent(
            user_id=user_id, symbol=self._symbol, amount=amount, command_id=command_id
        )
        self._wal(user_id, event)

        val_key = self.get_asset_escrow_key(user_id)
        log_key = self.get_asset_escrow_hkey(user_id)

        return float(
            self._script_update_balance(
                keys=[val_key, log_key], args=[str(event.id), -amount]
            )
        )

    @ignore_system_user
    def settle_ask(
        self,
        user_id: str,
        quantity: float,
        price: float,
        command_id: str,
        trade_event_id: str,
    ) -> None:
        event = AskSettledEvent(
            user_id=user_id,
            symbol=self._symbol,
            quantity=quantity,
            price=price,
            asset_balance_decreased=AssetBalanceDecreasedEvent(
                user_id=user_id,
                symbol=self._symbol,
                amount=quantity,
                command_id=command_id,
            ),
            asset_escrow_decreased=AssetEscrowDecreasedEvent(
                user_id=user_id,
                symbol=self._symbol,
                amount=quantity,
                command_id=command_id,
            ),
            cash_balance_increased=CashBalanceIncreasedEvent(
                user_id=user_id, amount=quantity * price, command_id=command_id
            ),
            command_id=command_id,
            trade_event_id=trade_event_id,
        )

        self._wal(user_id, event)

        # Keys for Lua
        keys = [
            self.get_asset_escrow_key(user_id),  # KEYS[1]
            self.get_asset_escrow_hkey(user_id),  # KEYS[2]
            get_asset_balance_key(self._symbol, user_id),  # KEYS[3]
            self.get_asset_balance_hkey(user_id),  # KEYS[4]
            self.get_cash_balance_key(user_id),  # KEYS[5]
            self.get_cash_balance_hkey(user_id),  # KEYS[6]
        ]

        # Args for Lua
        args = [
            quantity,  # ARGV[1]
            price,  # ARGV[2]
            str(event.asset_escrow_decreased.id),  # ARGV[3]
            str(event.asset_balance_decreased.id),  # ARGV[4]
            str(event.cash_balance_increased.id),  # ARGV[5]
        ]

        self._script_settle_ask(keys=keys, args=args)

    @ignore_system_user
    def settle_bid(
        self,
        user_id: str,
        quantity: float,
        price: float,
        command_id: str,
        trade_event_id: str,
    ) -> None:
        total = quantity * price

        event = BidSettledEvent(
            user_id=user_id,
            symbol=self._symbol,
            quantity=quantity,
            price=price,
            cash_escrow_decreased=CashEscrowDecreasedEvent(
                user_id=user_id, amount=total, command_id=command_id
            ),
            cash_balance_decreased=CashBalanceDecreasedEvent(
                user_id=user_id, amount=total, command_id=command_id
            ),
            asset_balance_increased=AssetBalanceIncreasedEvent(
                user_id=user_id,
                symbol=self._symbol,
                amount=quantity,
                command_id=command_id,
            ),
            command_id=command_id,
            trade_event_id=trade_event_id,
        )

        self._wal(user_id, event)

        # Keys for Lua
        keys = [
            self.get_cash_escrow_key(user_id),  # KEYS[1]
            self.get_cash_escrow_hkey(user_id),  # KEYS[2]
            self.get_cash_balance_key(user_id),  # KEYS[3]
            self.get_cash_balance_hkey(user_id),  # KEYS[4]
            get_asset_balance_key(self._symbol, user_id),  # KEYS[5]
            self.get_asset_balance_hkey(user_id),  # KEYS[6]
        ]

        # Args for Lua
        args = [
            quantity,  # ARGV[1]
            price,  # ARGV[2]
            str(event.cash_escrow_decreased.id),  # ARGV[3]
            str(event.cash_balance_decreased.id),  # ARGV[4]
            str(event.asset_balance_increased.id),  # ARGV[5]
        ]

        self._script_settle_bid(keys=keys, args=args)

    async def increase_cash_balance_async(
        self,
        user_id: str,
        amount: float,
        command_id: str,
    ) -> float:
        event = CashBalanceIncreasedEvent(
            user_id=user_id, amount=amount, command_id=command_id
        )
        self._wal(user_id, event)

        val_key = self.get_cash_balance_key(user_id)
        log_key = self.get_cash_balance_hkey(user_id)

        return float(
            await self._script_update_balance_async(
                keys=[val_key, log_key], args=[str(event.id), amount]
            )
        )
