"""Resolve a futures root to a back-adjusted continuous OHLCV panel.

Composes the store-cached Nautilus databento port fetch, the contract-chain
assembly, and the back-adjustment transform.  This is the package's deep public
entry point for consumers (Aegis RD's pipeline, Aegis Trader): an omitted
``source:`` means "read the store, fetch-on-miss via the port, then back-adjust".
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from aegis_data.back_adjust import back_adjust_chain
from aegis_data.chain import ContractCalendar, ContractFetcher, fetch_contract_chain
from aegis_data.databento_port import databento_contract_calendar, databento_port_fetcher
from aegis_data.raw_leg_cache import LegPorts, raw_leg_ports


def databento_source(
    dataset: str, *, store_dir=None, client=None
) -> ContractFetcher:
    """A raw-leg-cache-backed per-contract fetcher over the databento port."""
    return databento_leg_ports(dataset, store_dir=store_dir, client=client).fetch


def databento_leg_ports(
    dataset: str, *, timeframe: str = "1D", store_dir=None, client=None
) -> LegPorts:
    """Fetch/probe ports over the databento port, bound to the same raw-leg cache."""
    return raw_leg_ports(
        dataset=dataset,
        timeframe=timeframe,
        fetch=databento_port_fetcher(dataset, client=client),
        store_dir=store_dir,
    )


def continuous_panel(
    root: str,
    start: date,
    end: date,
    *,
    ports: LegPorts,
    list_contracts: ContractCalendar,
    method: str = "ratio",
    bar_cadence: timedelta,
) -> pd.DataFrame:
    """Back-adjusted continuous OHLCV panel for ``root`` over ``[start, end]``.

    ``ports`` supplies the per-contract source plus daily volume probe, and
    ``list_contracts`` the dated-contract calendar (use :func:`databento_source` /
    :func:`databento_contract_calendar` in production; inject fakes in tests). The
    roll lead derives from ``bar_cadence``.
    """
    chain = fetch_contract_chain(
        root,
        start,
        end,
        list_contracts=list_contracts,
        fetch=ports.fetch,
        bar_cadence=bar_cadence,
        probe_volume=ports.probe,
    )
    return back_adjust_chain(chain, method=method)


__all__ = [
    "continuous_panel",
    "databento_contract_calendar",
    "databento_leg_ports",
    "databento_source",
]
