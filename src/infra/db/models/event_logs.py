import uuid

from sqlalchemy import UUID, String, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from infra.db.models.base import Base, uuid_pk
from engine.enums import EngineEventCategory


class EventLogs(Base):
    __tablename__ = "event_logs"

    log_id: Mapped[uuid.UUID] = uuid_pk()
    type: Mapped[EngineEventCategory] = mapped_column(String, nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    timestamp: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
