import uvicorn
from .base import BaseRunner


class ServerRunner(BaseRunner):
    def __init__(self, **kw):
        self._kw = kw

    def run(self) -> None:
        uvicorn.run("api.app:app", **self._kw)
