import logging
from typing import TYPE_CHECKING

from redis import Redis
from redis.asyncio import Redis as AsyncRedis  # Added import

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
from utils import get_default_cash_balance

if TYPE_CHECKING:
    from engine.loggers import WALogger


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
        wal_logger: "WALogger | None" = None,
        redis_client: Redis = REDIS_CLIENT_SYNC,
        rediss_client_async: AsyncRedis = REDIS_CLIENT,
    ) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)
        self._wal_logger = wal_logger
        if wal_logger is None:
            self._logger.warning("BalanceManager initialised with no WALogger")

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
        self._wal_logger.log_balance_event(user_id, event)

    @staticmethod
    def get_asset_balance_hkey(symbol: str, user_id: str) -> str:
        return f"{symbol}:{user_id}:balance:log"

    @staticmethod
    def get_asset_balance_key(symbol: str, user_id: str) -> str:
        return f"{symbol}:{user_id}:balance"

    @staticmethod
    def get_asset_escrow_hkey(symbol: str, user_id: str) -> str:
        return f"{symbol}:{user_id}:escrow:log"

    @staticmethod
    def get_asset_escrow_key(symbol: str, user_id: str) -> str:
        return f"{symbol}:{user_id}:escrow"

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
        # bal_key = self.get_cash_balance_key(user_id)
        # esc_key = self.get_cash_escrow_key(user_id)

        # balance = self._redis_client.get(bal_key)
        # escrow = self._redis_client.get(esc_key)
        # if balance is None:
        #     balance = get_default_cash_balance()
        #     self._redis_client.set(bal_key, str(balance))

        # if escrow is None:
        #     self._redis_client.set(esc_key, "0")
        #     escrow = "0"
        balance = self.get_cash_balance(user_id)
        escrow = self.get_cash_escrow(user_id)

        return float(balance) - float(escrow)

    def get_available_asset_balance(self, user_id: str, symbol: str) -> float:
        bal_key = self.get_asset_balance_key(symbol, user_id)
        esc_key = self.get_asset_escrow_key(symbol, user_id)

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
        event: CashBalanceIncreasedEvent | None = None,
    ) -> float:
        event = event or CashBalanceIncreasedEvent(user_id=user_id, amount=amount)
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
        event: CashBalanceDecreasedEvent | None = None,
    ) -> float:
        event = event or CashBalanceDecreasedEvent(user_id=user_id, amount=amount)
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
        self, user_id: str, amount: float, event: CashEscrowIncreasedEvent | None = None
    ) -> float:
        event = event or CashEscrowIncreasedEvent(user_id=user_id, amount=amount)
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
        self, user_id: str, amount: float, event: CashEscrowDecreasedEvent | None = None
    ) -> float:
        event = event or CashEscrowDecreasedEvent(user_id=user_id, amount=amount)
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
        symbol: str,
        amount: float,
        event: AssetBalanceIncreasedEvent | None = None,
    ) -> float:
        event = event or AssetBalanceIncreasedEvent(
            user_id=user_id, symbol=symbol, amount=amount
        )
        self._wal(user_id, event)

        val_key = self.get_asset_balance_key(symbol, user_id)
        log_key = self.get_asset_balance_hkey(symbol, user_id)

        return float(
            self._script_update_balance(
                keys=[val_key, log_key], args=[str(event.id), amount]
            )
        )

    @ignore_system_user
    def decrease_asset_balance(
        self,
        user_id: str,
        symbol: str,
        amount: float,
        event: AssetBalanceDecreasedEvent | None = None,
    ) -> float:
        event = event or AssetBalanceDecreasedEvent(
            user_id=user_id, symbol=symbol, amount=amount
        )
        self._wal(user_id, event)

        val_key = self.get_asset_balance_key(symbol, user_id)
        log_key = self.get_asset_balance_hkey(symbol, user_id)

        return float(
            self._script_update_balance(
                keys=[val_key, log_key], args=[str(event.id), -amount]
            )
        )

    @ignore_system_user
    def increase_asset_escrow(
        self,
        user_id: str,
        symbol: str,
        amount: float,
        event: AssetEscrowIncreasedEvent | None = None,
    ) -> float:
        event = event or AssetEscrowIncreasedEvent(
            user_id=user_id, symbol=symbol, amount=amount
        )
        self._wal(user_id, event)

        val_key = self.get_asset_escrow_key(symbol, user_id)
        log_key = self.get_asset_escrow_hkey(symbol, user_id)

        return float(
            self._script_update_balance(
                keys=[val_key, log_key], args=[str(event.id), amount]
            )
        )

    @ignore_system_user
    def decrease_asset_escrow(
        self,
        user_id: str,
        symbol: str,
        amount: float,
        event: AssetEscrowDecreasedEvent | None = None,
    ) -> float:
        event = event or AssetEscrowDecreasedEvent(
            user_id=user_id, symbol=symbol, amount=amount
        )
        self._wal(user_id, event)

        val_key = self.get_asset_escrow_key(symbol, user_id)
        log_key = self.get_asset_escrow_hkey(symbol, user_id)

        return float(
            self._script_update_balance(
                keys=[val_key, log_key], args=[str(event.id), -amount]
            )
        )

    @ignore_system_user
    def settle_ask(
        self,
        user_id: str,
        symbol: str,
        quantity: float,
        price: float,
        event: AskSettledEvent | None = None,
    ) -> None:
        event = event or AskSettledEvent(
            user_id=user_id,
            symbol=symbol,
            quantity=quantity,
            price=price,
            asset_balance_decreased=AssetBalanceDecreasedEvent(
                user_id=user_id, symbol=symbol, amount=quantity
            ),
            asset_escrow_decreased=AssetEscrowDecreasedEvent(
                user_id=user_id, symbol=symbol, amount=quantity
            ),
            cash_balance_increased=CashBalanceIncreasedEvent(
                user_id=user_id, amount=quantity * price
            ),
        )

        self._wal(user_id, event)

        # Keys for Lua
        keys = [
            self.get_asset_escrow_key(symbol, user_id),  # KEYS[1]
            self.get_asset_escrow_hkey(symbol, user_id),  # KEYS[2]
            self.get_asset_balance_key(symbol, user_id),  # KEYS[3]
            self.get_asset_balance_hkey(symbol, user_id),  # KEYS[4]
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
        symbol: str,
        quantity: float,
        price: float,
        event: BidSettledEvent | None = None,
    ) -> None:
        total = quantity * price

        event = event or BidSettledEvent(
            user_id=user_id,
            symbol=symbol,
            quantity=quantity,
            price=price,
            cash_escrow_decreased=CashEscrowDecreasedEvent(
                user_id=user_id, amount=total
            ),
            cash_balance_decreased=CashBalanceDecreasedEvent(
                user_id=user_id, amount=total
            ),
            asset_balance_increased=AssetBalanceIncreasedEvent(
                user_id=user_id, symbol=symbol, amount=quantity
            ),
        )

        self._wal(user_id, event)

        # Keys for Lua
        keys = [
            self.get_cash_escrow_key(user_id),  # KEYS[1]
            self.get_cash_escrow_hkey(user_id),  # KEYS[2]
            self.get_cash_balance_key(user_id),  # KEYS[3]
            self.get_cash_balance_hkey(user_id),  # KEYS[4]
            self.get_asset_balance_key(symbol, user_id),  # KEYS[5]
            self.get_asset_balance_hkey(symbol, user_id),  # KEYS[6]
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

    async def get_cash_balance_async(self, user_id: str) -> float:
        key = self.get_cash_balance_key(user_id)
        balance = await self._redis_async_client.get(key)
        if balance is None:
            await self._redis_async_client.set(key, "0")
            return 0.0
        return float(balance)

    async def get_cash_escrow_async(self, user_id: str) -> float:
        key = self.get_cash_escrow_key(user_id)
        escrow = await self._redis_async_client.get(key)
        if escrow is None:
            await self._redis_async_client.set(key, "0")
            return 0.0
        return float(escrow)

    async def get_available_cash_balance_async(self, user_id: str) -> float:
        bal_key = self.get_cash_balance_key(user_id)
        esc_key = self.get_cash_escrow_key(user_id)

        balance = await self._redis_async_client.get(bal_key)
        escrow = await self._redis_async_client.get(esc_key)

        if balance is None:
            await self._redis_async_client.set(bal_key, "0")
            balance = "0"

        if escrow is None:
            await self._redis_async_client.set(esc_key, "0")
            escrow = "0"

        return float(balance) - float(escrow)

    async def get_available_asset_balance_async(
        self, user_id: str, symbol: str
    ) -> float:
        bal_key = self.get_asset_balance_key(symbol, user_id)
        esc_key = self.get_asset_escrow_key(symbol, user_id)

        balance = await self._redis_async_client.get(bal_key)
        escrow = await self._redis_async_client.get(esc_key)

        if balance is None:
            await self._redis_async_client.set(bal_key, "0")
            balance = "0"

        if escrow is None:
            await self._redis_async_client.set(esc_key, "0")
            escrow = "0"

        return float(balance) - float(escrow)

    async def increase_cash_balance_async(
        self,
        user_id: str,
        amount: float,
        event: CashBalanceIncreasedEvent | None = None,
    ) -> float:
        event = event or CashBalanceIncreasedEvent(user_id=user_id, amount=amount)
        self._wal(user_id, event)

        val_key = self.get_cash_balance_key(user_id)
        log_key = self.get_cash_balance_hkey(user_id)

        return float(
            await self._script_update_balance_async(
                keys=[val_key, log_key], args=[str(event.id), amount]
            )
        )

    async def decrease_cash_balance_async(
        self,
        user_id: str,
        amount: float,
        event: CashBalanceDecreasedEvent | None = None,
    ) -> float:
        event = event or CashBalanceDecreasedEvent(user_id=user_id, amount=amount)
        self._wal(user_id, event)

        val_key = self.get_cash_balance_key(user_id)
        log_key = self.get_cash_balance_hkey(user_id)

        return float(
            await self._script_update_balance_async(
                keys=[val_key, log_key], args=[str(event.id), -amount]
            )
        )

    async def increase_cash_escrow_async(
        self, user_id: str, amount: float, event: CashEscrowIncreasedEvent | None = None
    ) -> float:
        event = event or CashEscrowIncreasedEvent(user_id=user_id, amount=amount)
        self._wal(user_id, event)

        val_key = self.get_cash_escrow_key(user_id)
        log_key = self.get_cash_escrow_hkey(user_id)

        return float(
            await self._script_update_balance_async(
                keys=[val_key, log_key], args=[str(event.id), amount]
            )
        )

    async def decrease_cash_escrow_async(
        self, user_id: str, amount: float, event: CashEscrowDecreasedEvent | None = None
    ) -> float:
        event = event or CashEscrowDecreasedEvent(user_id=user_id, amount=amount)
        self._wal(user_id, event)

        val_key = self.get_cash_escrow_key(user_id)
        log_key = self.get_cash_escrow_hkey(user_id)

        return float(
            await self._script_update_balance_async(
                keys=[val_key, log_key], args=[str(event.id), -amount]
            )
        )

    async def increase_asset_balance_async(
        self,
        user_id: str,
        symbol: str,
        amount: float,
        event: AssetBalanceIncreasedEvent | None = None,
    ) -> float:
        event = event or AssetBalanceIncreasedEvent(
            user_id=user_id, symbol=symbol, amount=amount
        )
        self._wal(user_id, event)

        val_key = self.get_asset_balance_key(symbol, user_id)
        log_key = self.get_asset_balance_hkey(symbol, user_id)

        return float(
            await self._script_update_balance_async(
                keys=[val_key, log_key], args=[str(event.id), amount]
            )
        )

    async def decrease_asset_balance_async(
        self,
        user_id: str,
        symbol: str,
        amount: float,
        event: AssetBalanceDecreasedEvent | None = None,
    ) -> float:
        event = event or AssetBalanceDecreasedEvent(
            user_id=user_id, symbol=symbol, amount=amount
        )
        self._wal(user_id, event)

        val_key = self.get_asset_balance_key(symbol, user_id)
        log_key = self.get_asset_balance_hkey(symbol, user_id)

        return float(
            await self._script_update_balance_async(
                keys=[val_key, log_key], args=[str(event.id), -amount]
            )
        )

    async def increase_asset_escrow_async(
        self,
        user_id: str,
        symbol: str,
        amount: float,
        event: AssetEscrowIncreasedEvent | None = None,
    ) -> float:
        event = event or AssetEscrowIncreasedEvent(
            user_id=user_id, symbol=symbol, amount=amount
        )
        self._wal(user_id, event)

        val_key = self.get_asset_escrow_key(symbol, user_id)
        log_key = self.get_asset_escrow_hkey(symbol, user_id)

        return float(
            await self._script_update_balance_async(
                keys=[val_key, log_key], args=[str(event.id), amount]
            )
        )

    async def decrease_asset_escrow_async(
        self,
        user_id: str,
        symbol: str,
        amount: float,
        event: AssetEscrowDecreasedEvent | None = None,
    ) -> float:
        event = event or AssetEscrowDecreasedEvent(
            user_id=user_id, symbol=symbol, amount=amount
        )
        self._wal(user_id, event)

        val_key = self.get_asset_escrow_key(symbol, user_id)
        log_key = self.get_asset_escrow_hkey(symbol, user_id)

        return float(
            await self._script_update_balance_async(
                keys=[val_key, log_key], args=[str(event.id), -amount]
            )
        )

    async def settle_ask_async(
        self,
        user_id: str,
        symbol: str,
        quantity: float,
        price: float,
        event: AskSettledEvent | None = None,
    ) -> None:
        event = event or AskSettledEvent(
            user_id=user_id,
            symbol=symbol,
            quantity=quantity,
            price=price,
            asset_balance_decreased=AssetBalanceDecreasedEvent(
                user_id=user_id, symbol=symbol, amount=quantity
            ),
            asset_escrow_decreased=AssetEscrowDecreasedEvent(
                user_id=user_id, symbol=symbol, amount=quantity
            ),
            cash_balance_increased=CashBalanceIncreasedEvent(
                user_id=user_id, amount=quantity * price
            ),
        )

        self._wal(user_id, event)

        # Keys for Lua
        keys = [
            self.get_asset_escrow_key(symbol, user_id),  # KEYS[1]
            self.get_asset_escrow_hkey(symbol, user_id),  # KEYS[2]
            self.get_asset_balance_key(symbol, user_id),  # KEYS[3]
            self.get_asset_balance_hkey(symbol, user_id),  # KEYS[4]
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

        await self._script_settle_ask_async(keys=keys, args=args)

    async def settle_bid_async(
        self,
        user_id: str,
        symbol: str,
        quantity: float,
        price: float,
        event: BidSettledEvent | None = None,
    ) -> None:
        total = quantity * price

        event = event or BidSettledEvent(
            user_id=user_id,
            symbol=symbol,
            quantity=quantity,
            price=price,
            cash_escrow_decreased=CashEscrowDecreasedEvent(
                user_id=user_id, amount=total
            ),
            cash_balance_decreased=CashBalanceDecreasedEvent(
                user_id=user_id, amount=total
            ),
            asset_balance_increased=AssetBalanceIncreasedEvent(
                user_id=user_id, symbol=symbol, amount=quantity
            ),
        )

        self._wal(user_id, event)

        # Keys for Lua
        keys = [
            self.get_cash_escrow_key(user_id),  # KEYS[1]
            self.get_cash_escrow_hkey(user_id),  # KEYS[2]
            self.get_cash_balance_key(user_id),  # KEYS[3]
            self.get_cash_balance_hkey(user_id),  # KEYS[4]
            self.get_asset_balance_key(symbol, user_id),  # KEYS[5]
            self.get_asset_balance_hkey(symbol, user_id),  # KEYS[6]
        ]

        # Args for Lua
        args = [
            quantity,  # ARGV[1]
            price,  # ARGV[2]
            str(event.cash_escrow_decreased.id),  # ARGV[3]
            str(event.cash_balance_decreased.id),  # ARGV[4]
            str(event.asset_balance_increased.id),  # ARGV[5]
        ]

        await self._script_settle_bid_async(keys=keys, args=args)
