"""Mode wiring (Slice 10 & 11): paper and live TradingNodes against IBKR (aegis-rd-fuu.9: paper=DU under LIVE)
with IBKR client configs.

Builds NautilusTrader TradingNodes configured for paper (IBKR paper DU) and
live trading, both under ``Environment.LIVE``, through Interactive Brokers.  Every wire is
connected — data client, exec client, instrument provider, routing, cache,
logging, reconciliation — but NO live connection is made or asserted.

Architecture invariant (ADR-0003): IBKR appears ONLY in this module as
client-factory config.  No broker import in domain/, ports/, the Strategy,
or execution translation.

The IBKR-specific config objects (``InteractiveBrokersDataClientConfig``,
``InteractiveBrokersExecClientConfig``) require the ``ibapi`` runtime.
To keep this module importable without ``ibapi``, the data-client and
exec-client configs are produced as plain dicts.  The operator feeds these
dicts into the full IBKR config classes at node-build time.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.config import (
    CacheConfig,
    LiveExecEngineConfig,
    LiveRiskEngineConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.common import Environment
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.config import DataCatalogConfig
from nautilus_trader.risk.config import RiskEngineConfig

from aegis_data.catalog import catalog_root

from aegis_trader.domain.risk_guard import RiskGuardConfig


# ── next-close execution TIF per mode (ADR-0001) ──────────────────────────────


def fill_time_in_force_for_mode(mode: str) -> TimeInForce | None:
    """Next-close time-in-force for a run *mode* (ADR-0001).

    - ``"backtest"`` → ``None``: a plain ``MARKET`` order fills at the execution
      bar's close (the SimulatedExchange rejects session TIFs).
    - ``"paper"`` / ``"live"`` → ``TimeInForce.AT_THE_CLOSE``: a Market-on-Close
      order into the closing auction.

    Both model the same fill point (the close), so research↔backtest↔live align.
    Feed the result into ``RebalanceStrategyConfig.fill_time_in_force``.
    """
    if mode == "backtest":
        return None
    if mode in ("paper", "live"):
        return TimeInForce.AT_THE_CLOSE
    raise ValueError(f"unknown mode {mode!r}; expected 'backtest', 'paper', or 'live'")


# ── RiskEngine wiring (ADR-0001: order-level guards are mandatory) ─────────────


def build_risk_engine_config(
    risk_guard_config: RiskGuardConfig | None = None,
) -> RiskEngineConfig:
    """Build the backtest RiskEngineConfig (``BacktestEngine`` requires the
    non-live variant).

    Carries the RiskGuard's order submit/modify rate limits and is never
    bypassed — the RiskEngine is an always-on, defense-in-depth guard over the
    sizing layer.  Per-instrument max-notional caps depend on live NAV and are
    applied by the strategy at startup (``RebalanceStrategy.risk_engine_config_dict``).
    """
    guard = risk_guard_config or RiskGuardConfig()
    return RiskEngineConfig(
        bypass=False,
        max_order_submit_rate=guard.max_order_submit_rate,
        max_order_modify_rate=guard.max_order_modify_rate,
    )


def build_live_risk_engine_config(
    risk_guard_config: RiskGuardConfig | None = None,
) -> LiveRiskEngineConfig:
    """Build the live/paper RiskEngine config (``TradingNode`` requires the live
    variant).  Same always-on guard as :func:`build_risk_engine_config`."""
    guard = risk_guard_config or RiskGuardConfig()
    return LiveRiskEngineConfig(
        bypass=False,
        max_order_submit_rate=guard.max_order_submit_rate,
        max_order_modify_rate=guard.max_order_modify_rate,
    )

# ── IBKR constants ───────────────────────────────────────────────────────────

IB_HOST: str = "127.0.0.1"
IB_CLIENT_ID: int = 1

# IBKR spot-FX venue; FX reference pairs (e.g. "EUR/USD.IDEALPRO") are loaded
# here so the overlay can mark the cache xrates from their quotes (aegis-rd-x0a).
IB_FX_VENUE: str = "IDEALPRO"

IB_PAPER_PORT: int = 4002  # IB Gateway paper port (TWS paper is 7497)
IB_PAPER_ACCOUNT_ID: str = "DU0000000"  # placeholder — operator provides real one

IB_LIVE_PORT: int = 4001  # IB Gateway live port (TWS live is 7496)
IB_LIVE_ACCOUNT_ID: str = "U0000000"  # placeholder — operator provides real one


# ── IBKR config dict builders (paper) ────────────────────────────────────────
#
# These return *dicts* rather than importing IBKR config classes so the module
# remains importable without ``ibapi``.  At runtime (with ibapi available) the
# operator passes the dict through InteractiveBrokersDataClientConfig or
# InteractiveBrokersExecClientConfig, which Nautilus resolves automatically.


def fx_reference_instrument_ids(
    base_currency: str,
    fx_currencies: Iterable[str],
) -> list[InstrumentId]:
    """FX reference-pair ``InstrumentId`` values for the IBKR InstrumentProvider
    to load — one ``{base}/{ccy}.IDEALPRO`` pair per non-base currency.

    Include these in a data-client builder's ``instrument_ids`` so the overlay
    can mark the cache xrate from each pair's quotes.  Assumes the book's base
    is the FX pair base — true for an EUR-base book on IDEALPRO (EUR is the
    base in every EUR cross); a non-base book would need an FX-convention map
    (not built: no such book today).
    """
    return sorted(
        (
            InstrumentId.from_str(f"{base_currency}/{ccy}.{IB_FX_VENUE}")
            for ccy in set(fx_currencies)
            if ccy != base_currency
        ),
        key=lambda instrument_id: instrument_id.value,
    )


def _data_client_config(
    *,
    ibg_host: str,
    ibg_port: int,
    ibg_client_id: int,
    market_data_type: str,
    instrument_ids: Iterable[InstrumentId],
) -> dict[str, Any]:
    """Shared data-client dict; embeds an InstrumentProvider load_ids list."""
    cfg: dict[str, Any] = {
        "ibg_host": ibg_host,
        "ibg_port": ibg_port,
        "ibg_client_id": ibg_client_id,
        "market_data_type": market_data_type,
        "use_regular_trading_hours": True,
    }
    return _with_instrument_provider(
        cfg,
        instrument_ids=instrument_ids,
    )


def _with_instrument_provider(
    cfg: dict[str, Any],
    *,
    instrument_ids: Iterable[InstrumentId],
) -> dict[str, Any]:
    provider = _instrument_provider_config(instrument_ids=instrument_ids)
    if provider:
        cfg["instrument_provider"] = provider
    return cfg


def _instrument_provider_config(
    *,
    instrument_ids: Iterable[InstrumentId],
) -> dict[str, Any]:
    load_ids = sorted(
        {instrument_id.value for instrument_id in instrument_ids},
    )
    return {"load_ids": load_ids} if load_ids else {}


def build_paper_data_client_config(
    *,
    ibg_host: str = IB_HOST,
    ibg_port: int = IB_PAPER_PORT,
    ibg_client_id: int = IB_CLIENT_ID,
    market_data_type: str = "REALTIME",
    instrument_ids: Iterable[InstrumentId] = (),
) -> dict[str, Any]:
    """Build an IBKR paper-mode data client config dict.

    ``market_data_type`` defaults to ``"REALTIME"`` (IBMarketDataTypeEnum.REALTIME):
    IDEALPRO spot FX streams real-time quotes the overlay needs to maintain its
    mark xrates, and DELAYED_FROZEN delivers none of them (live-validated). Pass
    native *instrument_ids* to preload provider-native contracts.
    """
    return _data_client_config(
        ibg_host=ibg_host, ibg_port=ibg_port, ibg_client_id=ibg_client_id,
        market_data_type=market_data_type,
        instrument_ids=instrument_ids,
    )


def build_paper_exec_client_config(
    *,
    ibg_host: str = IB_HOST,
    ibg_port: int = IB_PAPER_PORT,
    ibg_client_id: int = IB_CLIENT_ID,
    account_id: str = IB_PAPER_ACCOUNT_ID,
    instrument_ids: Iterable[InstrumentId] = (),
) -> dict[str, Any]:
    """Build an IBKR paper-mode execution client config dict.

    The account ID must be the Interactive Brokers paper account ID
    (DU-prefixed).  The actual account ID is provided by the operator,
    not hard-coded here.
    """
    cfg: dict[str, Any] = {
        "ibg_host": ibg_host,
        "ibg_port": ibg_port,
        "ibg_client_id": ibg_client_id,
        "account_id": account_id,
    }
    return _with_instrument_provider(
        cfg,
        instrument_ids=instrument_ids,
    )


# ── IBKR config dict builders (live) ─────────────────────────────────────────


def build_live_data_client_config(
    *,
    ibg_host: str = IB_HOST,
    ibg_port: int = IB_LIVE_PORT,
    ibg_client_id: int = IB_CLIENT_ID,
    market_data_type: str = "REALTIME",
    instrument_ids: Iterable[InstrumentId] = (),
) -> dict[str, Any]:
    """Build an IBKR live-mode data client config dict.

    ``market_data_type`` defaults to ``"REALTIME"`` (IBMarketDataTypeEnum.REALTIME)
    for live market data.  Pass native *instrument_ids* to have the
    InstrumentProvider load provider-native contracts.
    """
    return _data_client_config(
        ibg_host=ibg_host, ibg_port=ibg_port, ibg_client_id=ibg_client_id,
        market_data_type=market_data_type,
        instrument_ids=instrument_ids,
    )


def build_live_exec_client_config(
    *,
    ibg_host: str = IB_HOST,
    ibg_port: int = IB_LIVE_PORT,
    ibg_client_id: int = IB_CLIENT_ID,
    account_id: str = IB_LIVE_ACCOUNT_ID,
    instrument_ids: Iterable[InstrumentId] = (),
) -> dict[str, Any]:
    """Build an IBKR live-mode execution client config dict.

    The account ID must be the Interactive Brokers live account ID
    (non-DU-prefixed).  The actual account ID is provided by the
    operator, not hard-coded here.
    """
    cfg: dict[str, Any] = {
        "ibg_host": ibg_host,
        "ibg_port": ibg_port,
        "ibg_client_id": ibg_client_id,
        "account_id": account_id,
    }
    return _with_instrument_provider(
        cfg,
        instrument_ids=instrument_ids,
    )


# ── TradingNodeConfig builders ───────────────────────────────────────────────


DEFAULT_BACKTEST_BAR_CAPACITY = 10_000


def _build_trading_node_config(
    *,
    environment: Environment,
    trader_id: str = "TRADER-001",
) -> TradingNodeConfig:
    """Build a TradingNodeConfig with cache, logging, and reconciliation.

    The shared aegis-data catalog is wired in (ADR-0006): a startup
    ``request_bars(update_catalog=True)`` then serves history from the catalog and
    tops up only the missing tail from IBKR, persisting it — so research and live
    warm from the *same* corpus and live has no cold-start lookback gap.

    IBKR client configs are NOT populated — use the dict builders to
    produce configs, then pass them through the IBKR config constructors
    at node-build time (requires ``ibapi``).
    """
    return TradingNodeConfig(
        environment=environment,
        trader_id=trader_id,
        exec_engine=LiveExecEngineConfig(reconciliation=True),
        risk_engine=build_live_risk_engine_config(),
        cache=CacheConfig(),
        logging=LoggingConfig(),
        catalogs=[DataCatalogConfig(path=str(catalog_root()))],
    )


def build_backtest_engine_config(
    *,
    trader_id: str = "TRADER-001",
    risk_guard_config: RiskGuardConfig | None = None,
    bar_capacity: int = DEFAULT_BACKTEST_BAR_CAPACITY,
) -> BacktestEngineConfig:
    """Build the backtest-mode engine config (ADR-0003: the third mode).

    Mirrors the paper/live nodes' RiskEngine wiring so the overlay validated in
    backtest is constructed the same way it trades — "what you backtest is what
    you trade".  The caller adds venues, instruments, data, and the strategy to
    the resulting ``BacktestEngine`` and pairs it with
    ``fill_time_in_force_for_mode("backtest")`` (a plain ``MARKET``).
    """
    return BacktestEngineConfig(
        trader_id=trader_id,
        cache=CacheConfig(bar_capacity=bar_capacity),
        risk_engine=build_risk_engine_config(risk_guard_config),
        logging=LoggingConfig(),
    )


def build_paper_trading_node_config(
    *,
    trader_id: str = "TRADER-001",
) -> TradingNodeConfig:
    """Build a LIVE TradingNodeConfig for IBKR paper (DU) trading.

    Paper uses ``Environment.LIVE`` (not Nautilus SANDBOX): the IBKR adapter
    connects to the paper-account port and IBKR reports fills/commissions on a
    multi-currency account.  No fee/fill/financing model is injected here —
    paper costs are broker-reported (aegis-rd-fuu.9).
    """
    return _build_trading_node_config(
        environment=Environment.LIVE,
        trader_id=trader_id,
    )


def build_live_trading_node_config(
    *,
    trader_id: str = "TRADER-001",
) -> TradingNodeConfig:
    """Build a LIVE TradingNodeConfig for IBKR live trading."""
    return _build_trading_node_config(
        environment=Environment.LIVE,
        trader_id=trader_id,
    )


# ── TradingNode builders ─────────────────────────────────────────────────────


def build_paper_trading_node(
    *,
    trader_id: str = "TRADER-001",
) -> TradingNode:
    """Build a LIVE TradingNode for IBKR paper (DU) trading.

    Caller must add IBKR client configs, register factories, add the
    strategy, then call ``node.build()`` and ``node.run()``.
    """
    config = build_paper_trading_node_config(trader_id=trader_id)
    return TradingNode(config=config)


def build_live_trading_node(
    *,
    trader_id: str = "TRADER-001",
) -> TradingNode:
    """Build a LIVE TradingNode for IBKR live trading.

    Caller must add IBKR client configs, register factories, add the
    strategy, then call ``node.build()`` and ``node.run()``.
    """
    config = build_live_trading_node_config(trader_id=trader_id)
    return TradingNode(config=config)
