from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot, Dispatcher

from expense_bot.config import Settings
from expense_bot.handlers import build_router
from expense_bot.repository import SQLiteExpenseRepository

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BotRuntime:
    settings: Settings
    repository: SQLiteExpenseRepository
    bot: Bot
    dispatcher: Dispatcher


def build_runtime(settings: Settings) -> BotRuntime:
    repository = SQLiteExpenseRepository(settings)
    bot = Bot(settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(repository, settings))
    return BotRuntime(settings=settings, repository=repository, bot=bot, dispatcher=dispatcher)


async def run_polling_forever(settings: Settings) -> None:
    restart_delay = max(1, settings.restart_delay_seconds)

    while True:
        runtime = build_runtime(settings)
        try:
            await runtime.repository.setup()
            logger.info(
                "Starting polling",
                extra={
                    "polling_timeout": settings.polling_timeout,
                    "database_path": str(settings.database_file),
                },
            )
            await runtime.dispatcher.start_polling(
                runtime.bot,
                polling_timeout=settings.polling_timeout,
                allowed_updates=runtime.dispatcher.resolve_used_update_types(),
                handle_signals=False,
                tasks_concurrency_limit=4,
            )
            logger.info("Polling stopped cleanly")
            return
        except asyncio.CancelledError:
            logger.info("Polling cancelled")
            raise
        except Exception:
            logger.exception("Polling crashed; restarting after backoff", extra={"restart_delay_seconds": restart_delay})
        finally:
            await runtime.bot.session.close()

        await asyncio.sleep(restart_delay)
        restart_delay = min(restart_delay * 2, settings.max_restart_delay_seconds)
