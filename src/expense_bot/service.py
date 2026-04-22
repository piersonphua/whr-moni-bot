from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol

from expense_bot.config import Settings
from expense_bot.models import ExpenseRecord
from expense_bot.parser import ExpenseParseError, parse_expense_text
from expense_bot.responses import (
    build_help_text,
    build_start_text,
    format_confirmation,
    format_deleted,
    format_recent,
    format_sheet_error,
    format_stats,
    format_total,
    format_updated,
)
from expense_bot.summary import category_breakdown, day_range, month_range, total_for_range, week_range

logger = logging.getLogger(__name__)


class ExpenseRepository(Protocol):
    async def setup(self) -> None: ...

    async def append_expense(self, expense: ExpenseRecord) -> None: ...

    async def list_expenses_for_user(self, user_id: int) -> list[ExpenseRecord]: ...

    async def recent_expenses_for_user(self, user_id: int, limit: int = 5) -> list[ExpenseRecord]: ...

    async def get_expense(self, user_id: int, expense_id: int) -> ExpenseRecord | None: ...

    async def get_last_expense(self, user_id: int) -> ExpenseRecord | None: ...

    async def update_expense(self, expense: ExpenseRecord) -> ExpenseRecord: ...

    async def delete_expense(self, user_id: int, expense_id: int) -> ExpenseRecord | None: ...


@dataclass(slots=True)
class UserContext:
    telegram_user_id: int
    username: str
    display_name: str


@dataclass(slots=True)
class BotReply:
    text: str
    parse_mode: str | None = None


class ExpenseBotService:
    def __init__(self, repository: ExpenseRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    async def process_message(self, user: UserContext, text: str) -> BotReply | None:
        normalized = (text or "").strip()
        if not normalized:
            return None
        if normalized.startswith("/"):
            return await self._process_command(user, normalized)
        return await self._handle_expense_entry(user, normalized, source_message=normalized)

    async def _process_command(self, user: UserContext, text: str) -> BotReply | None:
        command, _, raw_args = text.partition(" ")
        args = raw_args.strip()
        command_name = command[1:].split("@", 1)[0].lower()

        if command_name == "start":
            return BotReply(build_start_text(self._settings.default_currency), parse_mode="Markdown")
        if command_name == "help":
            return BotReply(build_help_text(self._settings.default_currency), parse_mode="Markdown")
        if command_name == "add":
            if not args:
                return BotReply("Usage: /add 12.50 lunch")
            return await self._handle_expense_entry(user, args, source_message=text)
        if command_name == "today":
            return await self._send_total(user.telegram_user_id, "Today", day_range(_now_local(self._settings)))
        if command_name == "week":
            return await self._send_total(user.telegram_user_id, "This week", week_range(_now_local(self._settings)))
        if command_name == "month":
            return await self._send_total(user.telegram_user_id, "This month", month_range(_now_local(self._settings)))
        if command_name == "recent":
            return await self._recent(user.telegram_user_id)
        if command_name == "undo":
            return await self._undo(user.telegram_user_id)
        if command_name == "delete":
            return await self._delete(user.telegram_user_id, args)
        if command_name == "edit":
            return await self._edit(user.telegram_user_id, args)
        if command_name == "stats":
            return await self._stats(user.telegram_user_id)
        return None

    async def _recent(self, user_id: int) -> BotReply:
        try:
            records = await self._repository.recent_expenses_for_user(user_id, limit=5)
        except Exception:
            logger.exception("Failed to load recent expenses", extra={"user_id": user_id})
            return BotReply(format_sheet_error())
        return BotReply(format_recent(records))

    async def _undo(self, user_id: int) -> BotReply:
        try:
            expense = await self._repository.get_last_expense(user_id)
            if expense is None or expense.id is None:
                return BotReply("No expense found to undo.")
            deleted = await self._repository.delete_expense(user_id, expense.id)
        except Exception:
            logger.exception("Failed to undo expense", extra={"user_id": user_id})
            return BotReply(format_sheet_error())
        if deleted is None:
            return BotReply("No expense found to undo.")
        return BotReply(format_deleted(deleted))

    async def _delete(self, user_id: int, raw_args: str) -> BotReply:
        if not raw_args:
            return BotReply("Usage: /delete <id>")
        try:
            expense_id = int(raw_args.strip())
        except ValueError:
            return BotReply("Expense id must be a number. Usage: /delete <id>")
        try:
            deleted = await self._repository.delete_expense(user_id, expense_id)
        except Exception:
            logger.exception("Failed to delete expense", extra={"user_id": user_id, "expense_id": expense_id})
            return BotReply(format_sheet_error())
        if deleted is None:
            return BotReply(f"Expense #{expense_id} was not found.")
        return BotReply(format_deleted(deleted))

    async def _edit(self, user_id: int, raw_args: str) -> BotReply:
        if not raw_args:
            return BotReply("Usage: /edit <id> <amount> <description>")
        parts = raw_args.split(" ", 1)
        if len(parts) < 2:
            return BotReply("Usage: /edit <id> <amount> <description>")
        try:
            expense_id = int(parts[0])
        except ValueError:
            return BotReply("Expense id must be a number. Usage: /edit <id> <amount> <description>")
        try:
            existing = await self._repository.get_expense(user_id, expense_id)
            if existing is None:
                return BotReply(f"Expense #{expense_id} was not found.")
            parsed = parse_expense_text(parts[1])
            existing.amount = parsed.amount
            existing.description = parsed.description
            existing.category = parsed.category
            existing.tags = parsed.tags
            existing.source_message = parts[1]
            updated = await self._repository.update_expense(existing)
        except ExpenseParseError as exc:
            return BotReply(str(exc))
        except Exception:
            logger.exception("Failed to edit expense", extra={"user_id": user_id, "expense_id": expense_id})
            return BotReply(format_sheet_error())
        return BotReply(format_updated(updated))

    async def _stats(self, user_id: int) -> BotReply:
        try:
            records = await self._repository.list_expenses_for_user(user_id)
        except Exception:
            logger.exception("Failed to load stats", extra={"user_id": user_id})
            return BotReply(format_sheet_error())
        now = _now_local(self._settings)
        week = week_range(now)
        month = month_range(now)
        week_total = total_for_range(records, week.start, week.end)
        month_total = total_for_range(records, month.start, month.end)
        avg_daily = _average_daily_spend(records, month.start, month.end)
        top_day, top_day_total = _highest_spend_day(records, month.start, month.end)
        categories = category_breakdown(records, month.start, month.end)
        return BotReply(
            format_stats(
                week_total=week_total,
                month_total=month_total,
                avg_daily=avg_daily,
                top_day=top_day,
                top_day_total=top_day_total,
                categories=categories,
                currency=self._settings.default_currency,
            )
        )

    async def _handle_expense_entry(self, user: UserContext, raw_text: str, source_message: str) -> BotReply:
        try:
            parsed = parse_expense_text(raw_text)
        except ExpenseParseError as exc:
            return BotReply(str(exc))

        now_utc = datetime.now(timezone.utc)
        now_local = now_utc.astimezone(self._settings.timezone)
        expense = ExpenseRecord(
            id=None,
            telegram_user_id=user.telegram_user_id,
            username=user.username,
            display_name=user.display_name,
            amount=parsed.amount,
            description=parsed.description,
            currency=self._settings.default_currency,
            category=parsed.category,
            tags=parsed.tags,
            logged_at_utc=now_utc,
            logged_at_local=now_local,
            source_message=source_message,
        )
        try:
            await self._repository.append_expense(expense)
        except Exception:
            logger.exception("Failed to append expense", extra={"user_id": user.telegram_user_id})
            return BotReply(format_sheet_error())
        return BotReply(format_confirmation(expense))

    async def _send_total(self, user_id: int, label: str, range_value) -> BotReply:
        try:
            records = await self._repository.list_expenses_for_user(user_id)
        except Exception:
            logger.exception("Failed to load expense totals", extra={"user_id": user_id})
            return BotReply(format_sheet_error())
        total = total_for_range(records, range_value.start, range_value.end)
        return BotReply(format_total(label, total, self._settings.default_currency))


def _now_local(settings: Settings) -> datetime:
    return datetime.now(timezone.utc).astimezone(settings.timezone)


def _average_daily_spend(records: list[ExpenseRecord], start: datetime, end: datetime) -> Decimal:
    totals: dict[str, Decimal] = {}
    for record in records:
        if start <= record.logged_at_local < end:
            key = record.logged_at_local.date().isoformat()
            totals.setdefault(key, Decimal("0.00"))
            totals[key] += record.amount
    if not totals:
        return Decimal("0.00")
    total = sum(totals.values(), Decimal("0.00"))
    return (total / Decimal(len(totals))).quantize(Decimal("0.01"))


def _highest_spend_day(records: list[ExpenseRecord], start: datetime, end: datetime) -> tuple[str | None, Decimal]:
    totals: dict[str, Decimal] = {}
    for record in records:
        if start <= record.logged_at_local < end:
            key = record.logged_at_local.date().isoformat()
            totals.setdefault(key, Decimal("0.00"))
            totals[key] += record.amount
    if not totals:
        return None, Decimal("0.00")
    top_day, top_total = max(totals.items(), key=lambda item: (item[1], item[0]))
    return top_day, top_total.quantize(Decimal("0.01"))
