"""Resolve a futures root to a back-adjusted continuous OHLCV panel.

Composes the store-cached Nautilus databento port fetch, the contract-chain
assembly, and the back-adjustment transform.  This is the package's deep public
entry point for consumers (Aegis RD's pipeline, Aegis Trader): an omitted
``source:`` means "read the store, fetch-on-miss via the port, then back-adjust".
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from aegis_data.back_adjust import back_adjust_chain
from aegis_data.chain import ContractCalendar, ContractFetcher, fetch_contract_chain
from aegis_data.databento_port import databento_contract_calendar, databento_port_fetcher
from aegis_data.store import cached_fetcher


def databento_source(
    dataset: str, *, store_dir=None, client=None
) -> ContractFetcher:
    """A store-cached, fetch-on-miss per-contract fetcher over the databento port."""
    return cached_fetcher(
        databento_port_fetcher(dataset, client=client), dataset=dataset, store_dir=store_dir
    )


def continuous_panel(
    root: str,
    start: date,
    end: date,
    *,
    fetch: ContractFetcher,
    list_contracts: ContractCalendar,
    method: str = "ratio",
    roll_lead_days: int = 5,
) -> pd.DataFrame:
    """Back-adjusted continuous OHLCV panel for ``root`` over ``[start, end]``.

    ``fetch`` is the per-contract source and ``list_contracts`` the dated-contract
    calendar (use :func:`databento_source` / :func:`databento_contract_calendar` in
    production; inject fakes in tests).
    """
    chain = fetch_contract_chain(
        root, start, end, list_contracts=list_contracts, fetch=fetch, roll_lead_days=roll_lead_days
    )
    return back_adjust_chain(chain, method=method)


__all__ = ["continuous_panel", "databento_contract_calendar", "databento_source"]
