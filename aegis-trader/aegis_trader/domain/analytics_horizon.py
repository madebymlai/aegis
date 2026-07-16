"""The Book's derived analytics horizon (aegis-rd-cy7l).

One value owns how observation timestamps bucket into return rows and how
many rows a year holds.  It is derived deterministically from the roster's
declared Sleeve cadences — never from operator config, and never from data
(callback counts, observed timestamp gaps, realized frequencies).  The
annualization count is an internal convention keyed by the bucket width; the
table below is its sole owner, deliberately module-private so no call site
can carry a count somewhere derivation didn't put it.

Bucketing is epoch-floor for every width, with one convention-aware rule:
under the weekday convention (daily buckets, 252 rows/yr) Saturday and Sunday
timestamps fold into the following Monday's bucket.  That matches the
exchanges' own trade-date convention — a Globex or FX Sunday-evening session
belongs to Monday — so an intraday futures Sleeve's Sunday spillover joins
Monday's row instead of forming a sixth, variance-diluting weekly row.
Weekly buckets are Thursday-anchored epoch weeks (1970-01-01 was a Thursday)
and never fold: a week contains its weekend by definition.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property

from aegis_data.bar_type import timeframe_to_ns

_NS_PER_DAY = timeframe_to_ns("1D")

# Annualization counts for the weekday-grid asset universe (equities, futures,
# FX, metals, energies).  A 24/7 venue (365) is a different, deferred design;
# widths outside this table have no validated convention and fail closed.
_WEEKDAY_CONVENTION_BY_WIDTH_NS: dict[int, tuple[str, int]] = {
    timeframe_to_ns("1D"): ("1D", 252),
    timeframe_to_ns("1W"): ("1W", 52),
}

_WEEKDAY_PERIODS_PER_YEAR = 252
_SATURDAY = 5  # Monday=0 convention; epoch day zero (1970-01-01) was a Thursday.


class UnsupportedAnalyticsWidthError(ValueError):
    """The roster's bucket width has no validated annualization convention."""


@dataclass(frozen=True)
class AnalyticsHorizon:
    """Bucket width and annualization count for the Book's return rows.

    Consumers receive the horizon explicitly (it is a required parameter
    everywhere); the only production source is :func:`derive_horizon` via the
    assembled Book.
    """

    bucket_timeframe: str
    periods_per_year: int

    def __post_init__(self) -> None:
        timeframe_to_ns(self.bucket_timeframe)  # fails closed on bad spellings
        if self.periods_per_year <= 0:
            raise ValueError(
                f"periods_per_year must be positive, got {self.periods_per_year}"
            )

    @cached_property
    def bucket_width_ns(self) -> int:
        """The bucket width in nanoseconds."""
        return timeframe_to_ns(self.bucket_timeframe)

    def bucket_of(self, timestamp_ns: int) -> int:
        """The bucket index holding *timestamp_ns* — the single bucketing rule.

        Epoch-floor division, plus the weekend fold under the weekday
        convention at daily width (see module docstring).  Never reimplement
        this with a pandas resample: pandas anchors ``1W`` to Sunday, a
        silently different alignment.
        """
        bucket = timestamp_ns // self.bucket_width_ns
        if (
            self.bucket_width_ns == _NS_PER_DAY
            and self.periods_per_year == _WEEKDAY_PERIODS_PER_YEAR
        ):
            day_of_week = (bucket + 3) % 7
            if day_of_week >= _SATURDAY:
                bucket += 7 - day_of_week
        return bucket


def derive_horizon(sleeve_timeframes: Iterable[str]) -> AnalyticsHorizon:
    """The Book's analytics horizon from its declared Sleeve cadences.

    Width is the slowest cadence, floored at one day (sub-daily analytics
    would need per-venue session counts — a calendar dependency this design
    refuses; the estimator's promotion evidence is daily-row calibrated).
    The count comes from the internal weekday-convention table; a width
    without a validated convention fails closed.
    """
    widths = [timeframe_to_ns(timeframe) for timeframe in sleeve_timeframes]
    if not widths:
        raise UnsupportedAnalyticsWidthError(
            "deriving an analytics horizon needs at least one Sleeve cadence"
        )
    width = max(max(widths), _NS_PER_DAY)
    convention = _WEEKDAY_CONVENTION_BY_WIDTH_NS.get(width)
    if convention is None:
        raise UnsupportedAnalyticsWidthError(
            f"no annualization convention for a {max(widths)}ns bucket width; "
            "supported widths are 1D and 1W (aegis-rd-cy7l)"
        )
    bucket_timeframe, periods_per_year = convention
    return AnalyticsHorizon(
        bucket_timeframe=bucket_timeframe, periods_per_year=periods_per_year
    )
