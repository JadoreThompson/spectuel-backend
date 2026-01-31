import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import UUID, String, Float, ForeignKey, DateTime, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infra.db.models.base import Base, uuid_pk
from engine.enums import OrderType, OrderStatus, Side, StrategyType

if TYPE_CHECKING:
    from infra.db.models.users import Users
    from infra.db.models.order_events import OrderEvents


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
