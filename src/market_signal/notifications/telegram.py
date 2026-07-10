from __future__ import annotations

from dataclasses import dataclass

import httpx
from pydantic import SecretStr


class TelegramNotificationError(RuntimeError):
    """Raised when Telegram rejects or cannot receive a notification."""


@dataclass(frozen=True)
class TelegramNotifier:
    bot_token: SecretStr
    chat_id: SecretStr
    timeout_seconds: float = 10.0

    def send_message(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token.get_secret_value()}/sendMessage"
        try:
            response = httpx.post(
                url,
                json={
                    "chat_id": self.chat_id.get_secret_value(),
                    "text": text,
                    "disable_web_page_preview": True,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise TelegramNotificationError(_format_telegram_error(exc.response)) from exc
        except httpx.HTTPError as exc:
            raise TelegramNotificationError("Telegram notification request failed") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise TelegramNotificationError("Telegram response was not valid JSON") from exc
        if not isinstance(data, dict) or data.get("ok") is not True:
            description = data.get("description") if isinstance(data, dict) else None
            raise TelegramNotificationError(description or "Telegram rejected the notification")


def _format_telegram_error(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return f"Telegram HTTP {response.status_code}: non-JSON response"
    description = data.get("description") if isinstance(data, dict) else None
    if description:
        return f"Telegram HTTP {response.status_code}: {description}"
    return f"Telegram HTTP {response.status_code}"
