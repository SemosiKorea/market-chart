from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from market_signal.notifications.telegram import TelegramNotificationError, TelegramNotifier


def test_telegram_notifier_sends_message(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[tuple[str, dict[str, str]]] = []

    def fake_post(url: str, *, json: dict[str, str], timeout: float) -> httpx.Response:
        requests.append((url, json))
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"ok": True}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    notifier = TelegramNotifier(
        bot_token=SecretStr("bot-token"),
        chat_id=SecretStr("chat-id"),
        timeout_seconds=1.0,
    )

    notifier.send_message("hello")

    assert requests == [
        (
            "https://api.telegram.org/botbot-token/sendMessage",
            {"chat_id": "chat-id", "text": "hello", "disable_web_page_preview": True},
        )
    ]


def test_telegram_notifier_raises_without_leaking_token(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(url: str, *, json: dict[str, str], timeout: float) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(400, json={"description": "Bad Request"}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    notifier = TelegramNotifier(
        bot_token=SecretStr("bot-token"),
        chat_id=SecretStr("chat-id"),
    )

    with pytest.raises(TelegramNotificationError) as exc_info:
        notifier.send_message("hello")

    assert "Bad Request" in str(exc_info.value)
    assert "bot-token" not in str(exc_info.value)
