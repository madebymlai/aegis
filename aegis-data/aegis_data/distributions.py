from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
import pandas as pd
from nautilus_trader.core.data import Data
from nautilus_trader.model.custom import customdataclass
from nautilus_trader.model.identifiers import InstrumentId

from aegis_data.storage import Catalog, CatalogKey


_DEFAULT_MIN_CASH_AMOUNT = 0.005
_ADJUSTED_CLOSE_CURRENCY_PARAM = "currency"


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


@customdataclass
class AdjustedClose(Data):
    """One instrument's daily IBKR ``ADJUSTED_LAST`` close."""

    instrument_id: InstrumentId = InstrumentId.from_str("SPY.ARCA")
    close: float = 0.0

    @classmethod
    def from_value(
        cls,
        instrument_id: InstrumentId,
        timestamp: pd.Timestamp,
        close: float,
    ) -> "AdjustedClose":
        ts_event = _ex_date_ns(timestamp)
        return cls(
            ts_event,
            ts_event,
            instrument_id=instrument_id,
            close=float(close),
        )


class InvalidAdjustedCloseCurrencyError(ValueError):
    """Adjusted-close request metadata contains no usable currency."""


@dataclass(frozen=True)
class AdjustedCloseRequestMetadata:
    """Currency qualification carried by an AdjustedClose request."""

    currency: str

    def __post_init__(self) -> None:
        normalized = self.currency.strip().upper()
        if not normalized:
            raise InvalidAdjustedCloseCurrencyError(
                "adjusted-close request currency must not be empty"
            )
        object.__setattr__(self, "currency", normalized)

    def to_params(self) -> dict[str, Any]:
        return {_ADJUSTED_CLOSE_CURRENCY_PARAM: self.currency}

    @classmethod
    def from_params(cls, params: Mapping[str, Any]) -> "AdjustedCloseRequestMetadata":
        return cls(str(params.get(_ADJUSTED_CLOSE_CURRENCY_PARAM, "USD")))


def distribution_records(records: Sequence[Data]) -> tuple[Distribution, ...]:
    """Select the Distribution consumer view from generic typed records."""
    return tuple(record for record in records if isinstance(record, Distribution))


def adjusted_close_records(
    instrument_id: InstrumentId,
    closes: pd.Series,
) -> tuple[AdjustedClose, ...]:
    """Convert a vendor close series to one typed Catalog record per day."""
    values = _positive_series(closes)
    if isinstance(values.index, pd.DatetimeIndex):
        values = values.copy()
        values.index = values.index.normalize()
        values = values[~values.index.duplicated(keep="last")]
    return tuple(
        AdjustedClose.from_value(instrument_id, pd.Timestamp(timestamp), float(close))
        for timestamp, close in values.items()
    )


def adjusted_close_series(records: Sequence[AdjustedClose]) -> pd.Series:
    """Project stored adjusted-close records back to the decode series."""
    if not records:
        return pd.Series(dtype=float)
    return pd.Series(
        [record.close for record in records],
        index=pd.DatetimeIndex(
            [pd.Timestamp(record.ts_event, tz="UTC") for record in records]
        ),
        dtype=float,
    ).sort_index()


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


def query_distribution_data(
    catalog: Catalog,
    instrument_ids: Sequence[InstrumentId],
    *,
    start: str | int | pd.Timestamp | None = None,
    end: str | int | pd.Timestamp | None = None,
) -> tuple[Distribution, ...]:
    """Read stored distributions for the requested instruments and window."""
    events: list[Distribution] = []
    for instrument_id in instrument_ids:
        queried = _force_window_items(
            catalog.read_all(CatalogKey.for_instrument(Distribution, instrument_id)),
            force_start=start,
            force_end=end,
        )
        events.extend(queried)
    return tuple(
        sorted(events, key=lambda item: (item.instrument_id.value, item.ts_event))
    )


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
        if end_ns is not None and item.ts_event > end_ns:
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
    "AdjustedClose",
    "AdjustedCloseRequestMetadata",
    "Distribution",
    "InvalidAdjustedCloseCurrencyError",
    "adjusted_close_records",
    "adjusted_close_series",
    "distribution_records",
    "query_distribution_data",
    "recover_distributions_from_adjusted_last",
]
