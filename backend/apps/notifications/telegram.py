"""The Telegram Bot API, behind a small interface so tests and an unconfigured server use a fake.

The bot token sits in the URL path, so neither a URL nor an exception message from the HTTP
library is ever logged or stored: failures are recorded as a short reason only. Messages are
plain text (no parse mode), so nothing in them can become markup.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx2
from django.conf import settings

API = "https://api.telegram.org"
# A send that hangs must not hold the worker: the delivery is retried on the next run instead.
TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class SendResult:
    ok: bool
    # "blocked" when the user blocked the bot or deleted the chat: the channel is then switched off.
    error: str = ""


@dataclass(frozen=True)
class Update:
    update_id: int
    chat_id: int | None
    text: str


class Bot(Protocol):
    def send(self, chat_id: int, text: str) -> SendResult: ...

    def updates(self, offset: int) -> list[Update]: ...


def bot_token() -> str | None:
    """From TELEGRAM_BOT_TOKEN or the file TELEGRAM_BOT_TOKEN_FILE names; None if neither."""
    value = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if value:
        return value
    path = os.environ.get("TELEGRAM_BOT_TOKEN_FILE", "").strip()
    if path:
        try:
            return Path(path).read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    return None


class TelegramBot:
    def __init__(self, token: str, http: httpx2.Client | None = None) -> None:
        self._base = f"{API}/bot{token}"
        self._http = http or httpx2.Client(
            timeout=TIMEOUT_SECONDS, headers={"User-Agent": settings.HTTP_USER_AGENT}
        )

    def _call(self, method: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        response = self._http.post(f"{self._base}/{method}", json=body)
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return response.status_code, payload if isinstance(payload, dict) else {}

    def send(self, chat_id: int, text: str) -> SendResult:
        try:
            status, payload = self._call(
                "sendMessage",
                {"chat_id": chat_id, "text": text[:4096], "disable_web_page_preview": True},
            )
        except httpx2.HTTPError as error:
            return SendResult(False, type(error).__name__)
        if payload.get("ok"):
            return SendResult(True)
        # 403: the user blocked the bot. 400 "chat not found": the chat is gone.
        if status == 403 or (
            status == 400 and "chat not found" in str(payload.get("description", ""))
        ):
            return SendResult(False, "blocked")
        return SendResult(False, f"http_{status}")

    def updates(self, offset: int) -> list[Update]:
        try:
            _status, payload = self._call(
                "getUpdates", {"offset": offset, "timeout": 0, "allowed_updates": ["message"]}
            )
        except httpx2.HTTPError:
            return []
        found = []
        for item in payload.get("result", []) if payload.get("ok") else []:
            message = item.get("message") or {}
            chat = message.get("chat") or {}
            found.append(
                Update(
                    update_id=int(item.get("update_id", 0)),
                    chat_id=chat.get("id") if isinstance(chat.get("id"), int) else None,
                    text=str(message.get("text") or ""),
                )
            )
        return found


def get_bot() -> Bot | None:
    token = bot_token()
    return TelegramBot(token) if token else None
