from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal

from expense_bot.models import ExpenseRecord


@dataclass(slots=True)
class DateRange:
    start: datetime
    end: datetime


@dataclass(slots=True)
class CategoryTotal:
    category: str
    total: Decimal


def day_range(now: datetime) -> DateRange:
    start = datetime.combine(now.date(), time.min, tzinfo=now.tzinfo)
    end = start + timedelta(days=1)
    return DateRange(start=start, end=end)


def week_range(now: datetime) -> DateRange:
    start_date = now.date() - timedelta(days=now.weekday())
    start = datetime.combine(start_date, time.min, tzinfo=now.tzinfo)
    end = start + timedelta(days=7)
    return DateRange(start=start, end=end)


def month_range(now: datetime) -> DateRange:
    start = datetime.combine(now.date().replace(day=1), time.min, tzinfo=now.tzinfo)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return DateRange(start=start, end=end)


def total_for_range(records: list[ExpenseRecord], start: datetime, end: datetime) -> Decimal:
    total = Decimal("0.00")
    for record in records:
        if start <= record.logged_at_local < end:
            total += record.amount
    return total.quantize(Decimal("0.01"))


def recent_records(records: list[ExpenseRecord], limit: int = 5) -> list[ExpenseRecord]:
    ordered = sorted(records, key=lambda record: record.logged_at_local, reverse=True)
    return ordered[:limit]


def category_breakdown(records: list[ExpenseRecord], start: datetime, end: datetime) -> list[CategoryTotal]:
    totals: dict[str, Decimal] = {}
    for record in records:
        if start <= record.logged_at_local < end:
            totals.setdefault(record.category, Decimal("0.00"))
            totals[record.category] += record.amount
    ordered = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    return [CategoryTotal(category=category, total=total.quantize(Decimal("0.01"))) for category, total in ordered]
