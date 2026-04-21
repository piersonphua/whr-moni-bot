from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

@dataclass(slots=True)
class ParsedExpenseInput:
    amount: Decimal
    description: str
    category: str
    tags: tuple[str, ...]


@dataclass(slots=True)
class ExpenseRecord:
    id: int | None
    telegram_user_id: int
    username: str
    display_name: str
    amount: Decimal
    description: str
    currency: str
    category: str
    tags: tuple[str, ...]
    logged_at_utc: datetime
    logged_at_local: datetime
    source_message: str
    deleted_at_utc: datetime | None = None

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "ExpenseRecord":
        return cls(
            id=int(row["id"]) if row.get("id") else None,
            telegram_user_id=int(row["telegram_user_id"]),
            username=row.get("username", ""),
            display_name=row.get("display_name", ""),
            amount=Decimal(row["amount"]),
            description=row["description"],
            currency=row["currency"],
            category=row.get("category", "other"),
            tags=tuple(tag for tag in row.get("tags", "").split(",") if tag),
            logged_at_utc=datetime.fromisoformat(row["logged_at_utc"]),
            logged_at_local=datetime.fromisoformat(row["logged_at_local"]),
            source_message=row.get("source_message", ""),
            deleted_at_utc=datetime.fromisoformat(row["deleted_at_utc"]) if row.get("deleted_at_utc") else None,
        )


@dataclass(slots=True)
class DailySummaryRow:
    telegram_user_id: int
    date: str
    currency: str
    total_amount: Decimal
    updated_at_utc: datetime

    def to_row(self) -> list[str]:
        return [
            str(self.telegram_user_id),
            self.date,
            self.currency,
            str(self.total_amount),
            self.updated_at_utc.isoformat(),
        ]
