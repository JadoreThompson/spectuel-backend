import asyncio


class HeartbeatConnection:
    def __init__(
        self,
        symbol: str,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        last_message_ts: float,
    ) -> None:
        self._symbol = symbol
        self._reader: asyncio.StreamReader = reader
        self._writer: asyncio.StreamWriter = writer
        self.last_message_ts: float = last_message_ts

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def reader(self) -> asyncio.StreamReader:
        return self._reader

    @property
    def writer(self) -> asyncio.StreamWriter:
        return self._writer
