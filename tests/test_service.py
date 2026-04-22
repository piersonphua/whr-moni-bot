from __future__ import annotations

from expense_bot.config import Settings
from expense_bot.repository import SQLiteExpenseRepository
from expense_bot.service import ExpenseBotService, UserContext


def _settings(tmp_path) -> Settings:
    return Settings(
        TELEGRAM_BOT_TOKEN="123456:ABCdef_test_token",
        DATABASE_PATH=str(tmp_path / "expenses.db"),
        DEFAULT_CURRENCY="SGD",
        BOT_TIMEZONE="Asia/Singapore",
        WEBHOOK_SECRET="secret",
        WEBHOOK_PATH="/telegram/webhook",
        LOG_LEVEL="INFO",
    )


def _user() -> UserContext:
    return UserContext(telegram_user_id=1, username="tester", display_name="Test User")


def test_service_add_and_recent(tmp_path) -> None:
    import asyncio

    async def run() -> None:
        settings = _settings(tmp_path)
        repository = SQLiteExpenseRepository(settings)
        await repository.setup()
        service = ExpenseBotService(repository, settings)

        add_reply = await service.process_message(_user(), "12.50 lunch #food")
        assert add_reply is not None
        assert add_reply.text.startswith("Saved #")

        recent_reply = await service.process_message(_user(), "/recent")
        assert recent_reply is not None
        assert "Recent expenses:" in recent_reply.text
        assert "lunch" in recent_reply.text

    asyncio.run(run())


def test_service_edit_usage_validation(tmp_path) -> None:
    import asyncio

    async def run() -> None:
        settings = _settings(tmp_path)
        repository = SQLiteExpenseRepository(settings)
        await repository.setup()
        service = ExpenseBotService(repository, settings)

        reply = await service.process_message(_user(), "/edit 1")
        assert reply is not None
        assert reply.text == "Usage: /edit <id> <amount> <description>"

    asyncio.run(run())
