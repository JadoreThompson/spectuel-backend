from typing import Literal, NamedTuple, TypedDict

from engine.enums import MatchOutcome


HeartbeatAction = Literal["add", "remove"]
EngineEventCategory = Literal["balance", "command", "order", "trade"]
HeartbeatMessageT = Literal["register", "heartbeat"]


class MatchResult(NamedTuple):
    outcome: MatchOutcome
    quantity: float
    price: float | None


class RegisterMessage(TypedDict):
    type: HeartbeatMessageT
    symbol: str


class HeartbeatMessage(TypedDict):
    type: HeartbeatMessageT
    symbol: str
