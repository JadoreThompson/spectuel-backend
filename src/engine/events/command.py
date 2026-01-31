import uuid
from typing import Literal
from dataclasses import field, dataclass

from engine.events.enums import CommandEventType


@dataclass
class CommandReceivedEvent:
    type: Literal[CommandEventType.COMMAND_RECEIVED]
    command: dict
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class CommandProcessedEvent:
    type: Literal[CommandEventType.COMMAND_PROCESSED]
    command_id: str
    id: uuid.UUID = field(default_factory=uuid.uuid4)
