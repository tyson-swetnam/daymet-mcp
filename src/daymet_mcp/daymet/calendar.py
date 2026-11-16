# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""The Daymet 365-day calendar (DESIGN.md §3.2).

"All Daymet years, including leap years, have 1–365 days ... December 31 is discarded from
leap years" (Daymet V4 R1 user guides). So ``yday`` maps to the ordinary date in every year,
and in a leap year ``yday 60`` is Feb 29 and ``yday 365`` is Dec 30.
"""

from __future__ import annotations

import calendar as _cal
from datetime import date, timedelta

DAYS_PER_YEAR = 365
CALENDAR_RULE = "leap years keep Feb 29 and drop Dec 31"


def is_leap(year: int) -> bool:
    return _cal.isleap(year)


def yday_to_date(year: int, yday: int) -> date:
    """Daymet day-of-year (1..365) to a calendar date."""
    if not 1 <= yday <= DAYS_PER_YEAR:
        raise ValueError(f"Daymet yday must be 1..365, got {yday}")
    return date(year, 1, 1) + timedelta(days=yday - 1)


def in_calendar(day: date) -> bool:
    """False only for Dec 31 of a leap year."""
    return not (is_leap(day.year) and day.month == 12 and day.day == 31)


def date_to_yday(day: date) -> int:
    if not in_calendar(day):
        raise ValueError(f"{day.isoformat()} is not in the Daymet calendar (leap-year Dec 31)")
    return (day - date(day.year, 1, 1)).days + 1


def year_dates(year: int) -> list[date]:
    """The 365 dates of a Daymet year."""
    start = date(year, 1, 1)
    return [start + timedelta(days=i) for i in range(DAYS_PER_YEAR)]


def month_day_count(year: int, month: int) -> int:
    """Number of Daymet days in a calendar month (leap-year December has 30)."""
    n = _cal.monthrange(year, month)[1]
    if month == 12 and is_leap(year):
        n -= 1
    return n


def calendar_info() -> dict[str, object]:
    return {"daysPerYear": DAYS_PER_YEAR, "rule": CALENDAR_RULE}
