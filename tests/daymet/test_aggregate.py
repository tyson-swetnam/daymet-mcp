# SPDX-FileCopyrightText: 2026 Tyson Lee Swetnam
# SPDX-License-Identifier: MIT
"""Monthly/annual reductions: golden values from the recorded 2020 fixture, computed by an
independent loop, plus properties (annual sum = sum of monthly sums, etc.)."""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from daymet_mcp.daymet.aggregate import summarise
from daymet_mcp.daymet.calendar import year_dates
from daymet_mcp.daymet.catalog import VARIABLES, aggregation_spec
from tests.fixture_router import fixture_json


def _fixture_series() -> tuple[list[date], dict[str, list[float | None]]]:
    body = fixture_json("pixel_dem_centre_2020")
    data = body["data"]
    series: dict[str, list[float | None]] = {
        v: [float(x) for x in data[info.upstream_column]] for v, info in VARIABLES.items()
    }
    return year_dates(2020), series


def test_monthly_prcp_is_sum_with_30_day_leap_december() -> None:
    dates, series = _fixture_series()
    body = fixture_json("pixel_dem_centre_2020")["data"]
    # independent loop: yday -> date via plain datetime arithmetic
    expected: dict[int, float] = {}
    counts: dict[int, int] = {}
    for yday, p in zip(body["yday"], body["prcp (mm/day)"], strict=True):
        d = date(2020, 1, 1) + timedelta(days=int(yday) - 1)
        expected[d.month] = expected.get(d.month, 0.0) + float(p)
        counts[d.month] = counts.get(d.month, 0) + 1
    spec = aggregation_spec("prcp", "monthly")
    periods, values = summarise(dates, series, [spec], "monthly")
    assert [p.label for p in periods] == [f"2020-{m:02d}" for m in range(1, 13)]
    assert [p.day_count for p in periods] == [counts[m] for m in range(1, 13)]
    assert periods[1].day_count == 29 and periods[11].day_count == 30
    assert periods[11].last_date == date(2020, 12, 30)
    assert all(p.complete for p in periods)
    for m in range(1, 13):
        assert values["prcp"][m - 1] == pytest.approx(expected[m], abs=5e-4)
    assert spec.units == "mm/month" and spec.field_label == "prcp_monthly_total_mm"
    total = sum(float(p) for p in body["prcp (mm/day)"])
    assert math.fsum(v for v in values["prcp"] if v is not None) == pytest.approx(total, abs=6e-3)


def test_monthly_means_and_alternatives() -> None:
    dates, series = _fixture_series()
    specs = [
        aggregation_spec("tmax", "monthly"),
        aggregation_spec("swe", "monthly", "last"),
        aggregation_spec("srad", "monthly", "total"),
        aggregation_spec("dayl", "monthly"),
    ]
    periods, values = summarise(dates, series, specs, "monthly")
    jan = [i for i, d in enumerate(dates) if d.month == 1]
    tmax = series["tmax"]
    srad, dayl, swe = series["srad"], series["dayl"], series["swe"]
    assert values["tmax"][0] == pytest.approx(sum(tmax[i] or 0 for i in jan) / 31, abs=5e-4)
    assert values["swe"][0] == pytest.approx(swe[jan[-1]] or 0, abs=5e-4)
    assert values["srad"][0] == pytest.approx(
        sum((srad[i] or 0) * (dayl[i] or 0) for i in jan) / 1e6, abs=5e-4
    )
    assert values["dayl"][0] == pytest.approx(sum(dayl[i] or 0 for i in jan) / 31, abs=5e-4)
    assert len(periods) == 12


def test_annual_and_labels() -> None:
    dates, series = _fixture_series()
    spec = aggregation_spec("prcp", "annual")
    periods, values = summarise(dates, series, [spec], "annual")
    assert [p.label for p in periods] == ["2020"]
    assert values["prcp"][0] is not None and values["prcp"][0] > 0
    assert periods[0].day_count == 365 and periods[0].complete
    assert spec.units == "mm/year" and spec.field_label == "prcp_annual_total_mm"
    assert aggregation_spec("vp", "annual").field_label == "vp_annual_mean_Pa"
    assert aggregation_spec("srad", "monthly").field_label == "srad_monthly_mean_W_m2"
    assert aggregation_spec("srad", "monthly", "total").field_label == "srad_monthly_total_MJ_m2"
    assert aggregation_spec("swe", "monthly", "last").field_label == "swe_monthly_last_kg_m2"
    assert aggregation_spec("dayl", "monthly").field_label == "dayl_monthly_mean_s"
    assert aggregation_spec("tmax", "monthly").field_label == "tmax_monthly_mean_degC"


def test_disallowed_alternative() -> None:
    with pytest.raises(ValueError, match="cannot be aggregated"):
        aggregation_spec("prcp", "monthly", "mean")


def test_missing_value_makes_period_incomplete() -> None:
    dates, series = _fixture_series()
    series["prcp"][40] = None  # a February day
    periods, values = summarise(dates, series, [aggregation_spec("prcp", "monthly")], "monthly")
    assert values["prcp"][1] is None and not periods[1].complete
    assert values["prcp"][0] is not None and periods[0].complete


@settings(max_examples=40, deadline=None)
@given(st.lists(st.floats(min_value=0, max_value=200, allow_nan=False), min_size=365, max_size=365))
def test_properties(daily: list[float]) -> None:
    dates = year_dates(2020)
    series: dict[str, list[float | None]] = {"prcp": list(daily), "tmax": list(daily)}
    _, monthly = summarise(
        dates,
        series,
        [aggregation_spec("prcp", "monthly"), aggregation_spec("tmax", "monthly")],
        "monthly",
    )
    periods, annual = summarise(
        dates,
        series,
        [aggregation_spec("prcp", "annual"), aggregation_spec("tmax", "annual")],
        "annual",
    )
    del periods
    msum = math.fsum(v for v in monthly["prcp"] if v is not None)
    assert annual["prcp"][0] == pytest.approx(msum, abs=12 * 5e-4 + 1e-9)
    counts = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 30]
    weighted = math.fsum((v or 0) * n for v, n in zip(monthly["tmax"], counts, strict=True)) / 365
    assert annual["tmax"][0] == pytest.approx(weighted, abs=1e-3)
