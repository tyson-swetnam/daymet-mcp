# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""The Daymet 365-day calendar (leap years keep Feb 29 and drop Dec 31)."""

from __future__ import annotations

from datetime import date

import pytest

from daymet_mcp.daymet.calendar import (
    calendar_info,
    date_to_yday,
    in_calendar,
    is_leap,
    month_day_count,
    yday_to_date,
    year_dates,
)


def test_leap_year_mapping() -> None:
    assert is_leap(2020)
    assert yday_to_date(2020, 59) == date(2020, 2, 28)
    assert yday_to_date(2020, 60) == date(2020, 2, 29)
    assert yday_to_date(2020, 365) == date(2020, 12, 30)


def test_non_leap_year_mapping() -> None:
    assert not is_leap(2019)
    assert yday_to_date(2019, 60) == date(2019, 3, 1)
    assert yday_to_date(2019, 365) == date(2019, 12, 31)


@pytest.mark.parametrize("yday", [0, 366, -1])
def test_yday_out_of_range(yday: int) -> None:
    with pytest.raises(ValueError):
        yday_to_date(2020, yday)


def test_leap_dec31_not_in_calendar() -> None:
    assert not in_calendar(date(2020, 12, 31))
    assert in_calendar(date(2019, 12, 31))
    assert in_calendar(date(2020, 2, 29))
    with pytest.raises(ValueError, match="not in the Daymet calendar"):
        date_to_yday(date(2020, 12, 31))
    assert date_to_yday(date(2020, 12, 30)) == 365
    assert date_to_yday(date(2020, 3, 1)) == 61


def test_month_day_counts() -> None:
    assert month_day_count(2020, 2) == 29
    assert month_day_count(2020, 12) == 30
    assert month_day_count(2019, 12) == 31
    assert month_day_count(2019, 2) == 28
    assert sum(month_day_count(2020, m) for m in range(1, 13)) == 365
    assert sum(month_day_count(2019, m) for m in range(1, 13)) == 365


def test_year_dates() -> None:
    days = year_dates(2020)
    assert len(days) == len(set(days)) == 365
    assert days[0] == date(2020, 1, 1)
    assert days[-1] == date(2020, 12, 30)
    assert calendar_info() == {"daysPerYear": 365, "rule": "leap years keep Feb 29 and drop Dec 31"}
