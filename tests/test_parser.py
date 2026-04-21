from decimal import Decimal

import pytest

from expense_bot.parser import ExpenseParseError, parse_expense_text


def test_parse_valid_decimal_amount() -> None:
    result = parse_expense_text("12.50 lunch")
    assert result.amount == Decimal("12.50")
    assert result.description == "lunch"
    assert result.category == "food"
    assert result.tags == ()


def test_parse_valid_integer_amount() -> None:
    result = parse_expense_text("12 dinner")
    assert result.amount == Decimal("12.00")
    assert result.description == "dinner"
    assert result.category == "food"


def test_parse_invalid_amount() -> None:
    with pytest.raises(ExpenseParseError):
        parse_expense_text("abc lunch")


def test_parse_missing_description() -> None:
    with pytest.raises(ExpenseParseError):
        parse_expense_text("12.50")


def test_parse_extra_whitespace() -> None:
    result = parse_expense_text("  18.20    taxi to airport   ")
    assert result.amount == Decimal("18.20")
    assert result.description == "taxi to airport"
    assert result.category == "transport"


def test_parse_description_then_amount() -> None:
    result = parse_expense_text("coffee 4")
    assert result.amount == Decimal("4.00")
    assert result.description == "coffee"
    assert result.category == "food"


def test_parse_tags_and_category() -> None:
    result = parse_expense_text("12.50 lunch #food #team")
    assert result.tags == ("food", "team")
    assert result.category == "food"
