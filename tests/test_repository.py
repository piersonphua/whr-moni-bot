from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from expense_bot.config import Settings
from expense_bot.models import ExpenseRecord
from expense_bot.repository import SQLiteExpenseRepository


def _expense(amount: str, local_time: datetime) -> ExpenseRecord:
    return ExpenseRecord(
        id=None,
        telegram_user_id=1,
        username="user",
        display_name="User",
        amount=Decimal(amount),
        description=f"expense-{amount}",
        currency="SGD",
        category="other",
        tags=(),
        logged_at_utc=local_time.astimezone(ZoneInfo("UTC")),
        logged_at_local=local_time,
        source_message=f"{amount} expense",
    )


async def _create_repository(tmp_path):
    settings = Settings(
        TELEGRAM_BOT_TOKEN="123456:ABCdef_test_token",
        DATABASE_PATH=str(tmp_path / "expenses.db"),
        DEFAULT_CURRENCY="SGD",
        BOT_TIMEZONE="Asia/Singapore",
        WEBHOOK_BASE_URL="",
        WEBHOOK_SECRET="secret",
        HOST="127.0.0.1",
        PORT=8000,
        LOG_LEVEL="INFO",
    )
    repository = SQLiteExpenseRepository(settings)
    await repository.setup()
    return repository


def test_append_and_list_expenses(tmp_path) -> None:
    import asyncio

    async def run() -> None:
        repository = await _create_repository(tmp_path)
        local_time = datetime(2026, 4, 20, 12, 0, tzinfo=ZoneInfo("Asia/Singapore"))
        await repository.append_expense(_expense("12.50", local_time))
        records = await repository.list_expenses_for_user(1)
        assert len(records) == 1
        assert records[0].description == "expense-12.50"
        assert records[0].id is not None

    asyncio.run(run())


def test_recent_expenses_are_descending(tmp_path) -> None:
    import asyncio

    async def run() -> None:
        repository = await _create_repository(tmp_path)
        await repository.append_expense(_expense("10.00", datetime(2026, 4, 20, 9, 0, tzinfo=ZoneInfo("Asia/Singapore"))))
        await repository.append_expense(_expense("20.00", datetime(2026, 4, 20, 10, 0, tzinfo=ZoneInfo("Asia/Singapore"))))
        recent = await repository.recent_expenses_for_user(1, limit=5)
        assert [item.amount for item in recent] == [Decimal("20.00"), Decimal("10.00")]

    asyncio.run(run())


def test_update_and_delete_expense(tmp_path) -> None:
    import asyncio

    async def run() -> None:
        repository = await _create_repository(tmp_path)
        expense = _expense("10.00", datetime(2026, 4, 20, 9, 0, tzinfo=ZoneInfo("Asia/Singapore")))
        await repository.append_expense(expense)
        current = await repository.get_last_expense(1)
        assert current is not None
        current.amount = Decimal("12.50")
        current.description = "updated"
        current.category = "food"
        current.tags = ("food",)
        updated = await repository.update_expense(current)
        assert updated.amount == Decimal("12.50")
        assert updated.category == "food"
        deleted = await repository.delete_expense(1, current.id)
        assert deleted is not None
        remaining = await repository.list_expenses_for_user(1)
        assert remaining == []

    asyncio.run(run())
