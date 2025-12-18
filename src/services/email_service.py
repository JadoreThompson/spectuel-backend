import logging

import requests
from aiohttp import ClientSession

from config import BREVO_API_KEY


class EmailService:
    _instances: dict[tuple[str, str], "EmailService"] = {}

    def __new__(cls, sender_name: str, sender_email: str):
        key = (sender_name, sender_email)
        if key in cls._instances:
            return cls._instances[key]
        instance = super().__new__(cls)
        cls._instances[key] = instance
        return instance

    def __init__(self, sender_name: str, sender_email: str) -> None:
        if hasattr(self, "_initialised") and self._initialised:
            return

        self.sender_name = sender_name
        self.sender_email = sender_email
        self._http_sess: ClientSession | None = None
        self._initialised = True
        self._logger = logging.getLogger("email_service")

    async def send_email(self, recipient: str, subject: str, body: str) -> None:
        if not recipient:
            raise ValueError("recipient is required")

        try:
            await self._send_via_brevo(recipient, subject, body)
            self._logger.info(f"Email sent via Brevo to {recipient}")
        except Exception as e:
            self._logger.exception(f"Brevo send failed, attempting SMTP fallback: {e}")

    async def _send_via_brevo(self, recipient: str, subject: str, body: str) -> None:
        """
        Uses Brevo SMTP API endpoint: POST https://api.brevo.com/v3/smtp/email
        Documentation: https://developers.brevo.com/
        """
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "accept": "application/json",
            "api-key": BREVO_API_KEY,
            "content-type": "application/json",
        }

        payload = {
            "sender": {"name": self.sender_name, "email": self.sender_email},
            "to": [{"email": recipient}],
            "subject": subject,
            "textContent": body,
            "htmlContent": self._escape_html(body),
        }

        if self._http_sess is None or self._http_sess.closed():
            self._http_sess = ClientSession()

        rsp = await self._http_sess.post(url, json=payload, headers=headers)
        if rsp.status >= 400:
            text = await rsp.text()
            self._logger.error(f"Brevo API error: {rsp.status} - {text}")
            raise RuntimeError(f"Brevo API returned {rsp.status}: {text}")

    async def close(self):
        """Gracefully close the internal HTTP session."""
        if self._http_sess and not self._http_sess.closed:
            await self._http_sess.close()

    def send_email_sync(self, recipient: str, subject: str, body: str) -> None:
        """
        Pure synchronous version of send_email().
        No asyncio used. Uses requests directly.
        """
        if not recipient:
            raise ValueError("recipient is required")

        try:
            self._send_via_brevo_sync(recipient, subject, body)
            self._logger.info(f"Email sent (sync) via Brevo to {recipient}")
        except Exception as e:
            self._logger.exception(f"Brevo sync send failed: {e}")
            raise

    def _send_via_brevo_sync(self, recipient: str, subject: str, body: str) -> None:
        """Synchronous version using requests instead of aiohttp."""
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "accept": "application/json",
            "api-key": BREVO_API_KEY,
            "content-type": "application/json",
        }

        payload = {
            "sender": {"name": self.sender_name, "email": self.sender_email},
            "to": [{"email": recipient}],
            "subject": subject,
            "textContent": body,
            "htmlContent": self._escape_html(body),
        }

        rsp = requests.post(url, json=payload, headers=headers, timeout=15)
        if rsp.status_code >= 400:
            self._logger.error(f"Brevo API error: {rsp.status_code} - {rsp.text}")
            raise RuntimeError(f"Brevo API returned {rsp.status_code}: {rsp.text}")

    @staticmethod
    def _escape_html(s: str) -> str:
        """Minimal HTML escaper for embedding plain text into <pre> blocks."""
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;")
        )
