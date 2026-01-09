import uuid
from typing import Literal
from dataclasses import field, dataclass

from engine.commands import CommandBase
from engine.events.enums import CommandEventType
from .base import EngineEventBase


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
