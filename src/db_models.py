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
    OrderType,
    InstrumentStatus,
    OrderStatus,
    Side
)
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

    orders = relationship("Orders", back_populates="user", cascade="all, delete-orphan")


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


class EventLogs(Base):
    __tablename__ = "event_logs"

    event_id: Mapped[uuid.UUID] = uuid_pk()
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=False)


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
