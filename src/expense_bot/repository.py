from __future__ import annotations

import asyncio
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal

from expense_bot.config import Settings
from expense_bot.models import DailySummaryRow, ExpenseRecord
from expense_bot.summary import day_range, total_for_range

logger = logging.getLogger(__name__)


class SQLiteExpenseRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def setup(self) -> None:
        await asyncio.to_thread(self._setup_sync)

    async def append_expense(self, expense: ExpenseRecord) -> None:
        logger.info("Appending expense", extra={"user_id": expense.telegram_user_id, "amount": str(expense.amount)})
        saved = await asyncio.to_thread(self._append_expense_sync, expense)
        await self.refresh_daily_summary(expense.telegram_user_id, expense.logged_at_local, expense.currency)
        expense.id = saved.id

    async def list_expenses_for_user(self, user_id: int) -> list[ExpenseRecord]:
        return await asyncio.to_thread(self._list_expenses_for_user_sync, user_id)

    async def recent_expenses_for_user(self, user_id: int, limit: int = 5) -> list[ExpenseRecord]:
        return await asyncio.to_thread(self._recent_expenses_for_user_sync, user_id, limit)

    async def get_expense(self, user_id: int, expense_id: int) -> ExpenseRecord | None:
        return await asyncio.to_thread(self._get_expense_sync, user_id, expense_id)

    async def get_last_expense(self, user_id: int) -> ExpenseRecord | None:
        return await asyncio.to_thread(self._get_last_expense_sync, user_id)

    async def update_expense(self, expense: ExpenseRecord) -> ExpenseRecord:
        updated = await asyncio.to_thread(self._update_expense_sync, expense)
        await self.refresh_daily_summary(expense.telegram_user_id, expense.logged_at_local, expense.currency)
        return updated

    async def delete_expense(self, user_id: int, expense_id: int) -> ExpenseRecord | None:
        deleted = await asyncio.to_thread(self._delete_expense_sync, user_id, expense_id)
        if deleted is not None:
            await self.refresh_daily_summary(user_id, deleted.logged_at_local, deleted.currency)
        return deleted

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
        await asyncio.to_thread(self._upsert_daily_summary_sync, summary_row)

    @contextmanager
    def _connect(self):
        self._settings.database_file.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._settings.database_file, timeout=self._settings.sqlite_busy_timeout_ms / 1000)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute(f"PRAGMA busy_timeout={self._settings.sqlite_busy_timeout_ms}")
            yield connection
        finally:
            connection.close()

    def _setup_sync(self) -> None:
        with self._connect() as connection:
            connection.execute(
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
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_summary (
                    telegram_user_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    total_amount TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY (telegram_user_id, date)
                )
                """
            )
            self._ensure_column(connection, "expenses", "category", "TEXT NOT NULL DEFAULT 'other'")
            self._ensure_column(connection, "expenses", "tags", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "expenses", "deleted_at_utc", "TEXT")
            connection.commit()

    def _append_expense_sync(self, expense: ExpenseRecord) -> ExpenseRecord:
        with self._connect() as connection:
            cursor = connection.execute(
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
                (
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
                ),
            )
            connection.commit()
        return ExpenseRecord(
            id=cursor.lastrowid,
            telegram_user_id=expense.telegram_user_id,
            username=expense.username,
            display_name=expense.display_name,
            amount=expense.amount,
            description=expense.description,
            currency=expense.currency,
            category=expense.category,
            tags=expense.tags,
            logged_at_utc=expense.logged_at_utc,
            logged_at_local=expense.logged_at_local,
            source_message=expense.source_message,
            deleted_at_utc=None,
        )

    def _list_expenses_for_user_sync(self, user_id: int) -> list[ExpenseRecord]:
        with self._connect() as connection:
            rows = connection.execute(
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
                (user_id,),
            ).fetchall()
        return [ExpenseRecord.from_row(dict(row)) for row in rows]

    def _recent_expenses_for_user_sync(self, user_id: int, limit: int) -> list[ExpenseRecord]:
        with self._connect() as connection:
            rows = connection.execute(
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
                (user_id, limit),
            ).fetchall()
        return [ExpenseRecord.from_row(dict(row)) for row in rows]

    def _get_expense_sync(self, user_id: int, expense_id: int) -> ExpenseRecord | None:
        with self._connect() as connection:
            row = connection.execute(
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
                (user_id, expense_id),
            ).fetchone()
        return ExpenseRecord.from_row(dict(row)) if row else None

    def _get_last_expense_sync(self, user_id: int) -> ExpenseRecord | None:
        with self._connect() as connection:
            row = connection.execute(
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
                (user_id,),
            ).fetchone()
        return ExpenseRecord.from_row(dict(row)) if row else None

    def _update_expense_sync(self, expense: ExpenseRecord) -> ExpenseRecord:
        with self._connect() as connection:
            connection.execute(
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
                (
                    str(expense.amount),
                    expense.description,
                    expense.currency,
                    expense.category,
                    ",".join(expense.tags),
                    expense.source_message,
                    expense.id,
                    expense.telegram_user_id,
                ),
            )
            connection.commit()
        return expense

    def _delete_expense_sync(self, user_id: int, expense_id: int) -> ExpenseRecord | None:
        expense = self._get_expense_sync(user_id, expense_id)
        if expense is None:
            return None
        deleted_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE expenses
                SET deleted_at_utc = ?
                WHERE id = ?
                  AND telegram_user_id = ?
                  AND deleted_at_utc IS NULL
                """,
                (deleted_at, expense_id, user_id),
            )
            connection.commit()
        expense.deleted_at_utc = datetime.fromisoformat(deleted_at)
        return expense

    def _upsert_daily_summary_sync(self, summary: DailySummaryRow) -> None:
        with self._connect() as connection:
            connection.execute(
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
                (
                    summary.telegram_user_id,
                    summary.date,
                    summary.currency,
                    str(summary.total_amount),
                    summary.updated_at_utc.isoformat(),
                ),
            )
            connection.commit()

    def _ensure_column(self, connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in existing_columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def parse_decimal(value: str) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))
