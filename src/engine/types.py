from typing import NamedTuple

from engine.enums import MatchOutcome


class MatchResult(NamedTuple):
    outcome: MatchOutcome
    quantity: int
    price: float | None
