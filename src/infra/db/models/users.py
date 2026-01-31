import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infra.db.models.base import Base, uuid_pk
from utils import gen_api_key

if TYPE_CHECKING:
    from infra.db.models.orders import Orders
    from infra.db.models.order_events import OrderEvents
    from infra.db.models.balance_events import BalanceEvents


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
