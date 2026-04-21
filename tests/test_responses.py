from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from expense_bot.models import ExpenseRecord
from expense_bot.responses import build_help_text, build_start_text, format_confirmation, format_recent


def test_start_text_includes_commands() -> None:
    text = build_start_text("SGD")
    assert "/today" in text
    assert "Default currency: SGD" in text


def test_help_text_includes_usage_examples() -> None:
    text = build_help_text("SGD")
    assert "`12.50 lunch`" in text
    assert "/add 18.20 taxi to airport" in text


def test_confirmation_contains_amount_description_and_time() -> None:
    expense = ExpenseRecord(
        id=7,
        telegram_user_id=1,
        username="user",
        display_name="User",
        amount=Decimal("12.50"),
        description="lunch",
        currency="SGD",
        category="food",
        tags=("food",),
        logged_at_utc=datetime.now(tz=ZoneInfo("UTC")),
        logged_at_local=datetime(2026, 4, 20, 13, 45, tzinfo=ZoneInfo("Asia/Singapore")),
        source_message="12.50 lunch",
    )
    text = format_confirmation(expense)
    assert "#7" in text
    assert "12.50 SGD" in text
    assert "lunch" in text
    assert "category: food" in text
    assert "2026-04-20 13:45" in text


def test_recent_text_handles_empty_state() -> None:
    assert format_recent([]) == "No expenses found yet."
