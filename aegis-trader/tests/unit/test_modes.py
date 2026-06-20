"""Unit tests for Slice 10 (paper-mode) and Slice 11 (live-mode) wiring.

Validates that paper-mode (IBKR paper DU, LIVE) and live-mode (LIVE) configuration
functions build correctly configured TradingNodeConfigs with cache,
logging, and reconciliation — all without requiring a live IBKR
connection or the ``ibapi`` package.

These are *wiring* tests: they assert that the right components are present
and correctly configured, not that the node connects to IBKR.

The IBKR-specific data-client and exec-client configs are tested as dict
builders — the actual ``InteractiveBrokersDataClientConfig`` /
``InteractiveBrokersExecClientConfig`` constructors require ``ibapi`` and
are tested separately in an integration environment.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pytest
from aegis_data.roll import DatedContract
from aegis_runtime import FuturesRef, ListedRef
from nautilus_trader.config import (
    CacheConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.common import Environment

from nautilus_trader.model.enums import TimeInForce

from aegis_trader.domain.book_config import BookConfig, CostModelConfig, SleeveConfig
from aegis_trader.domain.types import SleeveName
from aegis_trader.trader.costs import (
    IbkrPerShareFeeModel,
    SimulatedFillModel,
    build_simulated_cost_models,
)
from aegis_trader.trader.modes import (
    build_backtest_engine_config,
    build_paper_trading_node,
    build_paper_trading_node_config,
    build_paper_data_client_config,
    build_paper_exec_client_config,
    build_live_trading_node,
    build_live_trading_node_config,
    build_live_data_client_config,
    build_live_exec_client_config,
    build_risk_engine_config,
    fill_time_in_force_for_mode,
    fx_reference_instrument_ids,
    IB_CLIENT_ID,
    IB_FX_VENUE,
    IB_HOST,
    IB_LIVE_ACCOUNT_ID,
    IB_LIVE_PORT,
    IB_PAPER_ACCOUNT_ID,
    IB_PAPER_PORT,
)
from aegis_trader.trader.instrument_provider import InstrumentResolutionError


# --------------------------------------------------------------------------- #
# FX reference-pair loading (aegis-rd-x0a: the overlay marks FX from these)
# --------------------------------------------------------------------------- #

def test_fx_reference_instrument_ids_for_eur_book():
    """Each non-base currency yields a base/ccy IDEALPRO FX pair id for the
    InstrumentProvider to load; the base currency itself is never a pair."""
    ids = fx_reference_instrument_ids("EUR", ["USD", "GBP", "EUR"])
    assert set(ids) == {f"EUR/USD.{IB_FX_VENUE}", f"EUR/GBP.{IB_FX_VENUE}"}


def test_fx_reference_instrument_ids_empty_when_single_currency():
    """A book wholly in its base currency needs no FX reference pairs."""
    assert fx_reference_instrument_ids("EUR", ["EUR"]) == []
    assert fx_reference_instrument_ids("EUR", []) == []


# --------------------------------------------------------------------------- #
# next-close TIF per mode (A2 / ADR-0001)
# --------------------------------------------------------------------------- #

def test_backtest_mode_uses_plain_market():
    """Backtest fills via a plain MARKET (no session TIF)."""
    assert fill_time_in_force_for_mode("backtest") is None


def test_paper_and_live_modes_use_market_on_close():
    """Paper/live carry AT_THE_CLOSE (Market-on-Close) per ADR-0001."""
    assert fill_time_in_force_for_mode("paper") == TimeInForce.AT_THE_CLOSE
    assert fill_time_in_force_for_mode("live") == TimeInForce.AT_THE_CLOSE


def test_unknown_mode_rejected():
    import pytest
    with pytest.raises(ValueError, match="unknown mode"):
        fill_time_in_force_for_mode("sandbox")


# --------------------------------------------------------------------------- #
# RiskEngine wiring (A4) + backtest mode runner (A5)
# --------------------------------------------------------------------------- #

def test_risk_engine_config_carries_rate_limits_and_is_not_bypassed():
    cfg = build_risk_engine_config()
    assert cfg.bypass is False
    assert cfg.max_order_submit_rate == "10/00:00:01"
    assert cfg.max_order_modify_rate == "10/00:00:01"


def test_paper_node_wires_risk_engine():
    cfg = build_paper_trading_node_config()
    assert cfg.risk_engine is not None
    assert cfg.risk_engine.bypass is False


def test_live_node_wires_risk_engine():
    cfg = build_live_trading_node_config()
    assert cfg.risk_engine is not None
    assert cfg.risk_engine.bypass is False


def test_backtest_engine_config_mirrors_risk_wiring():
    cfg = build_backtest_engine_config()
    assert cfg.risk_engine is not None
    assert cfg.risk_engine.bypass is False
    assert cfg.risk_engine.max_order_submit_rate == "10/00:00:01"


def test_backtest_engine_config_accepts_bar_capacity_for_cache_window():
    cfg = build_backtest_engine_config(bar_capacity=64)
    assert cfg.cache is not None
    assert cfg.cache.bar_capacity == 64


# --------------------------------------------------------------------------- #
# simulated venue cost wiring helper (aegis-rd-fuu.4)
# --------------------------------------------------------------------------- #

def test_simulated_cost_model_helper_derives_fee_and_fill_models_from_the_book():
    book = BookConfig(
        sleeves=(
            SleeveConfig(
                name=SleeveName("trend"),
                wheel_filename="trend.whl",
                risk_share=1.0,
            ),
        ),
        base_currency="EUR",
        costs=CostModelConfig(
            per_share_commission=0.0035,
            min_commission_per_order=1.0,
            max_commission_pct=0.01,
            slippage_probability=0.25,
            slippage_seed=42,
        ),
    )

    models = build_simulated_cost_models(book)

    assert isinstance(models.fee_model, IbkrPerShareFeeModel)
    assert isinstance(models.fill_model, SimulatedFillModel)
    assert models.fill_model.prob_slippage == 0.25
    assert models.fill_model.random_seed == 42


# --------------------------------------------------------------------------- #
# structural config tests (no IBKR imports needed)
# --------------------------------------------------------------------------- #

def test_paper_node_config_has_live_environment():
    """The paper TradingNodeConfig MUST use Environment.LIVE.

    Paper trades the IBKR paper (DU) account via the IBKR adapter, which runs
    under LIVE — Nautilus SANDBOX (local-sim execution) is intentionally not
    used, so paper fills/commissions are broker-reported (aegis-rd-fuu.9).
    """
    cfg = build_paper_trading_node_config()
    assert cfg.environment == Environment.LIVE, (
        f"Expected LIVE, got {cfg.environment}"
    )


def test_paper_node_config_has_cache():
    cfg = build_paper_trading_node_config()
    assert cfg.cache is not None, (
        "Expected cache config to be set"
    )
    assert isinstance(cfg.cache, CacheConfig)


def test_paper_node_config_has_logging():
    cfg = build_paper_trading_node_config()
    assert cfg.logging is not None, (
        "Expected logging config to be set"
    )
    assert isinstance(cfg.logging, LoggingConfig)


def test_paper_node_config_has_reconciliation():
    cfg = build_paper_trading_node_config()
    assert cfg.exec_engine.reconciliation is True, (
        f"Expected reconciliation=True, got {cfg.exec_engine.reconciliation}"
    )


def test_paper_node_config_is_msgspec_serializable():
    """TradingNodeConfig survives a JSON round-trip."""
    cfg = build_paper_trading_node_config()
    cfg_json = cfg.json()
    loaded = TradingNodeConfig.parse(cfg_json)
    assert loaded.environment == cfg.environment
    assert loaded.trader_id == cfg.trader_id
    assert loaded.cache is not None
    assert loaded.logging is not None
    assert loaded.exec_engine.reconciliation is True


# --------------------------------------------------------------------------- #
# IBKR dict config tests (no ibapi needed — just dict assertions)
# --------------------------------------------------------------------------- #

def test_paper_data_client_config_defaults():
    """The paper IBKR data client dict uses realtime market data on the paper port.

    Realtime (not frozen): IDEALPRO spot FX streams real-time quotes that
    DELAYED_FROZEN does not deliver — and the overlay needs those quotes to
    maintain its FX mark xrates (live-validated against paper DUQ455398)."""
    cfg = build_paper_data_client_config()
    assert cfg["ibg_host"] == IB_HOST
    assert cfg["ibg_port"] == IB_PAPER_PORT
    assert cfg["ibg_client_id"] == IB_CLIENT_ID
    assert cfg["market_data_type"] == "realtime"


def test_paper_data_client_config_custom_host():
    cfg = build_paper_data_client_config(ibg_host="10.0.0.1", ibg_port=4002)
    assert cfg["ibg_host"] == "10.0.0.1"
    assert cfg["ibg_port"] == 4002


def test_paper_data_client_config_custom_client_id():
    cfg = build_paper_data_client_config(ibg_client_id=99)
    assert cfg["ibg_client_id"] == 99


def test_data_client_loads_fx_reference_pairs_into_instrument_provider():
    """FX reference pairs are wired into the InstrumentProvider's load_ids so the
    venue streams their quotes and the overlay can mark the cache xrates."""
    fx_ids = fx_reference_instrument_ids("EUR", ["USD", "GBP"])
    cfg = build_paper_data_client_config(fx_instrument_ids=fx_ids)
    assert cfg["instrument_provider"]["load_ids"] == fx_ids
    # live builder wires it identically
    live = build_live_data_client_config(fx_instrument_ids=fx_ids)
    assert live["instrument_provider"]["load_ids"] == fx_ids


def test_data_client_loads_listed_refs_as_ib_figi_contracts():
    """ListedRefs are preloaded by FIGI through the IB InstrumentProvider."""
    refs = [ListedRef("BBG000R20GS9")]

    cfg = build_paper_data_client_config(listed_refs=refs)

    assert cfg["instrument_provider"] == {
        "load_contracts": [
            {
                "secType": "STK",
                "secIdType": "FIGI",
                "secId": "BBG000R20GS9",
                "exchange": "SMART",
            }
        ],
        "convert_exchange_to_mic_venue": True,
        "symbol_to_mic_venue": {"IGLN": "XLON", "GC": "XCEC", "SI": "XCEC", "HG": "XCEC"},
    }


def test_data_client_merges_fx_ids_and_listed_figi_contracts():
    fx_ids = fx_reference_instrument_ids("EUR", ["USD"])
    refs = [ListedRef("BBG000R20GS9")]

    cfg = build_live_data_client_config(fx_instrument_ids=fx_ids, listed_refs=refs)

    assert cfg["instrument_provider"]["load_ids"] == fx_ids
    assert cfg["instrument_provider"]["load_contracts"] == [
        {
            "secType": "STK",
            "secIdType": "FIGI",
            "secId": "BBG000R20GS9",
            "exchange": "SMART",
        }
    ]
    assert cfg["instrument_provider"]["convert_exchange_to_mic_venue"] is True


def test_data_client_loads_futures_refs_as_ib_local_symbol_contracts():
    ref = FuturesRef("6E", "GLBX.MDP3", roll_rule="calendar", adjustment="back_adjust")
    chains = {"6E": (DatedContract("6EU6", date(2026, 9, 14)),)}

    cfg = build_paper_data_client_config(
        futures_refs=[ref], futures_as_of=date(2026, 8, 1), futures_contract_chains=chains,
        bar_cadence=timedelta(days=1),
    )

    assert cfg["instrument_provider"] == {
        "load_contracts": [{"secType": "FUT", "localSymbol": "6EU6", "exchange": "CME"}],
        "convert_exchange_to_mic_venue": True,
        "symbol_to_mic_venue": {"IGLN": "XLON", "GC": "XCEC", "SI": "XCEC", "HG": "XCEC"},
    }


@pytest.mark.parametrize(
    ("bar_cadence", "expected_local_symbol"),
    [
        (timedelta(days=1), "6EM6"),   # daily lead 5: still holds the front contract
        (timedelta(weeks=1), "6EU6"),  # weekly lead 14: rolls earlier, already advanced
    ],
)
def test_data_client_derives_roll_lead_from_bar_cadence(bar_cadence, expected_local_symbol):
    # The lead is derived from the book's bar cadence, never configured. With the same
    # as_of, a daily book (lead 5) still holds the front 6EM6, while a weekly book
    # (lead 14, rolls earlier) has already advanced to 6EU6 — proving the data client
    # reads the *actual* cadence, not a daily constant.
    ref = FuturesRef("6E", "GLBX.MDP3", roll_rule="calendar", adjustment="back_adjust")
    chains = {
        "6E": (
            DatedContract("6EM6", date(2026, 6, 15)),
            DatedContract("6EU6", date(2026, 9, 14)),
        )
    }

    cfg = build_paper_data_client_config(
        futures_refs=[ref], futures_as_of=date(2026, 6, 1), futures_contract_chains=chains,
        bar_cadence=bar_cadence,
    )

    assert cfg["instrument_provider"]["load_contracts"] == [
        {"secType": "FUT", "localSymbol": expected_local_symbol, "exchange": "CME"}
    ]


def test_data_client_requires_bar_cadence_to_load_futures():
    # Mirrors the futures_as_of guard: futures cannot be selected without the cadence
    # the roll lead derives from.
    ref = FuturesRef("6E", "GLBX.MDP3", roll_rule="calendar", adjustment="back_adjust")
    chains = {"6E": (DatedContract("6EU6", date(2026, 9, 14)),)}

    with pytest.raises(InstrumentResolutionError, match="bar_cadence"):
        build_paper_data_client_config(
            futures_refs=[ref], futures_as_of=date(2026, 8, 1), futures_contract_chains=chains
        )


def test_data_client_omits_instrument_provider_when_no_fx_pairs():
    """A base-only book needs no FX pairs → no InstrumentProvider override."""
    assert "instrument_provider" not in build_paper_data_client_config()


def test_paper_exec_client_config_defaults():
    """The paper IBKR exec client dict MUST use paper port and DU-prefixed account."""
    cfg = build_paper_exec_client_config()
    assert cfg["ibg_host"] == IB_HOST
    assert cfg["ibg_port"] == IB_PAPER_PORT
    assert cfg["ibg_client_id"] == IB_CLIENT_ID
    assert cfg["account_id"].startswith("DU"), (
        f"Expected DU-prefixed paper account, got {cfg['account_id']!r}"
    )
    assert cfg["account_id"] == IB_PAPER_ACCOUNT_ID


def test_paper_exec_client_config_custom_account():
    cfg = build_paper_exec_client_config(account_id="DU1234567")
    assert cfg["account_id"] == "DU1234567"


# --------------------------------------------------------------------------- #
# node construction test (no live connection required)
# --------------------------------------------------------------------------- #

def test_paper_trading_node_constructs():
    """TradingNode constructs without error."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        try:
            node = build_paper_trading_node()
        except Exception as exc:
            assert False, f"build_paper_trading_node() raised {type(exc).__name__}: {exc}"
        else:
            assert node is not None
    finally:
        loop.close()


# --------------------------------------------------------------------------- #
# LIVE-mode structural config tests (Slice 11 — no IBKR imports needed)
# --------------------------------------------------------------------------- #

def test_live_node_config_has_live_environment():
    """The live TradingNodeConfig MUST use Environment.LIVE."""
    cfg = build_live_trading_node_config()
    assert cfg.environment == Environment.LIVE, (
        f"Expected LIVE, got {cfg.environment}"
    )


def test_live_node_config_has_cache():
    cfg = build_live_trading_node_config()
    assert cfg.cache is not None
    assert isinstance(cfg.cache, CacheConfig)


def test_live_node_config_has_logging():
    cfg = build_live_trading_node_config()
    assert cfg.logging is not None
    assert isinstance(cfg.logging, LoggingConfig)


def test_live_node_config_has_reconciliation():
    cfg = build_live_trading_node_config()
    assert cfg.exec_engine.reconciliation is True, (
        f"Expected reconciliation=True, got {cfg.exec_engine.reconciliation}"
    )


def test_live_node_config_is_msgspec_serializable():
    cfg = build_live_trading_node_config()
    cfg_json = cfg.json()
    loaded = TradingNodeConfig.parse(cfg_json)
    assert loaded.environment == cfg.environment
    assert loaded.trader_id == cfg.trader_id
    assert loaded.cache is not None
    assert loaded.logging is not None
    assert loaded.exec_engine.reconciliation is True


# --------------------------------------------------------------------------- #
# LIVE-mode IBKR dict config tests (no ibapi needed)
# --------------------------------------------------------------------------- #

def test_live_data_client_config_defaults():
    """The live IBKR data client dict defaults to realtime on the live port."""
    cfg = build_live_data_client_config()
    assert cfg["ibg_host"] == IB_HOST
    assert cfg["ibg_port"] == IB_LIVE_PORT
    assert cfg["ibg_client_id"] == IB_CLIENT_ID
    assert cfg["market_data_type"] == "realtime"


def test_live_data_client_config_custom_host():
    cfg = build_live_data_client_config(ibg_host="10.0.0.1", ibg_port=4001)
    assert cfg["ibg_host"] == "10.0.0.1"
    assert cfg["ibg_port"] == 4001


def test_live_data_client_config_custom_client_id():
    cfg = build_live_data_client_config(ibg_client_id=99)
    assert cfg["ibg_client_id"] == 99


def test_live_exec_client_config_defaults():
    """The live IBKR exec client dict MUST use live port and non-DU account."""
    cfg = build_live_exec_client_config()
    assert cfg["ibg_host"] == IB_HOST
    assert cfg["ibg_port"] == IB_LIVE_PORT
    assert cfg["ibg_client_id"] == IB_CLIENT_ID
    assert not cfg["account_id"].startswith("DU"), (
        f"Expected non-DU live account, got {cfg['account_id']!r}"
    )
    assert cfg["account_id"] == IB_LIVE_ACCOUNT_ID


def test_live_exec_client_config_custom_account():
    cfg = build_live_exec_client_config(account_id="U1234567")
    assert cfg["account_id"] == "U1234567"


def test_live_trading_node_constructs():
    """TradingNode constructs without error."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        try:
            node = build_live_trading_node()
        except Exception as exc:
            assert False, f"build_live_trading_node() raised {type(exc).__name__}: {exc}"
        else:
            assert node is not None
    finally:
        loop.close()
