# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Monthly and annual reductions of Daymet daily values (DESIGN.md §3.1, §4.5, D4, D10).

Rules:
* reductions run over the Daymet days present in the period (365-day calendar, so a
  leap-year December has 30 days); sums are never rescaled to a nominal month length;
* a missing or non-finite daily value makes the period ``complete=False`` and its value
  ``None`` — nothing is imputed;
* inputs are the unrounded upstream floats; outputs are rounded to 3 decimals.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from daymet_mcp.daymet.calendar import month_day_count
from daymet_mcp.daymet.catalog import AggSpec, Period

AGG_DECIMALS = 3


@dataclass(frozen=True)
class PeriodInfo:
    label: str
    year: int
    month: int | None
    day_count: int
    complete: bool
    first_date: date
    last_date: date


def _finite(v: float | None) -> bool:
    return v is not None and math.isfinite(v)


def period_key(day: date, period: Period) -> tuple[int, int | None]:
    return (day.year, day.month) if period == "monthly" else (day.year, None)


def group_indices(
    dates: Sequence[date], period: Period
) -> list[tuple[tuple[int, int | None], list[int]]]:
    """Consecutive index groups per period, in date order."""
    groups: dict[tuple[int, int | None], list[int]] = {}
    for i, d in enumerate(dates):
        groups.setdefault(period_key(d, period), []).append(i)
    return sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0))


def reduce_values(
    spec: AggSpec, idx: Sequence[int], series: Mapping[str, Sequence[float | None]]
) -> float | None:
    """Apply ``spec`` to the days ``idx``; ``None`` if any needed daily value is missing."""
    values = series[spec.variable]
    picked = [values[i] for i in idx]
    if not picked or not all(_finite(v) for v in picked):
        return None
    vals = [float(v) for v in picked if v is not None]
    if spec.method == "sum":
        out = math.fsum(vals)
    elif spec.method == "mean":
        out = math.fsum(vals) / len(vals)
    elif spec.method == "last":
        out = vals[-1]
    else:  # total: srad (W/m2, daylight average) * dayl (s) -> J/m2; /1e6 -> MJ/m2
        dayl = [series["dayl"][i] for i in idx]
        if not all(_finite(v) for v in dayl):
            return None
        out = (
            math.fsum(s * float(d) for s, d in zip(vals, dayl, strict=True) if d is not None) / 1e6
        )
    return round(out, AGG_DECIMALS)


def summarise(
    dates: Sequence[date],
    series: Mapping[str, Sequence[float | None]],
    specs: Sequence[AggSpec],
    period: Period,
) -> tuple[list[PeriodInfo], dict[str, list[float | None]]]:
    """Reduce aligned daily ``series`` (keyed by variable) to periods.

    ``dates`` must cover whole Daymet years in order. Returns the period descriptions
    and, per variable, one value per period.
    """
    periods: list[PeriodInfo] = []
    out: dict[str, list[float | None]] = {s.variable: [] for s in specs}
    for (year, month), idx in group_indices(dates, period):
        expected = month_day_count(year, month) if month is not None else 365
        row_values = {s.variable: reduce_values(s, idx, series) for s in specs}
        complete = len(idx) == expected and all(v is not None for v in row_values.values())
        label = f"{year:04d}-{month:02d}" if month is not None else f"{year:04d}"
        periods.append(
            PeriodInfo(label, year, month, len(idx), complete, dates[idx[0]], dates[idx[-1]])
        )
        for var, value in row_values.items():
            out[var].append(value)
    return periods, out
