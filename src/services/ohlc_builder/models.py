from dataclasses import dataclass


@dataclass
class Bar:
    open: float
    high: float
    low: float
    close: float
    timestamp: int

    def update(self, price: float):
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price
        self.close = price

    def snapshot(self) -> dict:
        return {
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "timestamp": self.timestamp,
        }
