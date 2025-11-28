from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class CustomBaseModel(BaseModel):
    model_config = {
        "json_encoders": {
            UUID: lambda x: str(x),
            datetime: lambda x: x.isoformat(),
            Enum: lambda x: x.value,
        }
    }
