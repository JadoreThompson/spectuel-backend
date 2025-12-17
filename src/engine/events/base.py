import time
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field

# from spectuel_engine_utils.models import CustomBaseModel
from models import CustomBaseModel


class EngineEventBase(CustomBaseModel):
    id: UUID = Field(default_factory=uuid4)
    version: int
    details: dict[str, Any] | None = None
    timestamp: int = Field(default_factory=lambda: int(time.time()))
