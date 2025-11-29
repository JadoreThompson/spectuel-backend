import time
from collections import defaultdict

from starlette.types import ASGIApp, Scope, Receive, Send


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp, limit: int = 100, window: int = 60):
        self.app = app
        self.limit = limit
        self.window = window
        self._records = defaultdict(lambda: (0.0, 0))

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        host = client[0] if client else None
        if not host:
            await self._send_error(send, 400, "Client host not found")
            return

        now = time.time()
        start, count = self._records[host]

        if now - start >= self.window:
            start = now
            count = 0

        if count >= self.limit:
            await self._send_error(send, 429, f"Rate limit exceeded")
            return

        self._records[host] = (start, count + 1)

        await self.app(scope, receive, send)

    async def _send_error(
        self, send: Send, status_code: int, message: str, headers=None
    ):
        headers = headers or []
        body = f'{{"error": "{message}"}}'.encode()
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [(b"content-type", b"application/json")] + headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body,
            }
        )
