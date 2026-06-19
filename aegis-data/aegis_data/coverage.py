"""Ensure Coverage: fill Historical Store gaps through a block-level Gap-Fill Provider.

Ensure Coverage is the write-capable counterpart to the provider-free Store Read.
It owns the asset-class Pull dispatch: a caller declares *which* refs to cover and
*which* Gap-Fill Provider to use, and this module decides *which* Pull runs for each
``InstrumentRef``. Listed refs gap-fill through yfinance; continuous futures gap-fill
through Databento. Provider Locators (e.g. yfinance tickers) are fetch inputs the
caller supplies; they never become Historical Store identity and never decide the
Pull. After this call a Store Read sees covered bars or fails closed.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path

from aegis_runtime import FuturesRef, InstrumentRef, ListedRef

from aegis_data.databento_pull import pull_databento_futures_bars
from aegis_data.store import NativeBarsRequest
from aegis_data.yfinance import YFinanceLocator, pull_yfinance_native_bars


class GapFillProvider(StrEnum):
    """Block-level provider that fills Historical Store gaps for a Pull."""

    YFINANCE = "yfinance"
    DATABENTO = "databento"


def ensure_native_bar_coverage(
    request: NativeBarsRequest,
    *,
    provider: GapFillProvider,
    locators: Mapping[InstrumentRef, str],
    store_dir: Path | None = None,
) -> None:
    """Ensure every requested ref has Covered History, pulling only missing gaps.

    Each ``InstrumentRef`` is dispatched to the Pull that owns its asset class for
    the given ``provider``; ``locators`` supplies the provider Locator per ref (used
    by providers that locate by ticker, ignored by providers that locate from the
    ref). Unsupported ``(ref, provider)`` pairs fail closed rather than silently
    skipping a Pull.
    """
    for ref in request.refs:
        _ensure_one(
            _single_ref_request(request, ref),
            provider=provider,
            locator=locators.get(ref),
            store_dir=store_dir,
        )


def _ensure_one(
    request: NativeBarsRequest,
    *,
    provider: GapFillProvider,
    locator: str | None,
    store_dir: Path | None,
) -> None:
    ref = request.refs[0]
    if isinstance(ref, ListedRef) and provider is GapFillProvider.YFINANCE:
        pull_yfinance_native_bars(
            request, _yfinance_locator(ref, locator), store_dir=store_dir
        )
        return
    if isinstance(ref, FuturesRef) and provider is GapFillProvider.DATABENTO:
        pull_databento_futures_bars(request, store_dir=store_dir)
        return
    raise ValueError(f"unsupported store gap-fill provider {provider.value!r} for {ref!r}")


def _yfinance_locator(ref: ListedRef, locator: str | None) -> YFinanceLocator:
    if locator is None:
        raise ValueError(f"yfinance gap-fill requires a provider locator for {ref!r}")
    return YFinanceLocator(locator)


def _single_ref_request(request: NativeBarsRequest, ref: InstrumentRef) -> NativeBarsRequest:
    return NativeBarsRequest(
        refs=(ref,),
        arrays=request.arrays,
        timeframe=request.timeframe,
        start=request.start,
        end=request.end,
        calendar=request.calendar,
        listed_adjustment=request.listed_adjustment,
    )


__all__ = ["GapFillProvider", "ensure_native_bar_coverage"]
