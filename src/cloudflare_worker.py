from __future__ import annotations

import json
import logging
from urllib.parse import urlparse

from js import Headers, Object, fetch
from pyodide.ffi import to_js as _to_js
from workers import Response, WorkerEntrypoint

from expense_bot.config import Settings
from expense_bot.d1_repository import D1ExpenseRepository
from expense_bot.service import ExpenseBotService, UserContext

logger = logging.getLogger(__name__)


def _to_js(obj):
    return _to_js(obj, dict_converter=Object.fromEntries)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        url = urlparse(request.url)
        path = url.path or "/"

        if request.method == "GET" and path == "/healthz":
            return Response.new("ok", _to_js({"status": 200}))

        settings = _settings_from_env(self.env)
        if request.method != "POST" or path != settings.webhook_path:
            return Response.new("Not Found", _to_js({"status": 404}))

        if settings.webhook_secret:
            provided = request.headers.get("x-telegram-bot-api-secret-token")
            if provided != settings.webhook_secret:
                return Response.new("Unauthorized", _to_js({"status": 401}))

        update = await request.json()
        update_data = update.to_py() if hasattr(update, "to_py") else update
        message = update_data.get("message") or update_data.get("edited_message")
        if not message or "text" not in message:
            return Response.json({"ok": True})

        user_data = message.get("from") or {}
        chat = message.get("chat") or {}
        text = message.get("text", "")
        user = UserContext(
            telegram_user_id=int(user_data.get("id", 0)),
            username=user_data.get("username", "") or "",
            display_name=user_data.get("first_name", "") or chat.get("title", "") or "Telegram User",
        )

        repository = D1ExpenseRepository(self.env.DB)
        await repository.setup()
        service = ExpenseBotService(repository, settings)
        reply = await service.process_message(user, text)
        if reply is None:
            return Response.json({"ok": True})

        await _send_telegram_reply(
            token=settings.telegram_bot_token,
            chat_id=chat.get("id"),
            text=reply.text,
            parse_mode=reply.parse_mode,
        )
        return Response.json({"ok": True})


async def _send_telegram_reply(token: str, chat_id: int | None, text: str, parse_mode: str | None) -> None:
    if chat_id is None:
        return
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    init = _to_js(
        {
            "method": "POST",
            "headers": Headers.new(_to_js({"content-type": "application/json;charset=UTF-8"})),
            "body": json.dumps(payload),
        }
    )
    response = await fetch(f"https://api.telegram.org/bot{token}/sendMessage", init)
    if not response.ok:
        body = await response.text()
        logger.error("Telegram sendMessage failed", extra={"status": response.status, "body": body})


def _settings_from_env(env) -> Settings:
    values = {
        "TELEGRAM_BOT_TOKEN": str(env.TELEGRAM_BOT_TOKEN),
        "DEFAULT_CURRENCY": str(getattr(env, "DEFAULT_CURRENCY", "SGD")),
        "BOT_TIMEZONE": str(getattr(env, "BOT_TIMEZONE", "Asia/Singapore")),
        "WEBHOOK_SECRET": _env_optional(env, "WEBHOOK_SECRET"),
        "WEBHOOK_PATH": str(getattr(env, "WEBHOOK_PATH", "/telegram/webhook")),
        "POLLING_TIMEOUT": int(getattr(env, "POLLING_TIMEOUT", 30)),
        "RESTART_DELAY_SECONDS": int(getattr(env, "RESTART_DELAY_SECONDS", 5)),
        "MAX_RESTART_DELAY_SECONDS": int(getattr(env, "MAX_RESTART_DELAY_SECONDS", 60)),
        "SQLITE_BUSY_TIMEOUT_MS": int(getattr(env, "SQLITE_BUSY_TIMEOUT_MS", 5000)),
        "LOG_LEVEL": str(getattr(env, "LOG_LEVEL", "INFO")),
    }
    return Settings(**values)


def _env_optional(env, name: str) -> str | None:
    value = getattr(env, name, None)
    if value in (None, ""):
        return None
    return str(value)
