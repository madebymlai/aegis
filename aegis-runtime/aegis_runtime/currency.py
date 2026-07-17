"""Non-base → base currency conversion as a per-consumer view.

The catalog stores native (account-agnostic) prices; a book that quotes its P&L
in a base currency converts on read. :class:`CurrencyConversion` carries one
``native → base`` FX rate series per instrument (``1.0`` for a base-currency leg)
and applies it to price arrays by aligning each rate onto the bar index and
multiplying. A share count (``Volume``) is never a price, so it passes through
unscaled.

The ``native → base`` orientation mirrors Nautilus' ``Cache.get_mark_xrate``
(native, base): the trader's engine converts a foreign position's value the same
way, and a currency parity test pins this view to it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument

# Currency-denominated arrays the conversion scales; a share count (Volume) is not
# a price and must pass through unscaled.
_PRICE_ARRAYS = frozenset({"Open", "High", "Low", "Close"})


class MissingFxPairError(ValueError):
    """A non-base quote currency has no matching ``exchange:`` FX pair to convert it."""


class FxRateCoverageError(ValueError):
    """An FX rate series does not cover every bar it must convert."""


class MissingInstrumentDefinitionError(ValueError):
    """A tradeable or exchange id has no resolved catalog instrument definition."""


def _matched_tz(source: pd.DatetimeIndex, target: pd.Index) -> pd.DatetimeIndex:
    """Coerce *source* to *target*'s tz-awareness so the two indices compare.

    Both denote the same UTC bar instants; dropping/adding the UTC zone keeps the
    calendar, it just makes the dtypes comparable for ``reindex``.
    """
    target_tz = getattr(target, "tz", None)
    source_tz = source.tz
    if source_tz is None and target_tz is not None:
        return source.tz_localize(target_tz)
    if source_tz is not None and target_tz is None:
        return source.tz_localize(None)
    if source_tz is not None and target_tz is not None and source_tz != target_tz:
        return source.tz_convert(target_tz)
    return source


@dataclass(frozen=True)
class CurrencyConversion:
    """A per-consumer view converting native-priced arrays to the book's base currency.

    ``rate_by_instrument`` holds a ``native → base`` rate series only for the legs
    that need converting; a base-currency leg is absent and passes through
    unchanged. Completeness for non-base legs is the builder's contract (a non-base
    quote currency with no matching FX pair fails loud there, not here).

    ``currency_by_instrument_id`` is each tradeable leg's quote currency as derived
    from its resolved ``Instrument`` — the foreign-leg detection the fee surcharge
    reads, never a configured field.
    """

    rate_by_instrument: Mapping[InstrumentId, pd.Series]
    currency_by_instrument_id: Mapping[InstrumentId, str] = field(default_factory=dict)

    def apply(self, arrays: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        """Convert every price array to base currency; pass non-price arrays through."""
        return {name: self._convert(name, frame) for name, frame in arrays.items()}

    def rate_for(self, instrument_id: InstrumentId, index: pd.Index) -> pd.Series:
        """Native → base FX rate for one instrument over *index*.

        Base-currency legs are absent from ``rate_by_instrument`` and therefore
        return an identity rate.  Non-base legs reuse the same aligned, coverage-
        checked series the price conversion uses.
        """
        if instrument_id not in self.rate_by_instrument:
            return pd.Series(1.0, index=index)
        return self._aligned_rate(instrument_id, index)

    def _convert(self, name: str, frame: pd.DataFrame) -> pd.DataFrame:
        if name not in _PRICE_ARRAYS:
            return frame
        convertible = [column for column in frame.columns if column in self.rate_by_instrument]
        if not convertible:
            return frame
        rates = pd.DataFrame(1.0, index=frame.index, columns=frame.columns)
        for column in convertible:
            rates[column] = self._aligned_rate(column, frame.index)
        converted = frame.mul(rates)
        converted.columns.name = frame.columns.name
        return converted

    def _aligned_rate(self, instrument_id: InstrumentId, index: pd.Index) -> pd.Series:
        series = self.rate_by_instrument[instrument_id]
        # The FX series and the price bars come from different reads (the catalog FX
        # frame is tz-aware UTC; vbt panels are tz-naive), so reconcile tz before
        # reindexing — a mismatch is a dtype error, not a silent misalignment.
        series = pd.Series(series.to_numpy(), index=_matched_tz(series.index, index))
        aligned = series.reindex(index, method="ffill")
        if aligned.isna().any():
            raise FxRateCoverageError(
                f"FX conversion rate for {instrument_id.value!r} does not cover every "
                "bar: the rate series starts after the first bar it must convert"
            )
        return aligned


def build_currency_conversion(
    *,
    instruments: Mapping[InstrumentId, Instrument],
    fx_pairs: Mapping[InstrumentId, Instrument],
    fx_close: Mapping[InstrumentId, pd.Series],
    base_currency: str,
) -> CurrencyConversion:
    """Derive each tradeable leg's ``native → base`` FX rate from resolved instruments.

    Each leg's currency is read from its resolved ``Instrument.quote_currency`` (never
    configured); the currency-code composition itself lives in
    :func:`build_currency_conversion_from_codes` — the trader builds the same view
    from its cache-backed ports without materialising ``Instrument`` objects.
    """
    return build_currency_conversion_from_codes(
        currency_by_instrument_id={
            instrument_id: instrument.quote_currency.code
            for instrument_id, instrument in instruments.items()
        },
        pair_currencies={
            pair_id: (pair.base_currency.code, pair.quote_currency.code)
            for pair_id, pair in fx_pairs.items()
        },
        fx_close=fx_close,
        base_currency=base_currency,
    )


def build_currency_conversion_from_codes(
    *,
    currency_by_instrument_id: Mapping[InstrumentId, str],
    pair_currencies: Mapping[InstrumentId, tuple[str, str]],
    fx_close: Mapping[InstrumentId, pd.Series],
    base_currency: str,
) -> CurrencyConversion:
    """Derive each tradeable leg's ``native → base`` FX rate from currency codes.

    Each declared FX pair contributes both directions of its rate from its
    ``(base, quote)`` codes: a pair ``X/Y`` priced ``p`` (Y per 1 X) gives
    ``X→Y = p`` and ``Y→X = 1/p`` — the same auto-inverse Nautilus' mark xrate
    uses. A non-base leg with no matching pair fails loud
    (:class:`MissingFxPairError`); a base-currency leg needs no conversion and
    is omitted.
    """
    base = base_currency.upper()
    rates: dict[tuple[str, str], pd.Series] = {}
    for pair_id, (left_code, right_code) in pair_currencies.items():
        price = fx_close[pair_id]
        left = left_code.upper()
        right = right_code.upper()
        rates[(left, right)] = price
        rates[(right, left)] = 1.0 / price

    rate_by_instrument: dict[InstrumentId, pd.Series] = {}
    normalized_currency_by_instrument_id: dict[InstrumentId, str] = {}
    for instrument_id, currency in currency_by_instrument_id.items():
        quote = currency.upper()
        normalized_currency_by_instrument_id[instrument_id] = quote
        if quote == base:
            continue
        try:
            rate_by_instrument[instrument_id] = rates[(quote, base)]
        except KeyError:
            raise MissingFxPairError(
                f"instrument {instrument_id.value!r} is quoted in {quote} but the book's "
                f"base currency is {base} and no exchange: FX pair connects {quote} to "
                f"{base}; declare the {quote}/{base} (or {base}/{quote}) pair under data.exchange"
            ) from None
    return CurrencyConversion(
        rate_by_instrument=rate_by_instrument,
        currency_by_instrument_id=normalized_currency_by_instrument_id,
    )
