from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from expense_bot.models import ExpenseRecord
from expense_bot.summary import category_breakdown, day_range, month_range, recent_records, total_for_range, week_range


def _record(amount: str, local_timestamp: str, category: str = "other") -> ExpenseRecord:
    local_dt = datetime.fromisoformat(local_timestamp).replace(tzinfo=ZoneInfo("Asia/Singapore"))
    utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
    return ExpenseRecord(
        id=None,
        telegram_user_id=1,
        username="user",
        display_name="User",
        amount=Decimal(amount),
        description="test",
        currency="SGD",
        category=category,
        tags=(),
        logged_at_utc=utc_dt,
        logged_at_local=local_dt,
        source_message=f"{amount} test",
    )


def test_today_total() -> None:
    now = datetime(2026, 4, 20, 12, 0, tzinfo=ZoneInfo("Asia/Singapore"))
    current_day = day_range(now)
    records = [
        _record("10.00", "2026-04-20T09:00:00"),
        _record("5.50", "2026-04-20T18:00:00"),
        _record("100.00", "2026-04-19T18:00:00"),
    ]
    assert total_for_range(records, current_day.start, current_day.end) == Decimal("15.50")


def test_week_total() -> None:
    now = datetime(2026, 4, 20, 12, 0, tzinfo=ZoneInfo("Asia/Singapore"))
    current_week = week_range(now)
    records = [
        _record("10.00", "2026-04-20T09:00:00"),
        _record("5.00", "2026-04-22T18:00:00"),
        _record("3.00", "2026-04-27T09:00:00"),
    ]
    assert total_for_range(records, current_week.start, current_week.end) == Decimal("15.00")


def test_month_total_respects_boundaries() -> None:
    now = datetime(2026, 4, 20, 12, 0, tzinfo=ZoneInfo("Asia/Singapore"))
    current_month = month_range(now)
    records = [
        _record("10.00", "2026-04-01T00:00:00"),
        _record("5.25", "2026-04-30T23:59:00"),
        _record("9.00", "2026-05-01T00:00:00"),
    ]
    assert total_for_range(records, current_month.start, current_month.end) == Decimal("15.25")


def test_recent_records_returns_latest_five() -> None:
    records = [_record(str(index), f"2026-04-{index:02d}T12:00:00") for index in range(1, 8)]
    recent = recent_records(records, limit=5)
    assert [record.amount for record in recent] == [
        Decimal("7"),
        Decimal("6"),
        Decimal("5"),
        Decimal("4"),
        Decimal("3"),
    ]


def test_category_breakdown_orders_highest_first() -> None:
    now = datetime(2026, 4, 20, 12, 0, tzinfo=ZoneInfo("Asia/Singapore"))
    current_month = month_range(now)
    records = [
        _record("10.00", "2026-04-20T09:00:00", category="food"),
        _record("15.00", "2026-04-21T09:00:00", category="transport"),
        _record("5.00", "2026-04-22T09:00:00", category="food"),
    ]
    breakdown = category_breakdown(records, current_month.start, current_month.end)
    assert [(item.category, item.total) for item in breakdown] == [
        ("food", Decimal("15.00")),
        ("transport", Decimal("15.00")),
    ]
