import uuid

from sqlalchemy import String, Float
from sqlalchemy.orm import Mapped, mapped_column

from infra.db.models.base import Base, uuid_pk
from engine.enums import InstrumentStatus


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
