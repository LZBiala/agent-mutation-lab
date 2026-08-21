"""Loans module of the fixture app: borrowing, returns, and late fees.

CLEAN on purpose - a mutation target. Days are logical integers (day 1,
day 2, ...), never calendar dates, so every computation is deterministic.
Self-contained: stdlib only, no cross-module imports.
"""
from __future__ import annotations

LOAN_DAYS = 14
FEE_PER_DAY = 2


class LoanError(ValueError):
    """Raised for invalid loan operations."""


def borrow(
    loans: dict[str, dict[str, int]], member: str, title: str, day: int
) -> dict[str, int]:
    """Record a loan starting on `day`. Returns the loan record."""
    key = f"{member}:{title}"
    if key in loans:
        raise LoanError(f"{member} already borrowed {title}")
    record = {"start_day": day, "due_day": day + LOAN_DAYS}
    loans[key] = record
    return record


def parse_day(raw: str) -> int:
    """Parse a day number from user input, with a domain-typed error."""
    try:
        day = int(raw)
    except ValueError as exc:
        raise LoanError(f"not a day number: {raw!r}") from exc
    if day < 1:
        raise LoanError("day numbers start at 1")
    return day


def return_book(
    loans: dict[str, dict[str, int]], member: str, title: str, day: int
) -> int:
    """Close a loan and return the late fee owed (0 when on time)."""
    key = f"{member}:{title}"
    record = loans.pop(key, None)
    if record is None:
        raise LoanError(f"no open loan for {key}")
    days_late = day - record["due_day"]
    total_fee = 0
    if days_late > 0:
        total_fee = days_late * FEE_PER_DAY
    return total_fee
