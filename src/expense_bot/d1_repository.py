from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from pyodide.ffi import to_js as _to_js
from js import Object

from expense_bot.models import DailySummaryRow, ExpenseRecord
from expense_bot.summary import day_range, total_for_range


def _to_js(obj):
    return _to_js(obj, dict_converter=Object.fromEntries)


def _to_python(value):
    if value is None:
        return None
    return value.to_py() if hasattr(value, "to_py") else value


class D1ExpenseRepository:
    def __init__(self, db) -> None:
        self._db = db

    async def setup(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                display_name TEXT NOT NULL,
                amount TEXT NOT NULL,
                description TEXT NOT NULL,
                currency TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'other',
                tags TEXT NOT NULL DEFAULT '',
                logged_at_utc TEXT NOT NULL,
                logged_at_local TEXT NOT NULL,
                source_message TEXT NOT NULL,
                deleted_at_utc TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS daily_summary (
                telegram_user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                currency TEXT NOT NULL,
                total_amount TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL,
                PRIMARY KEY (telegram_user_id, date)
            )
            """,
        ]
        await self._db.batch(_to_js([self._db.prepare(statement) for statement in statements]))

    async def append_expense(self, expense: ExpenseRecord) -> None:
        result = await self._run(
            """
            INSERT INTO expenses (
                telegram_user_id,
                username,
                display_name,
                amount,
                description,
                currency,
                category,
                tags,
                logged_at_utc,
                logged_at_local,
                source_message,
                deleted_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                expense.telegram_user_id,
                expense.username,
                expense.display_name,
                str(expense.amount),
                expense.description,
                expense.currency,
                expense.category,
                ",".join(expense.tags),
                expense.logged_at_utc.isoformat(),
                expense.logged_at_local.isoformat(),
                expense.source_message,
                None,
            ],
        )
        meta = _to_python(result.meta) or {}
        expense.id = int(meta.get("last_row_id", 0)) or None
        await self.refresh_daily_summary(expense.telegram_user_id, expense.logged_at_local, expense.currency)

    async def list_expenses_for_user(self, user_id: int) -> list[ExpenseRecord]:
        result = await self._run(
            """
            SELECT
                id,
                telegram_user_id,
                username,
                display_name,
                amount,
                description,
                currency,
                category,
                tags,
                logged_at_utc,
                logged_at_local,
                source_message,
                deleted_at_utc
            FROM expenses
            WHERE telegram_user_id = ?
              AND deleted_at_utc IS NULL
            ORDER BY logged_at_local ASC
            """,
            [user_id],
        )
        return [ExpenseRecord.from_row(row) for row in (_to_python(result.results) or [])]

    async def recent_expenses_for_user(self, user_id: int, limit: int = 5) -> list[ExpenseRecord]:
        result = await self._run(
            """
            SELECT
                id,
                telegram_user_id,
                username,
                display_name,
                amount,
                description,
                currency,
                category,
                tags,
                logged_at_utc,
                logged_at_local,
                source_message,
                deleted_at_utc
            FROM expenses
            WHERE telegram_user_id = ?
              AND deleted_at_utc IS NULL
            ORDER BY logged_at_local DESC
            LIMIT ?
            """,
            [user_id, limit],
        )
        return [ExpenseRecord.from_row(row) for row in (_to_python(result.results) or [])]

    async def get_expense(self, user_id: int, expense_id: int) -> ExpenseRecord | None:
        row = await self._first(
            """
            SELECT
                id,
                telegram_user_id,
                username,
                display_name,
                amount,
                description,
                currency,
                category,
                tags,
                logged_at_utc,
                logged_at_local,
                source_message,
                deleted_at_utc
            FROM expenses
            WHERE telegram_user_id = ?
              AND id = ?
              AND deleted_at_utc IS NULL
            """,
            [user_id, expense_id],
        )
        return ExpenseRecord.from_row(row) if row else None

    async def get_last_expense(self, user_id: int) -> ExpenseRecord | None:
        row = await self._first(
            """
            SELECT
                id,
                telegram_user_id,
                username,
                display_name,
                amount,
                description,
                currency,
                category,
                tags,
                logged_at_utc,
                logged_at_local,
                source_message,
                deleted_at_utc
            FROM expenses
            WHERE telegram_user_id = ?
              AND deleted_at_utc IS NULL
            ORDER BY logged_at_local DESC, id DESC
            LIMIT 1
            """,
            [user_id],
        )
        return ExpenseRecord.from_row(row) if row else None

    async def update_expense(self, expense: ExpenseRecord) -> ExpenseRecord:
        await self._run(
            """
            UPDATE expenses
            SET amount = ?,
                description = ?,
                currency = ?,
                category = ?,
                tags = ?,
                source_message = ?
            WHERE id = ?
              AND telegram_user_id = ?
              AND deleted_at_utc IS NULL
            """,
            [
                str(expense.amount),
                expense.description,
                expense.currency,
                expense.category,
                ",".join(expense.tags),
                expense.source_message,
                expense.id,
                expense.telegram_user_id,
            ],
        )
        await self.refresh_daily_summary(expense.telegram_user_id, expense.logged_at_local, expense.currency)
        return expense

    async def delete_expense(self, user_id: int, expense_id: int) -> ExpenseRecord | None:
        expense = await self.get_expense(user_id, expense_id)
        if expense is None:
            return None
        deleted_at = datetime.now(timezone.utc).isoformat()
        await self._run(
            """
            UPDATE expenses
            SET deleted_at_utc = ?
            WHERE id = ?
              AND telegram_user_id = ?
              AND deleted_at_utc IS NULL
            """,
            [deleted_at, expense_id, user_id],
        )
        expense.deleted_at_utc = datetime.fromisoformat(deleted_at)
        await self.refresh_daily_summary(user_id, expense.logged_at_local, expense.currency)
        return expense

    async def refresh_daily_summary(self, user_id: int, logged_at_local: datetime, currency: str) -> None:
        records = await self.list_expenses_for_user(user_id)
        current_day = day_range(logged_at_local)
        total = total_for_range(records, current_day.start, current_day.end)
        summary_row = DailySummaryRow(
            telegram_user_id=user_id,
            date=logged_at_local.date().isoformat(),
            currency=currency,
            total_amount=total,
            updated_at_utc=datetime.now(timezone.utc),
        )
        await self._run(
            """
            INSERT INTO daily_summary (
                telegram_user_id,
                date,
                currency,
                total_amount,
                updated_at_utc
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_user_id, date) DO UPDATE SET
                currency = excluded.currency,
                total_amount = excluded.total_amount,
                updated_at_utc = excluded.updated_at_utc
            """,
            summary_row.to_row(),
        )

    async def _run(self, query: str, params: list[object]):
        statement = self._db.prepare(query).bind(*params)
        return await statement.run()

    async def _first(self, query: str, params: list[object]) -> dict[str, object] | None:
        statement = self._db.prepare(query).bind(*params)
        return _to_python(await statement.first())
