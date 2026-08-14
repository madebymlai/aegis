"""The single IBKR seam — research historic fetch *and* live client wiring
(ADR-0003 amendment / ADR-0006/0008).

One seam for IBKR: research and live connect to Interactive Brokers through this
package, so the unified path (epic ``aegis-rd-r8b``) depends on the Nautilus
DataProvider port with IBKR as its first — and only — adapter.  The public
surface is this package's eight names; the submodules split the two
responsibilities by consumer:

- :mod:`aegis_data.ibkr.historical` — **historic fetch** (research / backfill):
  :class:`IbkrHistoricalProvider` wraps Nautilus's standalone
  ``HistoricInteractiveBrokersClient`` — the client "for backtesting and
  research".  It is **pure fetch** (``request_bars`` *returns* bars;
  :class:`CatalogBackedDataPort` is the single writer of record, ADR-0008),
  **hides ``asyncio``** behind a synchronous port, and resolves identity through
  IB **simplified symbology** — the native ``InstrumentId`` value
  (``SYMBOL.VENUE``) is the IBKR request id (ADR-0005).  Instrument
  *definitions* are a separate Step-1 write
  (:func:`seed_instrument_definitions`), not per-window fill data (ADR-0008).
- :mod:`aegis_data.ibkr.live` — **live client wiring**:
  :func:`attach_live_clients` builds Nautilus's *stock*
  ``InteractiveBrokers{Data,Exec}ClientConfig`` with a Nautilus-managed
  Dockerized IB Gateway and registers the stock live factories on a live
  ``TradingNode`` — no custom adapter code or container lifecycle code (epic
  thesis).  The Trader's broker-neutral ``node.py`` reaches IBKR through this
  one call.
- :mod:`aegis_data.ibkr.symbology` — the **venue pin** both sides share:
  :func:`mic_instrument_provider_config` qualifies IBKR exchanges to MIC venues
  so historic backfill and live subscriptions mint byte-identical ids.

IBKR (``ibapi``) is a true-external dependency, so *every* IBKR import — the
historic client and the live config/factory classes alike — is lazy: importing
this package never requires ``ibapi``.
"""

from __future__ import annotations

from aegis_data.ibkr.historical import (
    IbkrHistoricalProvider,
    IbkrRequestError,
    close_connection,
    historic_bar_client_factory,
    seed_instrument_definitions,
)
from aegis_data.ibkr.live import IB_CLIENT_NAME, BrokerConnection, attach_live_clients
from aegis_data.ibkr.symbology import mic_instrument_provider_config

__all__ = [
    "IB_CLIENT_NAME",
    "BrokerConnection",
    "IbkrHistoricalProvider",
    "IbkrRequestError",
    "attach_live_clients",
    "close_connection",
    "historic_bar_client_factory",
    "mic_instrument_provider_config",
    "seed_instrument_definitions",
]
