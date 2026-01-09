from typing import Literal, NamedTuple

from engine.enums import MatchOutcome


HeartbeatAction = Literal["add", "remove"]
EngineEventCategory = Literal["balance", "command", "order", "trade"]


class MatchResult(NamedTuple):
    outcome: MatchOutcome
    quantity: float
    price: float | None
