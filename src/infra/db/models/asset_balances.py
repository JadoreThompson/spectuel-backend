import uuid
from typing import TYPE_CHECKING

from sqlalchemy import UUID, Float, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infra.db.models.base import Base

if TYPE_CHECKING:
    from infra.db.models.instruments import Instruments
    from infra.db.models.users import Users


class AssetBalances(Base):
    __tablename__ = "asset_balances"

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instruments.instrument_id"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    escrow_balance: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default=text("0.0")
    )

    instrument = relationship("Instruments")
    user = relationship("Users")
