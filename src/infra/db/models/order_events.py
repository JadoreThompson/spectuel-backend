import uuid
from typing import TYPE_CHECKING

from sqlalchemy import UUID, String, Integer, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infra.db.models.base import Base
from engine.events.enums import OrderEventType

if TYPE_CHECKING:
    from infra.db.models.orders import Orders
    from infra.db.models.users import Users


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
    symbol: Mapped[str] = mapped_column(String, nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    timestamp: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, index=True)

    order = relationship("Orders", back_populates="events")
    user = relationship("Users", back_populates="order_events")
