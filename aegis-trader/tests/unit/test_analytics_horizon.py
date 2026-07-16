"""The derived analytics horizon: bucketing authority and roster derivation.

The horizon is derived from declared Sleeve cadences (never from data) and is
the single owner of how observation timestamps group into return rows and how
many rows a year holds (aegis-rd-cy7l).
"""

from __future__ import annotations

import pandas as pd
import pytest

from aegis_trader.domain.analytics_horizon import (
    AnalyticsHorizon,
    UnsupportedAnalyticsWidthError,
    derive_horizon,
)


def _ns(value: str) -> int:
    return int(pd.Timestamp(value, tz="UTC").value)


# ── construction ──────────────────────────────────────────────────────────


def test_horizon_rejects_unparseable_bucket_timeframe() -> None:
    with pytest.raises(ValueError):
        AnalyticsHorizon(bucket_timeframe="fortnight", periods_per_year=26)


def test_horizon_rejects_non_positive_periods() -> None:
    with pytest.raises(ValueError):
        AnalyticsHorizon(bucket_timeframe="1D", periods_per_year=0)


# ── bucket_of: daily golden behavior ─────────────────────────────────────


def test_daily_bucket_is_bit_identical_to_epoch_day_floor_on_weekdays() -> None:
    # Literal epoch-day indices: the same values the pre-cy7l day floor gave.
    horizon = AnalyticsHorizon(bucket_timeframe="1D", periods_per_year=252)

    assert horizon.bucket_of(_ns("2024-01-03 15:30:00")) == 19725  # Wednesday
    assert horizon.bucket_of(_ns("2024-01-05 21:00:00")) == 19727  # Friday close
    assert horizon.bucket_of(_ns("2026-07-16 00:00:00")) == 20650  # Thu midnight


def test_weekend_timestamps_fold_into_the_following_monday() -> None:
    horizon = AnalyticsHorizon(bucket_timeframe="1D", periods_per_year=252)

    saturday = horizon.bucket_of(_ns("2024-01-06 10:00:00"))
    sunday = horizon.bucket_of(_ns("2024-01-07 22:05:00"))

    assert saturday == 19730  # Monday 2024-01-08
    assert sunday == 19730


def test_epoch_weekend_folds_to_first_epoch_monday() -> None:
    # 1970-01-03 was a Saturday, 1970-01-04 a Sunday; both belong to Monday
    # 1970-01-05 — pins the epoch-Thursday day-of-week arithmetic.
    horizon = AnalyticsHorizon(bucket_timeframe="1D", periods_per_year=252)

    assert horizon.bucket_of(_ns("1970-01-03 12:00:00")) == 4  # Monday 1970-01-05
    assert horizon.bucket_of(_ns("1970-01-04 23:00:00")) == 4


def test_weekend_fold_applies_only_to_the_weekday_convention() -> None:
    non_weekday = AnalyticsHorizon(bucket_timeframe="1D", periods_per_year=365)

    assert non_weekday.bucket_of(_ns("2024-01-06 10:00:00")) == 19728  # Saturday


# ── bucket_of: weekly buckets ─────────────────────────────────────────────


def test_weekly_buckets_are_thursday_anchored_epoch_weeks() -> None:
    horizon = AnalyticsHorizon(bucket_timeframe="1W", periods_per_year=52)

    last_of_week_zero = horizon.bucket_of(_ns("1970-01-07 23:00:00"))  # Wednesday
    first_of_week_one = horizon.bucket_of(_ns("1970-01-08 00:00:00"))  # Thursday

    assert last_of_week_zero == 0
    assert first_of_week_one == 1


def test_weekly_buckets_do_not_fold_weekends() -> None:
    horizon = AnalyticsHorizon(bucket_timeframe="1W", periods_per_year=52)

    assert horizon.bucket_of(_ns("2024-01-06 10:00:00")) == 2818  # its own week


def test_consecutive_vendor_weekly_closes_land_in_consecutive_buckets() -> None:
    # Real IBKR-style weekly bar close stamps: consecutive Friday session
    # closes (LSE 16:30 London = 16:30 UTC in winter) must advance the bucket
    # by exactly one — the property the per-Sleeve weekly clock relies on.
    horizon = AnalyticsHorizon(bucket_timeframe="1W", periods_per_year=52)

    assert horizon.bucket_of(_ns("2024-01-05 16:30:00")) == 2818
    assert horizon.bucket_of(_ns("2024-01-12 16:30:00")) == 2819
    assert horizon.bucket_of(_ns("2024-01-19 16:30:00")) == 2820


# ── derive_horizon ────────────────────────────────────────────────────────


def test_all_daily_roster_derives_the_daily_convention() -> None:
    assert derive_horizon(("1D", "1D")) == AnalyticsHorizon("1D", 252)


def test_mixed_intraday_and_daily_roster_derives_daily() -> None:
    assert derive_horizon(("1H", "1D")) == AnalyticsHorizon("1D", 252)


def test_all_intraday_roster_floors_at_daily() -> None:
    assert derive_horizon(("1H",)) == AnalyticsHorizon("1D", 252)


def test_weekly_sleeve_derives_the_weekly_convention() -> None:
    assert derive_horizon(("1W", "1H")) == AnalyticsHorizon("1W", 52)
    assert derive_horizon(("1W",)) == AnalyticsHorizon("1W", 52)


def test_unknown_bucket_width_fails_closed() -> None:
    with pytest.raises(UnsupportedAnalyticsWidthError):
        derive_horizon(("2D",))


def test_empty_roster_fails_closed() -> None:
    with pytest.raises(UnsupportedAnalyticsWidthError):
        derive_horizon(())
