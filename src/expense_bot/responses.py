from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from expense_bot.models import ExpenseRecord
from expense_bot.summary import CategoryTotal


def build_start_text(currency: str) -> str:
    return (
        "Log expenses by sending a message like `12.50 lunch`, `lunch 12.50`, or `12.50 lunch #food`.\n\n"
        "Commands:\n"
        "/add <amount> <description>\n"
        "/today\n"
        "/week\n"
        "/month\n"
        "/recent\n"
        "/stats\n"
        "/undo\n"
        "/delete <id>\n"
        "/edit <id> <amount> <description>\n"
        "/help\n\n"
        f"Default currency: {currency}"
    )


def build_help_text(currency: str) -> str:
    return (
        "Accepted formats: `<amount> <description>`, `<description> <amount>`, and optional tags like `#food`\n"
        "Examples:\n"
        "- `12.50 lunch`\n"
        "- `lunch 12.50`\n"
        "- `12.50 lunch #food`\n"
        "- `/add 18.20 taxi to airport`\n\n"
        "Correction commands:\n"
        "- `/undo` removes the latest expense\n"
        "- `/delete 12` removes a specific expense id\n"
        "- `/edit 12 9.50 coffee` updates a specific expense\n\n"
        f"All expenses are stored in {currency}."
    )


def format_confirmation(expense: ExpenseRecord) -> str:
    time_text = expense.logged_at_local.strftime("%Y-%m-%d %H:%M")
    tags = f" | tags: {', '.join(f'#{tag}' for tag in expense.tags)}" if expense.tags else ""
    return (
        f"Saved #{expense.id} | {expense.amount} {expense.currency} | {expense.description} "
        f"| category: {expense.category}{tags} | {time_text}"
    )


def format_total(label: str, amount: Decimal, currency: str) -> str:
    return f"{label}: {amount} {currency}"


def format_recent(records: list[ExpenseRecord]) -> str:
    if not records:
        return "No expenses found yet."

    lines = ["Recent expenses:"]
    for record in records:
        timestamp = record.logged_at_local.strftime("%Y-%m-%d %H:%M")
        lines.append(
            f"- #{record.id} | {timestamp} | {record.amount} {record.currency} | "
            f"{record.description} | {record.category}"
        )
    return "\n".join(lines)


def format_sheet_error() -> str:
    return "I could not save or load expenses right now. Please try again in a moment."


def format_logged_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def format_deleted(expense: ExpenseRecord) -> str:
    return f"Deleted expense #{expense.id}: {expense.amount} {expense.currency} for {expense.description}."


def format_updated(expense: ExpenseRecord) -> str:
    return f"Updated expense #{expense.id}: {expense.amount} {expense.currency} for {expense.description} ({expense.category})."


def format_stats(
    week_total: Decimal,
    month_total: Decimal,
    avg_daily: Decimal,
    top_day: str | None,
    top_day_total: Decimal,
    categories: list[CategoryTotal],
    currency: str,
) -> str:
    lines = [
        "Stats:",
        f"- This week: {week_total} {currency}",
        f"- This month: {month_total} {currency}",
        f"- Average daily spend this month: {avg_daily} {currency}",
    ]
    if top_day is not None:
        lines.append(f"- Highest spend day this month: {top_day} ({top_day_total} {currency})")
    if categories:
        lines.append("- Category breakdown this month:")
        for item in categories[:5]:
            lines.append(f"  - {item.category}: {item.total} {currency}")
    return "\n".join(lines)
