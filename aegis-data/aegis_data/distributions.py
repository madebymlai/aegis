from collections.abc import Sequence
from itertools import groupby
from typing import Any

import pandas as pd
from nautilus_trader.core.data import Data
from nautilus_trader.model.custom import customdataclass
from nautilus_trader.model.identifiers import InstrumentId


_DEFAULT_MIN_CASH_AMOUNT = 0.005
_NANOS_PER_DAY = 86_400_000_000_000


@customdataclass
class Distribution(Data):
    """A per-share listed-ETF cash distribution on its ex-date."""

    instrument_id: InstrumentId = InstrumentId.from_str("SPY.ARCA")
    amount: float = 0.0
    currency: str = "USD"

    def __post_init__(self) -> None:
        if self.amount <= 0.0:
            raise ValueError("distribution amount must be positive")
        self.currency = self.currency.upper()

    @classmethod
    def from_ex_date(
        cls,
        instrument_id: InstrumentId,
        ex_date: str | pd.Timestamp,
        *,
        amount: float,
        currency: str,
    ) -> "Distribution":
        ts_event = _ex_date_ns(ex_date)
        return cls(
            ts_event,
            ts_event,
            instrument_id=instrument_id,
            amount=float(amount),
            currency=currency.upper(),
        )

    @property
    def ex_date(self) -> pd.Timestamp:
        return pd.Timestamp(self.ts_event, tz="UTC").normalize()

    @classmethod
    def schema(cls) -> Any:
        return cls._schema


def recover_distributions_from_adjusted_last(
    *,
    instrument_id: InstrumentId,
    trades: pd.Series,
    adjusted_last: pd.Series,
    currency: str,
    min_cash_amount: float = _DEFAULT_MIN_CASH_AMOUNT,
) -> list[Distribution]:
    """Recover dividend cash events from the ``ADJUSTED_LAST / TRADES`` ratio.

    The ratio's relative step is converted back into per-share cash using the
    previous trade close.  A half-cent cash floor rejects penny-rounding noise on
    lower-priced ETFs while leaving real distributions intact.
    """
    trade_closes = _positive_series(trades)
    adjusted_closes = _positive_series(adjusted_last)
    common = trade_closes.index.intersection(adjusted_closes.index).sort_values()
    events: list[Distribution] = []
    for prev, cur in zip(common, common[1:], strict=False):
        trade_prev = float(trade_closes.loc[prev])
        factor_prev = float(adjusted_closes.loc[prev]) / trade_prev
        factor_cur = float(adjusted_closes.loc[cur]) / float(trade_closes.loc[cur])
        if factor_prev <= 0.0 or factor_cur <= 0.0:
            continue
        amount = trade_prev * (1.0 - factor_prev / factor_cur)
        if amount < min_cash_amount:
            continue
        events.append(
            Distribution.from_ex_date(
                instrument_id,
                cur,
                amount=amount,
                currency=currency,
            )
        )
    return events


def request_distribution_data(
    provider: Any,
    instrument_id: InstrumentId,
    *,
    trades: pd.Series,
    start: pd.Timestamp,
    end: pd.Timestamp,
    currency: str,
    primary_exchange: str | None = None,
) -> tuple[Distribution, ...]:
    """Fetch ``ADJUSTED_LAST`` and decode listed-ETF distributions.

    The traded ``TRADES`` close series is supplied by the caller from the normal
    catalog/bar path; only the adjusted-last fetch crosses the raw-IBKR seam.
    """
    adjusted_last = provider.request_adjusted_last(
        instrument_id=instrument_id,
        start=start,
        end=end,
        primary_exchange=primary_exchange,
        currency=currency,
    )
    return tuple(
        recover_distributions_from_adjusted_last(
            instrument_id=instrument_id,
            trades=trades,
            adjusted_last=adjusted_last,
            currency=currency,
        )
    )


def query_distribution_data(
    catalog: Any,
    instrument_ids: Sequence[InstrumentId],
    *,
    start: str | int | pd.Timestamp | None = None,
    end: str | int | pd.Timestamp | None = None,
) -> tuple[Distribution, ...]:
    """Read stored distributions for the requested instruments and window."""
    events: list[Distribution] = []
    for instrument_id in instrument_ids:
        queried = catalog.query(
            Distribution,
            identifiers=[instrument_id.value],
            start=start,
            end=end,
        )
        events.extend(_as_distribution(item) for item in queried)
    return tuple(sorted(events, key=lambda item: (item.instrument_id.value, item.ts_event)))


def write_distribution_data(
    catalog: Any,
    distributions: Sequence[Distribution],
    *,
    force_start: str | int | pd.Timestamp | None = None,
    force_end: str | int | pd.Timestamp | None = None,
) -> int:
    """Write only distributions beyond each instrument's stored ex-date frontier.

    Passing a bounded force window deletes that range first, then writes the given
    events in the window.  The normal path is append-only-new so repeating a decode
    over the same historical window is idempotent without relying on byte-dedup.
    """
    grouped = sorted(distributions, key=lambda item: (item.instrument_id.value, item.ts_event))
    written = 0
    for instrument_value, group in groupby(grouped, key=lambda item: item.instrument_id.value):
        items = list(group)
        if force_start is not None or force_end is not None:
            selected = _force_window_items(items, force_start=force_start, force_end=force_end)
            catalog.delete_data_range(
                Distribution,
                identifier=instrument_value,
                start=force_start,
                end=force_end,
            )
        else:
            frontier = _stored_frontier(catalog, instrument_value)
            selected = [item for item in items if item.ts_event > frontier]
        if not selected:
            continue
        catalog.write_data(
            selected,
            data_cls=Distribution,
            identifier=instrument_value,
            start=min(item.ts_event for item in selected),
            end=max(item.ts_event for item in selected) + _NANOS_PER_DAY,
        )
        written += len(selected)
    return written


def _stored_frontier(catalog: Any, instrument_value: str) -> int:
    stored = [
        _as_distribution(item)
        for item in catalog.query(Distribution, identifiers=[instrument_value])
    ]
    if not stored:
        return -1
    return max(item.ts_event for item in stored)


def _as_distribution(item: Any) -> Distribution:
    return item.data if hasattr(item, "data") else item


def _force_window_items(
    items: Sequence[Distribution],
    *,
    force_start: str | int | pd.Timestamp | None,
    force_end: str | int | pd.Timestamp | None,
) -> list[Distribution]:
    start_ns = _optional_ns(force_start)
    end_ns = _optional_ns(force_end)
    selected: list[Distribution] = []
    for item in items:
        if start_ns is not None and item.ts_event < start_ns:
            continue
        if end_ns is not None and item.ts_event >= end_ns:
            continue
        selected.append(item)
    return selected


def _positive_series(values: pd.Series) -> pd.Series:
    series = pd.to_numeric(values, errors="coerce").dropna()
    positive = series[series > 0.0]
    if isinstance(positive.index, pd.DatetimeIndex):
        positive = positive.copy()
        if positive.index.tz is None:
            positive.index = positive.index.tz_localize("UTC")
        else:
            positive.index = positive.index.tz_convert("UTC")
        positive = positive.sort_index()
        positive = positive[~positive.index.duplicated(keep="last")]
    return positive


def _ex_date_ns(value: str | pd.Timestamp) -> int:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.normalize().value


def _optional_ns(value: str | int | pd.Timestamp | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    return _ex_date_ns(pd.Timestamp(value))


__all__ = [
    "Distribution",
    "query_distribution_data",
    "recover_distributions_from_adjusted_last",
    "request_distribution_data",
    "write_distribution_data",
]
