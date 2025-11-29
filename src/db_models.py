from datetime import datetime
from uuid import UUID, uuid4

from spectuel_engine_utils.enums import (
    OrderType,
    InstrumentStatus,
    OrderStatus,
    Side,
    LiquidityRole,
)
from sqlalchemy import (
    UUID as SaUUID,
    Integer,
    Float,
    ForeignKey,
    String,
    DateTime,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from core.enums import OrderGroupType
from utils.utils import get_datetime, get_default_cash_balance


class Base(DeclarativeBase):
    pass


class Users(Base):
    __tablename__ = "users"

    user_id: Mapped[UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String, nullable=False)
    cash_balance: Mapped[float] = mapped_column(
        Float, nullable=False, default=get_default_cash_balance
    )
    escrow_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.00)
    api_key: Mapped[str] = mapped_column(String, nullable=True)
    jwt: Mapped[str] = mapped_column(String, nullable=True)
    authenticated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=get_datetime
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=get_datetime,
        onupdate=get_datetime,
    )

    # Relationships
    orders = relationship("Orders", back_populates="user", cascade="all, delete-orphan")
    trades = relationship("Trades", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship(
        "Transactions", back_populates="user", cascade="all, delete-orphan"
    )
    asset_balances = relationship(
        "AssetBalances", back_populates="user", cascade="all, delete-orphan"
    )


class Instruments(Base):
    __tablename__ = "instruments"

    instrument_id: Mapped[UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    symbol: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    starting_price: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=InstrumentStatus.DOWN
    )

    # Relationships
    orders = relationship(
        "Orders", back_populates="instrument", cascade="all, delete-orphan"
    )
    trades = relationship(
        "Trades", back_populates="instrument", cascade="all, delete-orphan"
    )
    asset_balances = relationship(
        "AssetBalances", back_populates="instrument", cascade="all, delete-orphan"
    )


class Orders(Base):
    __tablename__ = "orders"

    order_id: Mapped[UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        SaUUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    order_group_id: Mapped[UUID] = mapped_column(
        SaUUID(as_uuid=True), nullable=True, index=True
    )
    parent_order_id: Mapped[UUID | None] = mapped_column(
        SaUUID(as_uuid=True), ForeignKey("orders.order_id"), nullable=True
    )
    instrument_id: Mapped[UUID] = mapped_column(
        SaUUID(as_uuid=True), ForeignKey("instruments.instrument_id"), nullable=False
    )
    side: Mapped[Side] = mapped_column(String, nullable=False)
    order_type: Mapped[OrderType] = mapped_column(String, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    executed_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_fill_price: Mapped[float] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=OrderStatus.PENDING.value
    )
    group_type: Mapped[OrderGroupType | None] = mapped_column(
        String, nullable=True
    )  # core.enums.OrderGroupType
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=get_datetime
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=get_datetime,
        onupdate=get_datetime,
    )

    # Relationships
    user = relationship("Users", back_populates="orders")
    instrument = relationship("Instruments", back_populates="orders")
    trades = relationship(
        "Trades", back_populates="order", cascade="all, delete-orphan"
    )


class Trades(Base):
    __tablename__ = "trades"

    trade_id: Mapped[UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    order_id: Mapped[UUID] = mapped_column(
        SaUUID(as_uuid=True), ForeignKey("orders.order_id"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        SaUUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    instrument_id: Mapped[UUID] = mapped_column(
        SaUUID(as_uuid=True), ForeignKey("instruments.instrument_id"), nullable=False
    )
    price: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    role: Mapped[LiquidityRole] = mapped_column(String, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=get_datetime
    )

    # Relationships
    order = relationship("Orders", back_populates="trades")
    user = relationship("Users", back_populates="trades")
    instrument = relationship("Instruments", back_populates="trades")


class AssetBalances(Base):
    __tablename__ = "asset_balances"

    user_id: Mapped[UUID] = mapped_column(
        SaUUID(as_uuid=True), ForeignKey("users.user_id"), primary_key=True
    )
    instrument_id: Mapped[UUID] = mapped_column(
        SaUUID(as_uuid=True), ForeignKey("instruments.instrument_id"), index=True
    )
    balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.00)
    escrow_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.00)

    # Relationships
    user = relationship("Users", back_populates="asset_balances")
    instrument = relationship("Instruments", back_populates="asset_balances")


class Transactions(Base):
    __tablename__ = "transactions"

    transaction_id: Mapped[UUID] = mapped_column(
        SaUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    user_id: Mapped[UUID] = mapped_column(
        SaUUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # from TransactionType enum .value
    related_id: Mapped[str] = mapped_column(
        String(50), nullable=True
    )  # Could be trade_id, deposit_id, etc.
    balance: Mapped[float] = mapped_column(
        Float, nullable=False
    )  # Cash balance after transaction
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=get_datetime
    )

    # Relationships
    user = relationship("Users", back_populates="transactions")


class EventLogs(Base):
    __tablename__ = "event_logs"

    event_id: Mapped[UUID] = mapped_column(SaUUID(as_uuid=True), primary_key=True, unique=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=False)


# class EngineSnapshots(Base):
#     __tablename__ = "engine_snapshots"

#     snapshot_id: Mapped[UUID] = mapped_column(SaUUID(as_uuid=True), primary_key=True, default=uuid4)
#     instrument_id: Mapped[UUID] = mapped_column(
#         SaUUID(as_uuid=True), ForeignKey("instruments.instrument_id"), index=True
#     )
#     snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)

class EngineContextSnapshots(Base):
    __tablename__ = "engine_context_snapshots"

    snapshot_id: Mapped[UUID] = mapped_column(SaUUID(as_uuid=True), primary_key=True, default=uuid4)
    instrument_id: Mapped[UUID] = mapped_column(
        SaUUID(as_uuid=True), ForeignKey("instruments.instrument_id"), index=True
    )
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
