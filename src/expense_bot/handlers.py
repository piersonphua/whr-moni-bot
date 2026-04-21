from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

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
from expense_bot.repository import SQLiteExpenseRepository
from expense_bot.summary import category_breakdown, day_range, month_range, total_for_range, week_range

logger = logging.getLogger(__name__)


def build_router(repository: SQLiteExpenseRepository, settings: Settings) -> Router:
    router = Router()

    @router.message(Command("start"))
    async def start_handler(message: Message) -> None:
        await message.answer(build_start_text(settings.default_currency), parse_mode="Markdown")

    @router.message(Command("help"))
    async def help_handler(message: Message) -> None:
        await message.answer(build_help_text(settings.default_currency), parse_mode="Markdown")

    @router.message(Command("add"))
    async def add_handler(message: Message, command: CommandObject) -> None:
        if not command.args:
            await message.answer("Usage: /add 12.50 lunch")
            return
        await _handle_expense_entry(message, command.args, source_message=message.text or command.args)

    @router.message(Command("today"))
    async def today_handler(message: Message) -> None:
        await _send_total(message, "Today", day_range(_now_local(settings)))

    @router.message(Command("week"))
    async def week_handler(message: Message) -> None:
        await _send_total(message, "This week", week_range(_now_local(settings)))

    @router.message(Command("month"))
    async def month_handler(message: Message) -> None:
        await _send_total(message, "This month", month_range(_now_local(settings)))

    @router.message(Command("recent"))
    async def recent_handler(message: Message) -> None:
        if not message.from_user:
            await message.answer("User context is missing.")
            return
        try:
            records = await repository.recent_expenses_for_user(message.from_user.id, limit=5)
        except Exception:
            logger.exception("Failed to load recent expenses")
            await message.answer(format_sheet_error())
            return
        await message.answer(format_recent(records))

    @router.message(Command("undo"))
    async def undo_handler(message: Message) -> None:
        if not message.from_user:
            await message.answer("User context is missing.")
            return
        try:
            expense = await repository.get_last_expense(message.from_user.id)
            if expense is None or expense.id is None:
                await message.answer("No expense found to undo.")
                return
            deleted = await repository.delete_expense(message.from_user.id, expense.id)
        except Exception:
            logger.exception("Failed to undo expense")
            await message.answer(format_sheet_error())
            return
        if deleted is None:
            await message.answer("No expense found to undo.")
            return
        await message.answer(format_deleted(deleted))

    @router.message(Command("delete"))
    async def delete_handler(message: Message, command: CommandObject) -> None:
        if not message.from_user:
            await message.answer("User context is missing.")
            return
        if not command.args:
            await message.answer("Usage: /delete <id>")
            return
        try:
            expense_id = int(command.args.strip())
        except ValueError:
            await message.answer("Expense id must be a number. Usage: /delete <id>")
            return
        try:
            deleted = await repository.delete_expense(message.from_user.id, expense_id)
        except Exception:
            logger.exception("Failed to delete expense")
            await message.answer(format_sheet_error())
            return
        if deleted is None:
            await message.answer(f"Expense #{expense_id} was not found.")
            return
        await message.answer(format_deleted(deleted))

    @router.message(Command("edit"))
    async def edit_handler(message: Message, command: CommandObject) -> None:
        if not message.from_user:
            await message.answer("User context is missing.")
            return
        if not command.args:
            await message.answer("Usage: /edit <id> <amount> <description>")
            return
        parts = command.args.strip().split(" ", 1)
        if len(parts) < 2:
            await message.answer("Usage: /edit <id> <amount> <description>")
            return
        try:
            expense_id = int(parts[0])
        except ValueError:
            await message.answer("Expense id must be a number. Usage: /edit <id> <amount> <description>")
            return
        try:
            existing = await repository.get_expense(message.from_user.id, expense_id)
            if existing is None:
                await message.answer(f"Expense #{expense_id} was not found.")
                return
            parsed = parse_expense_text(parts[1])
            existing.amount = parsed.amount
            existing.description = parsed.description
            existing.category = parsed.category
            existing.tags = parsed.tags
            existing.source_message = parts[1]
            updated = await repository.update_expense(existing)
        except ExpenseParseError as exc:
            await message.answer(str(exc))
            return
        except Exception:
            logger.exception("Failed to edit expense")
            await message.answer(format_sheet_error())
            return
        await message.answer(format_updated(updated))

    @router.message(Command("stats"))
    async def stats_handler(message: Message) -> None:
        if not message.from_user:
            await message.answer("User context is missing.")
            return
        try:
            records = await repository.list_expenses_for_user(message.from_user.id)
        except Exception:
            logger.exception("Failed to load stats")
            await message.answer(format_sheet_error())
            return
        now = _now_local(settings)
        week = week_range(now)
        month = month_range(now)
        week_total = total_for_range(records, week.start, week.end)
        month_total = total_for_range(records, month.start, month.end)
        avg_daily = _average_daily_spend(records, month.start, month.end)
        top_day, top_day_total = _highest_spend_day(records, month.start, month.end)
        categories = category_breakdown(records, month.start, month.end)
        await message.answer(
            format_stats(
                week_total=week_total,
                month_total=month_total,
                avg_daily=avg_daily,
                top_day=top_day,
                top_day_total=top_day_total,
                categories=categories,
                currency=settings.default_currency,
            )
        )

    @router.message(F.text)
    async def text_handler(message: Message) -> None:
        if not message.text or message.text.startswith("/"):
            return
        await _handle_expense_entry(message, message.text, source_message=message.text)

    async def _handle_expense_entry(message: Message, raw_text: str, source_message: str) -> None:
        if not message.from_user:
            await message.answer("User context is missing.")
            return
        try:
            parsed = parse_expense_text(raw_text)
        except ExpenseParseError as exc:
            await message.answer(str(exc))
            return

        now_utc = datetime.now(timezone.utc)
        now_local = now_utc.astimezone(settings.timezone)
        expense = ExpenseRecord(
            id=None,
            telegram_user_id=message.from_user.id,
            username=message.from_user.username or "",
            display_name=message.from_user.full_name,
            amount=parsed.amount,
            description=parsed.description,
            currency=settings.default_currency,
            category=parsed.category,
            tags=parsed.tags,
            logged_at_utc=now_utc,
            logged_at_local=now_local,
            source_message=source_message,
        )
        try:
            await repository.append_expense(expense)
        except Exception:
            logger.exception("Failed to append expense", extra={"user_id": message.from_user.id})
            await message.answer(format_sheet_error())
            return
        await message.answer(format_confirmation(expense))

    async def _send_total(message: Message, label: str, range_value) -> None:
        if not message.from_user:
            await message.answer("User context is missing.")
            return
        try:
            records = await repository.list_expenses_for_user(message.from_user.id)
        except Exception:
            logger.exception("Failed to load expense totals")
            await message.answer(format_sheet_error())
            return
        total = total_for_range(records, range_value.start, range_value.end)
        await message.answer(format_total(label, total, settings.default_currency))

    return router


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
    best_day, best_total = max(totals.items(), key=lambda item: (item[1], item[0]))
    return best_day, best_total.quantize(Decimal("0.01"))
