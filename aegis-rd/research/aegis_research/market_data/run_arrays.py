"""Prepare the market-data Arrays a Run sweeps — both views, one constructor.

:func:`prepare_run_arrays` is the module's entire public callable surface. It
materialises the signal view (a full Bundle, since Components may declare any
Array) and the P&L view (exactly the two frames the portfolio contract
consumes), applies the one base-currency conversion to both, defines the P&L
view once, subsumes the usability gate, and proves cross-view alignment.
A misaligned or unusable pairing cannot exist as a :class:`RunArrays` value.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from aegis_data.distributions import Distribution
from aegis_runtime import MarketDataBundle
from aegis_runtime.currency import CurrencyConversion

from research.aegis_research.market_data.contracts import MarketDataResult
from research.aegis_research.market_data.panels import (
    canonical_array_panel,
    market_data_bundle,
)


class RunArrayAlignmentError(ValueError):
    """A P&L frame diverges from the signal Close it must align with.

    Every downstream consumer carries both views through one continuous path, so
    any calendar or column divergence would corrupt path returns silently. The two
    series come from one catalog pull; a mismatch is a
    wiring bug and fails loud here — never repair-by-reindex.
    """

    def __init__(
        self,
        array_name: str,
        *,
        signal_rows: int,
        pnl_rows: int,
        first_divergent: tuple[str, str] | None = None,
        last_divergent: tuple[str, str] | None = None,
        missing_columns: tuple[str, ...] = (),
        extra_columns: tuple[str, ...] = (),
    ) -> None:
        self.array_name = array_name
        self.signal_rows = signal_rows
        self.pnl_rows = pnl_rows
        self.first_divergent = first_divergent
        self.last_divergent = last_divergent
        self.missing_columns = missing_columns
        self.extra_columns = extra_columns
        details = [f"signal has {signal_rows} rows, pnl has {pnl_rows}"]
        if first_divergent is not None:
            details.append(
                f"first divergent timestamp: signal {first_divergent[0]} != pnl {first_divergent[1]}"
            )
        if last_divergent is not None and last_divergent != first_divergent:
            details.append(
                f"last divergent timestamp: signal {last_divergent[0]} != pnl {last_divergent[1]}"
            )
        if missing_columns:
            details.append(f"columns missing from pnl: {list(missing_columns)}")
        if extra_columns:
            details.append(f"columns only in pnl: {list(extra_columns)}")
        super().__init__(
            f"P&L array {array_name!r} does not align with the signal Close: " + "; ".join(details)
        )


@dataclass(frozen=True)
class RunArrays:
    """The prepared Arrays a Run sweeps — coherent by construction.

    ``signal`` drives Indicators, Strategy allocation, and Splits;
    ``pnl_close``/``pnl_open`` price the portfolio. On a single-series Run the
    P&L frames are the signal frames themselves (the same objects), so
    downstream code never branches on the view's presence.
    """

    signal: MarketDataBundle  # FX-converted; drives Indicators, Strategy, Splits
    pnl_close: pd.DataFrame  # portfolio pricing view; never None
    pnl_open: pd.DataFrame
    currency_conversion: CurrencyConversion | None  # the one applied to both views
    distributions: tuple[Distribution, ...]


def prepare_run_arrays(data_result: MarketDataResult) -> RunArrays:
    """Materialise, convert, and prove both views from one loaded result.

    Continuous-future adjustment already happened in the load path (the catalog
    adapter materialises each declared root), so only base-currency conversion
    remains before the sweep. A single-currency book carries no conversion and
    passes through untouched; the catalog itself keeps native, account-agnostic
    prices.
    """
    signal = _to_base_currency(data_result.currency_conversion, market_data_bundle(data_result))
    if data_result.pnl_native_data is None:
        pnl_close = signal.array("Close")
        pnl_open = signal.array("Open")
    else:
        # The store already back-adjusted the P&L series; it only needs the same
        # FX conversion the signal view gets, and only the two frames the
        # portfolio contract consumes.
        pnl_view = _to_base_currency(
            data_result.currency_conversion,
            MarketDataBundle(
                {
                    name: canonical_array_panel(data_result.pnl_native_data, name)
                    for name in ("Close", "Open")
                }
            ),
        )
        pnl_close = pnl_view.array("Close")
        pnl_open = pnl_view.array("Open")
    signal_close = signal.array("Close")
    _assert_aligned("Close", signal_close=signal_close, pnl_frame=pnl_close)
    _assert_aligned("Open", signal_close=signal_close, pnl_frame=pnl_open)
    return RunArrays(
        signal=signal,
        pnl_close=pnl_close,
        pnl_open=pnl_open,
        currency_conversion=data_result.currency_conversion,
        distributions=data_result.distributions,
    )


def _to_base_currency(
    conversion: CurrencyConversion | None, bundle: MarketDataBundle
) -> MarketDataBundle:
    if conversion is None:
        return bundle
    return MarketDataBundle(conversion.apply(bundle.arrays))


def _assert_aligned(
    array_name: str, *, signal_close: pd.DataFrame, pnl_frame: pd.DataFrame
) -> None:
    index_aligned = signal_close.index.equals(pnl_frame.index)
    signal_columns = set(signal_close.columns)
    pnl_columns = set(pnl_frame.columns)
    if index_aligned and signal_columns == pnl_columns:
        return
    first_divergent, last_divergent = _divergent_timestamps(signal_close.index, pnl_frame.index)
    raise RunArrayAlignmentError(
        array_name,
        signal_rows=len(signal_close.index),
        pnl_rows=len(pnl_frame.index),
        first_divergent=first_divergent,
        last_divergent=last_divergent,
        missing_columns=tuple(sorted(str(c) for c in signal_columns - pnl_columns)),
        extra_columns=tuple(sorted(str(c) for c in pnl_columns - signal_columns)),
    )


def _divergent_timestamps(
    signal_index: pd.Index, pnl_index: pd.Index
) -> tuple[tuple[str, str] | None, tuple[str, str] | None]:
    """First and last positions where equal-length indices disagree.

    Unequal lengths carry no positional pairing to report — the row counts on
    the error already tell that story.
    """
    if len(signal_index) != len(pnl_index):
        return None, None
    mismatched = signal_index != pnl_index
    positions = [i for i, differs in enumerate(mismatched) if differs]
    if not positions:
        return None, None
    first, last = positions[0], positions[-1]
    return (
        (str(signal_index[first]), str(pnl_index[first])),
        (str(signal_index[last]), str(pnl_index[last])),
    )
