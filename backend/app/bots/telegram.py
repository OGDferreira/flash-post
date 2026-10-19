"""Minimal Telegram Bot API client for the sales bots.

Only the methods the engine uses. Errors surface as ``TelegramError`` with the
API's error code so callers can tell "the lead blocked the bot" (403) from a
transient failure (429/5xx, retried here with Telegram's ``retry_after``).
"""

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.bots import http

API_BASE = "https://api.telegram.org"
MAX_ATTEMPTS = 3
_background: set[asyncio.Task] = set()  # keeps fire-and-forget calls alive until they finish


@dataclass
class TelegramError(Exception):
    method: str
    status: int
    description: str

    def __str__(self) -> str:  # never includes the token
        return f"Telegram {self.method} failed ({self.status}): {self.description}"

    @property
    def blocked(self) -> bool:
        return self.status == 403


@dataclass
class InputFile:
    name: str
    content: bytes
    content_type: str


class TelegramClient:
    def __init__(self, token: str) -> None:
        self._token = token

    async def call(self, method: str, params: dict[str, Any] | None = None, files: dict[str, InputFile] | None = None) -> Any:
        url = f"{API_BASE}/bot{self._token}/{method}"
        params = {k: v for k, v in (params or {}).items() if v is not None}
        last: TelegramError | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                async with http.client(60.0 if files else 20.0) as session:
                    if files:
                        data = {k: (json.dumps(v) if isinstance(v, (dict, list, bool)) else str(v)) for k, v in params.items()}
                        response = await session.post(
                            url,
                            data=data,
                            files={k: (f.name, f.content, f.content_type) for k, f in files.items()},
                        )
                    else:
                        response = await session.post(url, json=params)
            except httpx.HTTPError as exc:
                last = TelegramError(method, 0, type(exc).__name__)
                await asyncio.sleep(1 + attempt)
                continue
            try:
                body = response.json()
            except ValueError:
                body = {"ok": False, "description": f"HTTP {response.status_code}"}
            if body.get("ok"):
                return body.get("result")
            status = int(body.get("error_code") or response.status_code)
            last = TelegramError(method, status, str(body.get("description") or "")[:300])
            if status == 429 or status >= 500:
                retry = (body.get("parameters") or {}).get("retry_after") or (1 + attempt)
                await asyncio.sleep(min(float(retry), 10.0))
                continue
            raise last
        assert last is not None
        raise last

    # --- bot setup ---
    async def get_me(self) -> dict:
        return await self.call("getMe")

    async def set_webhook(self, url: str, secret_token: str) -> None:
        await self.call(
            "setWebhook",
            {
                "url": url,
                "secret_token": secret_token,
                "allowed_updates": ["message", "callback_query", "my_chat_member", "channel_post"],
                "drop_pending_updates": False,
            },
        )

    async def delete_webhook(self) -> None:
        await self.call("deleteWebhook")

    # --- messages ---
    async def send_message(self, chat_id: int, text: str, reply_markup: dict | None = None, protect: bool = False) -> dict:
        return await self.call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
                "protect_content": protect or None,
                "link_preview_options": {"is_disabled": True},
            },
        )

    async def send_media(
        self,
        method: str,
        field: str,
        chat_id: int,
        media: str | InputFile,
        caption: str | None = None,
        reply_markup: dict | None = None,
        spoiler: bool = False,
        protect: bool = False,
        silent: bool = False,
    ) -> dict:
        params: dict[str, Any] = {
            "chat_id": chat_id,
            "disable_notification": silent or None,
            "caption": caption or None,
            "parse_mode": "HTML" if caption else None,
            "reply_markup": reply_markup,
            "has_spoiler": spoiler or None,
            "protect_content": protect or None,
        }
        if isinstance(media, InputFile):
            return await self.call(method, params, files={field: media})
        params[field] = media
        return await self.call(method, params)

    async def send_media_group(self, chat_id: int, media: list[dict], files: dict[str, InputFile], protect: bool = False) -> list:
        params = {"chat_id": chat_id, "media": media, "protect_content": protect or None}
        return await self.call("sendMediaGroup", params, files=files or None)

    async def delete_messages(self, chat_id: int, message_ids: list[int]) -> None:
        """Best effort: messages already deleted by the lead (or older than 48h) are skipped."""
        if not message_ids:
            return
        try:
            await self.call("deleteMessages", {"chat_id": chat_id, "message_ids": message_ids[:100]})
        except TelegramError as exc:
            if exc.status != 400:
                raise

    async def send_chat_action(self, chat_id: int, action: str) -> None:
        """Fire and forget: "digitando…" must not delay the message that follows it."""
        async def run() -> None:
            try:
                await self.call("sendChatAction", {"chat_id": chat_id, "action": action})
            except TelegramError:
                pass

        task = asyncio.create_task(run())
        _background.add(task)
        task.add_done_callback(_background.discard)

    async def answer_callback(self, callback_id: str, text: str | None = None, alert: bool = False) -> None:
        try:
            await self.call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text, "show_alert": alert or None})
        except TelegramError:
            pass

    # --- groups ---
    async def get_chat(self, chat_id: int | str) -> dict:
        return await self.call("getChat", {"chat_id": chat_id})

    async def get_chat_member(self, chat_id: int, user_id: int) -> dict:
        return await self.call("getChatMember", {"chat_id": chat_id, "user_id": user_id})


    async def create_invite_link(self, chat_id: int, name: str, expire_date: int) -> str:
        result = await self.call(
            "createChatInviteLink",
            {"chat_id": chat_id, "name": name[:32], "member_limit": 1, "expire_date": expire_date},
        )
        return result["invite_link"]

    async def remove_member(self, chat_id: int, user_id: int) -> None:
        """Kick without a permanent ban, so the lead can buy again later."""
        await self.call("banChatMember", {"chat_id": chat_id, "user_id": user_id})
        await self.call("unbanChatMember", {"chat_id": chat_id, "user_id": user_id, "only_if_banned": True})
