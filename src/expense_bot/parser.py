from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from expense_bot.models import ParsedExpenseInput


class ExpenseParseError(ValueError):
    pass


TAG_PATTERN = re.compile(r"#([a-zA-Z0-9_-]+)")
CATEGORY_KEYWORDS = {
    "food": {"lunch", "dinner", "breakfast", "coffee", "tea", "snack", "meal", "restaurant", "food"},
    "transport": {"taxi", "grab", "uber", "bus", "train", "mrt", "transport", "fuel", "petrol"},
    "shopping": {"shop", "shopping", "clothes", "shirt", "shoes", "mall", "purchase"},
    "groceries": {"grocery", "groceries", "supermarket", "market"},
    "entertainment": {"movie", "cinema", "game", "concert", "netflix", "spotify"},
    "utilities": {"electric", "water", "internet", "phone", "utility", "utilities"},
    "health": {"doctor", "clinic", "medicine", "pharmacy", "hospital"},
}


def parse_expense_text(text: str) -> ParsedExpenseInput:
    raw = " ".join(text.strip().split())
    if not raw:
        raise ExpenseParseError("Please send an amount followed by a description, for example: 12.50 lunch")

    tags = tuple(sorted({match.group(1).lower() for match in TAG_PATTERN.finditer(raw)}))
    without_tags = TAG_PATTERN.sub("", raw)
    normalized = " ".join(without_tags.strip().split())
    parts = normalized.split()
    if len(parts) < 2:
        raise ExpenseParseError("Missing description. Example: 12.50 lunch")

    amount_index = _find_amount_index(parts)
    if amount_index is None:
        raise ExpenseParseError("Amount must be a valid number. Example: 12.50 lunch")

    amount_text = parts[amount_index]
    description_parts = parts[:amount_index] + parts[amount_index + 1 :]
    description = " ".join(description_parts).strip()
    amount = _parse_amount(amount_text)
    if amount <= 0:
        raise ExpenseParseError("Amount must be greater than 0.")
    if not description.strip():
        raise ExpenseParseError("Missing description. Example: 12.50 lunch")

    category = infer_category(description, tags)
    return ParsedExpenseInput(
        amount=amount.quantize(Decimal("0.01")),
        description=description.strip(),
        category=category,
        tags=tags,
    )


def infer_category(description: str, tags: tuple[str, ...]) -> str:
    if tags:
        first_tag = tags[0]
        if first_tag in CATEGORY_KEYWORDS:
            return first_tag

    lowered_words = {word.lower() for word in re.findall(r"[a-zA-Z]+", description)}
    for category, keywords in CATEGORY_KEYWORDS.items():
        if lowered_words & keywords:
            return category
    return "other"


def _find_amount_index(parts: list[str]) -> int | None:
    for index, part in enumerate(parts):
        try:
            Decimal(part)
            return index
        except InvalidOperation:
            continue
    return None


def _parse_amount(text: str) -> Decimal:
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ExpenseParseError("Amount must be a valid number. Example: 12.50 lunch") from exc
