import uvicorn
from .base import RunnerBase


class ServerRunner(RunnerBase):
    def __init__(self, **kw):
        self._kw = kw

    def run(self) -> None:
        uvicorn.run("api.app:app", **self._kw)
