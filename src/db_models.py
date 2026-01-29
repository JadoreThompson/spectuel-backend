import uuid
from datetime import datetime

from sqlalchemy import (
    UUID,
    BigInteger,
    Integer,
    Float,
    ForeignKey,
    Numeric,
    String,
    DateTime,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from engine.enums import (
    EngineEventCategory,
    OrderType,
    InstrumentStatus,
    OrderStatus,
    Side,
    StrategyType,
)
from engine.events.enums import OrderEventType, BalanceEventType
from utils import gen_api_key


def uuid_pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def balance_field(**kw):
    return mapped_column(
        Numeric(precision=12, scale=2, asdecimal=False), nullable=False, **kw
    )


class Base(DeclarativeBase):
    pass


class Users(Base):
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = uuid_pk()
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String, nullable=False)

    api_key: Mapped[str] = mapped_column(String, nullable=True, default=gen_api_key)
    jwt: Mapped[str] = mapped_column(String, nullable=True)

    authenticated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        server_onupdate=text("NOW()"),
    )

    orders = relationship("Orders", back_populates="user")
    order_events = relationship("OrderEvents", back_populates="user")
    balance_events = relationship("BalanceEvents", back_populates="user")


class Instruments(Base):
    __tablename__ = "instruments"

    instrument_id: Mapped[uuid.UUID] = uuid_pk()
    symbol: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    starting_price: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=InstrumentStatus.DEAD
    )


class Orders(Base):
    __tablename__ = "orders"

    order_id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False
    )
    order_group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    parent_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.order_id"), nullable=True
    )
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    side: Mapped[Side] = mapped_column(String, nullable=False)
    strategy_type: Mapped[StrategyType] = mapped_column(String, nullable=False)
    order_type: Mapped[OrderType] = mapped_column(String, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    executed_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_fill_price: Mapped[float] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=OrderStatus.PENDING.value
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        server_onupdate=text("NOW()"),
    )

    user = relationship("Users", back_populates="orders")
    events = relationship("OrderEvents")

    def __init__(self, **kw):
        super().__init__(**kw)
        if self.executed_quantity is None:
            self.executed_quantity = 0.0


class OrderEvents(Base):
    __tablename__ = "order_events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.order_id"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id"),
        nullable=False,
        index=True,
    )
    command_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    type: Mapped[OrderEventType] = mapped_column(String, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    timestamp: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, index=True)

    order = relationship("Orders", back_populates="events")
    user = relationship("Users", back_populates="order_events")


class BalanceEvents(Base):
    __tablename__ = "balance_events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id"),
        nullable=False,
        index=True,
    )
    command_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    type: Mapped[BalanceEventType] = mapped_column(String, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    symbol: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    timestamp: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, index=True)

    user = relationship("Users", back_populates="balance_events")


class EventLogs(Base):
    __tablename__ = "event_logs"

    log_id: Mapped[uuid.UUID] = uuid_pk()
    type: Mapped[EngineEventCategory] = mapped_column(String, nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    timestamp: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)


class EngineContextSnapshots(Base):
    __tablename__ = "engine_context_snapshots"

    snapshot_id: Mapped[uuid.UUID] = uuid_pk()
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    topic: Mapped[str] = mapped_column(String, nullable=False)
    partition: Mapped[int] = mapped_column(BigInteger, nullable=False)
    offset: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )


class OHLC(Base):
    __tablename__ = "ohlc"

    id: Mapped[uuid.UUID] = uuid_pk()
    symbol: Mapped[str] = mapped_column(String, nullable=False, index=True)
    timeframe: Mapped[str] = mapped_column(String, nullable=False, index=True)
    timestamp: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)

