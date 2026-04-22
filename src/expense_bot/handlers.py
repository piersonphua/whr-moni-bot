from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from expense_bot.config import Settings
from expense_bot.service import ExpenseBotService, UserContext


def build_router(service: ExpenseBotService, settings: Settings) -> Router:
    router = Router()

    @router.message(F.text)
    async def text_handler(message: Message) -> None:
        if not message.text or not message.from_user:
            return
        user = UserContext(
            telegram_user_id=message.from_user.id,
            username=message.from_user.username or "",
            display_name=message.from_user.full_name,
        )
        reply = await service.process_message(user, message.text)
        if reply is None:
            return
        await message.answer(reply.text, parse_mode=reply.parse_mode)

    return router
