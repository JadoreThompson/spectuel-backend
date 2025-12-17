from typing import Any

from models import CustomBaseModel
from .enums import LogEventType


class LogEvent(CustomBaseModel):
    type: LogEventType
    data: Any
