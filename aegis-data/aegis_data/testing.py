"""Shared test fixtures for the catalog port and continuous-futures scenarios.

Importable test support (the ``pandas.testing`` pattern) so aegis-data and the
packages that consume it drive the same fake Catalog instead of copying it:

- ``FakeCatalog`` — a Catalog-backend stand-in: instrument definitions
  plus native bars by identifier, served beneath the real
  ``CatalogBackedDataPort`` (the port itself is never faked — one
  implementation, so the fixtures inherit production behavior).
- ``es_port`` / ``es_port_two_rolls`` / ``early_crossover_es_port`` — canned ES
  scenarios: one liquidity migration, two rolls, and an early crossover.

Bars carry production IBKR daily stamps — ``ts_event`` at the session date's
midnight UTC and ``ts_init`` at the day's last nanosecond (verified against a
live gateway, r8b.2) — so consumers see the event date and the bucket-close
ceiling exactly as they do live.
"""

from __future__ import annotations

from datetime import datetime, time, timezone

import pandas as pd
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import FuturesContract
from nautilus_trader.model.objects import Currency, Price, Quantity

from aegis_data.bar_type import raw_bar_type
from aegis_data.catalog import CatalogBackedDataPort
from aegis_data.storage import Catalog

ES_START = "2024-01-15"
ES_END = "2024-05-31"

_UTC = timezone.utc
_DAY_NS = 86_400_000_000_000
_PRECISION = 2
_CROSSOVER = pd.Timestamp("2024-03-01")


def future(
    instrument_id: str,
    expiry: str,
    *,
    underlying: str = "ES",
    currency: Currency = USD,
    multiplier: float = 1.0,
) -> FuturesContract:
    """A dated futures-contract definition for the fake catalog."""
    iid = InstrumentId.from_str(instrument_id)
    return FuturesContract(
        instrument_id=iid,
        raw_symbol=iid.symbol,
        asset_class=AssetClass.INDEX,
        exchange=iid.venue.value,
        currency=currency,
        price_precision=_PRECISION,
        price_increment=Price(10**-_PRECISION, _PRECISION),
        multiplier=Quantity.from_str(str(multiplier)),
        lot_size=Quantity.from_int(1),
        underlying=underlying,
        activation_ns=0,
        expiration_ns=pd.Timestamp(expiry, tz="UTC").value,
        ts_event=0,
        ts_init=0,
    )


def frame(start: str, end: str, base: float, *, leads_early: bool) -> pd.DataFrame:
    """A business-day OHLCV frame whose volume leads before or after the crossover."""
    idx = pd.bdate_range(start, end)
    close = [base + i for i in range(len(idx))]
    volume = [(1000.0 if (day < _CROSSOVER) == leads_early else 100.0) for day in idx]
    return _ohlcv(idx, close, volume)


def lead_frame(
    start: str, end: str, base: float, lead_lo: str, lead_hi: str
) -> pd.DataFrame:
    """A business-day OHLCV frame whose volume leads inside ``[lead_lo, lead_hi]``."""
    idx = pd.bdate_range(start, end)
    close = [base + i for i in range(len(idx))]
    lo, hi = pd.Timestamp(lead_lo), pd.Timestamp(lead_hi)
    volume = [1000.0 if lo <= day <= hi else 50.0 for day in idx]
    return _ohlcv(idx, close, volume)


def _ohlcv(
    idx: pd.DatetimeIndex, close: list[float], volume: list[float]
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [c - 0.5 for c in close],
            "High": [c + 1 for c in close],
            "Low": [c - 1 for c in close],
            "Close": close,
            "Volume": volume,
        },
        index=idx,
    )


def bars(instrument_id: InstrumentId, ohlcv: pd.DataFrame) -> list[Bar]:
    """Native daily bars for an OHLCV frame, stamped as IBKR serves them:
    ``ts_event`` at the session date's midnight UTC, ``ts_init`` at day end."""
    bar_type = raw_bar_type(instrument_id, "1D")
    out: list[Bar] = []
    for day, row in ohlcv.iterrows():
        ts_event = int(
            datetime.combine(day.date(), time(0, 0), _UTC).timestamp() * 1e9
        )
        out.append(
            Bar(
                bar_type,
                Price.from_str(str(row["Open"])),
                Price.from_str(str(row["High"])),
                Price.from_str(str(row["Low"])),
                Price.from_str(str(row["Close"])),
                Quantity.from_int(int(row["Volume"])),
                ts_event,
                ts_event + _DAY_NS - 1,
            )
        )
    return out


_UNBOUNDED_NS = 2**63 - 1


class _FakeCatalogBackend:
    """A Catalog-backend stand-in: instrument definitions + native bars by identifier."""

    def __init__(
        self,
        instruments: list[FuturesContract],
        bars: dict[str, list[Bar]],
        coverage_horizon: tuple[int, int] | None,
    ) -> None:
        self._instruments = instruments
        self._bars = bars
        self._coverage_horizon = coverage_horizon

    def instruments(
        self,
        instrument_type: type | None = None,
        instrument_ids: list[str] | None = None,
        **_kwargs: object,
    ) -> list[FuturesContract]:
        out = self._instruments
        if instrument_type is not None:
            out = [i for i in out if isinstance(i, instrument_type)]
        if instrument_ids is not None:
            wanted = set(instrument_ids)
            out = [i for i in out if i.id.value in wanted]
        return out

    def query(
        self,
        data_cls: type,
        identifiers: list[str] | None = None,
        start: object = None,
        end: object = None,
        **_kwargs: object,
    ) -> list:
        if data_cls.__name__ == "_CoverageMarker":
            return self._claims(data_cls, identifiers or [])
        if data_cls is not Bar:
            return []  # no non-bar data stored; distributions read as honestly empty
        lo, hi = pd.Timestamp(start).value, pd.Timestamp(end).value
        return [
            bar
            for ident in (identifiers or [])
            for bar in self._bars.get(ident, [])
            if lo <= bar.ts_event <= hi
        ]

    def _claims(self, marker_cls: type, identifiers: list[str]) -> list:
        """Whole-timeline claims for the record kinds that still keep them.

        Bars answer coverage from their file extents now, so nothing here
        narrows a claim: a fixture not exercising sparse-record coverage must
        never provoke a gap. One claim per identifier, each naming the dataset
        it belongs to rather than a fixed kind, so Custom Data subjects are not
        described as Distributions.
        """
        return [
            marker_cls(
                0,
                0,
                instrument_id=InstrumentId.from_str("COVERAGE.AEGIS"),
                record_type=identifier.split("-", 1)[0],
                start_ns=0,
                end_ns=_UNBOUNDED_NS,
            )
            for identifier in identifiers
        ]

    def _covered(self, data_cls: type) -> tuple[int, int]:
        """The window this fixture's Bar files have been checked over.

        The horizon narrows Bar coverage only — that is the seam these
        scenarios exercise. Every other record type, and every type at all when
        no horizon is declared, is covered end to end.
        """
        if self._coverage_horizon is None or data_cls is not Bar:
            return (0, _UNBOUNDED_NS)
        return self._coverage_horizon

    def get_missing_intervals_for_request(
        self,
        start: int,
        end: int,
        data_cls: type,
        identifier: str | None = None,
    ) -> list:
        """The fixture's coverage horizon, said the way the Catalog reads it.

        Coverage is the extents naming a dataset's files, so a fixture
        modelling a warmed window says so by reporting nothing missing inside
        it, and a fixture modelling an unwarmed one reports the whole request.
        """
        covered_start, covered_end = self._covered(data_cls)
        gaps = []
        if start < covered_start:
            gaps.append((start, min(end, covered_start - 1)))
        if end > covered_end:
            gaps.append((max(start, covered_end + 1), end))
        return gaps

    def get_intervals(self, *_args: object, **_kwargs: object) -> list:
        # No marker intervals stored.
        return []

    def write_data(
        self,
        data: list[object],
        start: int | None = None,
        end: int | None = None,
        data_cls: type | None = None,
        identifier: str | None = None,
        **_kwargs: object,
    ) -> None:
        raise NotImplementedError("FakeCatalog is a read-only fixture")

    def delete_data_range(
        self,
        data_cls: type,
        identifier: str | None = None,
        start: object = None,
        end: object = None,
    ) -> None:
        raise NotImplementedError("FakeCatalog is a read-only fixture")

    def reset_data_file_names(
        self,
        data_cls: type,
        identifier: str | None = None,
    ) -> None:
        raise NotImplementedError("FakeCatalog is a read-only fixture")

    def consolidate_data(
        self,
        data_cls: type,
        identifier: str | None = None,
        start: object = None,
        end: object = None,
        ensure_contiguous_files: bool = True,
        deduplicate: bool = False,
    ) -> None:
        raise NotImplementedError("FakeCatalog is a read-only fixture")


class FakeCatalog(Catalog):
    """Typed in-memory Catalog used by deterministic port tests."""

    def __init__(
        self,
        instruments: list[FuturesContract],
        bars: dict[str, list[Bar]],
        *,
        coverage_horizon: tuple[int, int] | None = None,
    ) -> None:
        super().__init__(_FakeCatalogBackend(instruments, bars, coverage_horizon))


def es_port(
    *,
    leg_currencies: dict[str, str] | None = None,
    leg_multipliers: dict[str, float] | None = None,
) -> tuple[CatalogBackedDataPort, dict[InstrumentId, list[Bar]]]:
    """ES with two legs and one liquidity migration at the crossover.

    ``leg_currencies`` overrides individual legs' quote currencies (by
    instrument-id string) so currency-derivation tests can stage disagreement.
    ``leg_multipliers`` does the same for contract-multiplier consistency tests.
    """
    currencies = leg_currencies or {}
    multipliers = leg_multipliers or {}

    def _currency(instrument_id: str) -> Currency:
        return Currency.from_str(currencies.get(instrument_id, "USD"))

    esh4 = InstrumentId.from_str("ESH4.XCME")
    esm4 = InstrumentId.from_str("ESM4.XCME")
    frames = {
        esh4: frame(ES_START, "2024-03-15", 100.0, leads_early=True),
        esm4: frame(ES_START, "2024-04-30", 200.0, leads_early=False),
    }
    return _port(
        frames,
        [
            future(
                "ESH4.XCME",
                "2024-03-15",
                currency=_currency("ESH4.XCME"),
                multiplier=multipliers.get("ESH4.XCME", 1.0),
            ),
            future(
                "ESM4.XCME",
                "2024-06-21",
                currency=_currency("ESM4.XCME"),
                multiplier=multipliers.get("ESM4.XCME", 1.0),
            ),
        ],
        coverage_end=ES_END,
    )


def es_port_two_rolls() -> tuple[CatalogBackedDataPort, dict[InstrumentId, list[Bar]]]:
    """ES with three legs and two liquidity-led rolls."""
    esh4 = InstrumentId.from_str("ESH4.XCME")
    esm4 = InstrumentId.from_str("ESM4.XCME")
    esu4 = InstrumentId.from_str("ESU4.XCME")
    frames = {
        esh4: lead_frame(ES_START, "2024-03-15", 100.0, ES_START, "2024-02-29"),
        esm4: lead_frame(ES_START, "2024-06-21", 200.0, "2024-03-01", "2024-06-06"),
        esu4: lead_frame("2024-03-01", "2024-09-19", 300.0, "2024-06-07", "2024-09-19"),
    }
    return _port(
        frames,
        [
            future("ESH4.XCME", "2024-03-15"),
            future("ESM4.XCME", "2024-06-21"),
            future("ESU4.XCME", "2024-09-20"),
        ],
    )


def early_crossover_es_port() -> CatalogBackedDataPort:
    """ES with three legs where liquidity crosses to the back leg early."""
    esh4 = InstrumentId.from_str("ESH4.XCME")
    esm4 = InstrumentId.from_str("ESM4.XCME")
    esu4 = InstrumentId.from_str("ESU4.XCME")
    frames = {
        esh4: lead_frame(ES_START, "2024-03-15", 100.0, ES_START, "2024-02-29"),
        esm4: lead_frame(ES_START, "2024-06-21", 200.0, "2024-03-01", "2024-04-14"),
        esu4: lead_frame("2024-03-01", "2024-09-19", 300.0, "2024-04-15", "2024-09-19"),
    }
    port, _native = _port(
        frames,
        [
            future("ESH4.XCME", "2024-03-15"),
            future("ESM4.XCME", "2024-06-21"),
            future("ESU4.XCME", "2024-09-20"),
        ],
    )
    return port


def _port(
    frames: dict[InstrumentId, pd.DataFrame],
    instruments: list[FuturesContract],
    *,
    coverage_end: str | None = None,
) -> tuple[CatalogBackedDataPort, dict[InstrumentId, list[Bar]]]:
    native = {iid: bars(iid, ohlcv) for iid, ohlcv in frames.items()}
    catalog = FakeCatalog(
        instruments=instruments,
        bars={str(raw_bar_type(iid, "1D")): native[iid] for iid in native},
        coverage_horizon=(
            pd.Timestamp(min(frame.index.min() for frame in frames.values()), tz="UTC").value,
            pd.Timestamp(
                coverage_end
                or max(frame.index.max() for frame in frames.values()),
                tz="UTC",
            ).value,
        ),
    )
    return CatalogBackedDataPort(catalog), native


__all__ = [
    "ES_END",
    "ES_START",
    "FakeCatalog",
    "bars",
    "early_crossover_es_port",
    "es_port",
    "es_port_two_rolls",
    "frame",
    "future",
    "lead_frame",
]
