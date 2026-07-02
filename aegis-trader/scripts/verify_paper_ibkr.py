"""Live verification for the Dockerized IBKR paper/live daemon.

Builds a live Nautilus node that hands Nautilus a Dockerized IB Gateway config,
lets Nautilus start or reuse the gateway, reconciles the account, and prints the
per-currency balances — proving the account is multi-currency (``base_currency``
is ``None``; balances are held per currency) and broker-reported. With
``--submit`` it also places a small market order so live routing is exercised.

This is the operator runtime step (no offline substrate): it makes a real
connection to IBKR and, with ``--submit``, a real paper/live order. Use this as
the short acceptance checklist before running the full Execution Bundle:

    [ ] FX instrument resolves and streams
    [ ] Listed instrument resolves and streams
    [ ] Continuous future resolves, streams, and rolls from the configured table

Connection is read from the environment (``IBConnectionSettings``):

    IB_ACCOUNT_ID   required, e.g. DUxxxxxxx
    IB_PORT         required — the dockerized gateway switch
                    (IB Gateway paper = 4002, live = 4001)
    IB_CLIENT_ID    default 1
    TWS_USERNAME    required by Nautilus's dockerized gateway
    TWS_PASSWORD    required by Nautilus's dockerized gateway

Example (reconcile-only first, then with the order):

    TWS_USERNAME=<user> TWS_PASSWORD=<pass> IB_ACCOUNT_ID=DUxxxxxx IB_PORT=4002 \
        uv run python scripts/verify_paper_ibkr.py
    TWS_USERNAME=<user> TWS_PASSWORD=<pass> IB_ACCOUNT_ID=DUxxxxxx IB_PORT=4002 \
        uv run python scripts/verify_paper_ibkr.py --symbol VOD --exchange LSE \
        --currency GBP --submit
"""

from __future__ import annotations

import argparse
import asyncio
import logging

import msgspec
import pandas as pd
from nautilus_trader.adapters.interactive_brokers.common import IBContract
from nautilus_trader.adapters.interactive_brokers.config import (
    IBMarketDataTypeEnum,
    InteractiveBrokersDataClientConfig,
    InteractiveBrokersExecClientConfig,
    InteractiveBrokersInstrumentProviderConfig,
)
from nautilus_trader.adapters.interactive_brokers.factories import (
    InteractiveBrokersLiveDataClientFactory,
    InteractiveBrokersLiveExecClientFactory,
)
from nautilus_trader.config import StrategyConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.trading.strategy import Strategy

from aegis_data.ibkr import _gateway_endpoint
from aegis_trader.config import IBConnectionSettings
from aegis_trader.trader.node import build_live_node_config

_log = logging.getLogger("verify_paper_ibkr")

# Nautilus client id used for both IBKR clients (matches the factory keys).
_IB = "INTERACTIVE_BROKERS"


class VerifyConfig(StrategyConfig, frozen=True):
    """What the verification strategy needs to find the instrument and act."""

    target_currency: str
    target_symbol: str
    submit: bool
    target_qty: float = 1.0
    cash_quantity: bool = False
    cancel_on_accept: bool = False
    time_in_force: str = "GTC"
    side: str = "BUY"
    warmup_secs: float = 8.0
    settle_secs: float = 14.0


class VerifyStrategy(Strategy):
    """Reconcile-and-report: dump the account, optionally buy 1 foreign share."""

    def __init__(self, config: VerifyConfig) -> None:
        super().__init__(config)
        self._traded = False

    def on_start(self) -> None:
        self.log.info("verify: started; waiting for account reconciliation")
        self.clock.set_time_alert(
            name="verify-warmup",
            alert_time=self.clock.utc_now() + pd.Timedelta(seconds=self.config.warmup_secs),
            callback=self._on_warmup,
        )

    def _on_warmup(self, _event) -> None:
        self.log.info("verify: post-reconciliation account snapshot")
        self._dump_accounts()
        self._dump_instruments()
        if self.config.submit:
            self._submit_foreign_buy()
        self.clock.set_time_alert(
            name="verify-settle",
            alert_time=self.clock.utc_now() + pd.Timedelta(seconds=self.config.settle_secs),
            callback=self._on_settle,
        )

    def _on_settle(self, _event) -> None:
        self.log.info("verify: final account snapshot")
        self._dump_accounts()
        self.stop()

    def _submit_foreign_buy(self) -> None:
        instrument = self._find_target_instrument()
        if instrument is None:
            self.log.error(
                f"verify: no {self.config.target_currency} instrument "
                f"(symbol~{self.config.target_symbol}) in cache; nothing to buy"
            )
            return
        quantity = instrument.make_qty(self.config.target_qty)
        order = self.order_factory.market(
            instrument_id=instrument.id,
            order_side=OrderSide[self.config.side],
            quantity=quantity,
            time_in_force=TimeInForce[self.config.time_in_force],
            quote_quantity=self.config.cash_quantity,
        )
        kind = "cash" if self.config.cash_quantity else "units"
        self.log.info(f"verify: submitting {self.config.side} {quantity} ({kind}) {instrument.id}")
        self.submit_order(order)
        self._traded = True

    def _find_target_instrument(self):
        want_ccy = self.config.target_currency.upper()
        want_sym = self.config.target_symbol.upper()
        # Match by symbol so this works for equities (VOD.LSE) and crypto
        # (BTC/USD.PAXOS) alike; prefer one quoted in the target currency.
        candidates = [i for i in self.cache.instruments() if want_sym in i.id.value.upper()]
        for instrument in candidates:
            if str(instrument.quote_currency) == want_ccy:
                return instrument
        return candidates[0] if candidates else None

    def on_order_filled(self, event) -> None:
        self.log.info(
            f"verify: FILLED {event.instrument_id} qty={event.last_qty} "
            f"px={event.last_px} commission={event.commission}"
        )
        self._dump_accounts()

    def on_order_accepted(self, event) -> None:
        self.log.info(f"verify: ACCEPTED {event.client_order_id} (exec routing to IBKR OK)")
        if not self.config.cancel_on_accept:
            return  # let it fill (e.g. 24/7 crypto)
        order = self.cache.order(event.client_order_id)
        if order is not None and not order.is_closed:
            self.log.info(
                f"verify: cancelling {event.client_order_id} "
                f"(prove-routing run — avoid a dangling order into next session)"
            )
            self.cancel_order(order)

    def on_order_rejected(self, event) -> None:
        self.log.info(
            f"verify: REJECTED {event.client_order_id} reason={event.reason!r} "
            f"(routing reached IBKR; market is closed)"
        )

    def on_order_canceled(self, event) -> None:
        self.log.info(f"verify: CANCELED {event.client_order_id}")

    def _dump_accounts(self) -> None:
        accounts = self.cache.accounts()
        if not accounts:
            self.log.warning("verify: no account reconciled yet")
            return
        for account in accounts:
            self.log.info(
                f"verify: account {account.id} type={account.type} "
                f"base_currency={account.base_currency} (None => multi-currency)"
            )
            for currency, balance in account.balances().items():
                self.log.info(
                    f"verify:   {currency}: total={balance.total} "
                    f"free={balance.free} locked={balance.locked}"
                )

    def _dump_instruments(self) -> None:
        for instrument in self.cache.instruments():
            self.log.info(
                f"verify: instrument {instrument.id} "
                f"({type(instrument).__name__}, quote={instrument.quote_currency})"
            )


def _build_node(args, settings: IBConnectionSettings) -> TradingNode:
    contract = IBContract(
        secType=args.sec_type,
        symbol=args.symbol,
        exchange=args.exchange,
        currency=args.currency,
    )
    provider = InteractiveBrokersInstrumentProviderConfig(load_contracts=frozenset([contract]))
    endpoint = _gateway_endpoint(settings)
    data_cfg = InteractiveBrokersDataClientConfig(
        ibg_client_id=settings.client_id,
        market_data_type=IBMarketDataTypeEnum.DELAYED_FROZEN,
        use_regular_trading_hours=True,
        instrument_provider=provider,
        **endpoint,
    )
    exec_cfg = InteractiveBrokersExecClientConfig(
        ibg_client_id=settings.client_id,
        account_id=settings.account_id,
        instrument_provider=provider,
        **endpoint,
    )
    base = build_live_node_config(trader_id=settings.trader_id)
    config = msgspec.structs.replace(
        base,
        data_clients={_IB: data_cfg},
        exec_clients={_IB: exec_cfg},
    )
    node = TradingNode(config=config)
    node.add_data_client_factory(_IB, InteractiveBrokersLiveDataClientFactory)
    node.add_exec_client_factory(_IB, InteractiveBrokersLiveExecClientFactory)
    node.build()
    node.trader.add_strategy(
        VerifyStrategy(
            VerifyConfig(
                target_currency=args.currency,
                target_symbol=args.symbol,
                target_qty=args.qty,
                cash_quantity=args.cash_qty,
                cancel_on_accept=args.cancel_on_accept,
                time_in_force=args.tif,
                side=args.side,
                submit=args.submit,
            )
        )
    )
    return node


async def _amain(args, settings: IBConnectionSettings, timeout: float) -> None:
    # Build the node INSIDE the running loop so its IBKR clients bind to the
    # loop that will drive them (building outside leaves _connect tasks orphaned
    # on a non-running loop).
    node = _build_node(args, settings)
    runner = asyncio.ensure_future(node.run_async())
    try:
        await asyncio.sleep(timeout)
    finally:
        await node.stop_async()
        await asyncio.sleep(2)
        runner.cancel()
        node.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the IBKR paper (DU) account under Environment.LIVE.")
    parser.add_argument("--symbol", default="VOD", help="foreign equity symbol (default VOD)")
    parser.add_argument("--exchange", default="LSE", help="IBKR exchange (default LSE)")
    parser.add_argument("--currency", default="GBP", help="instrument currency (default GBP)")
    parser.add_argument("--sec-type", default="STK", help="IBKR secType: STK, CRYPTO, ... (default STK)")
    parser.add_argument("--qty", type=float, default=1.0, help="order quantity (units, or cash amount with --cash-qty)")
    parser.add_argument("--cash-qty", action="store_true", help="interpret --qty as a quote-currency cash amount (IBKR crypto needs this)")
    parser.add_argument("--cancel-on-accept", action="store_true", help="cancel immediately on accept (prove routing without a fill)")
    parser.add_argument("--tif", default="GTC", help="time-in-force: GTC, IOC, DAY, ... (IBKR crypto needs IOC)")
    parser.add_argument("--side", default="BUY", help="order side: BUY or SELL")
    parser.add_argument("--submit", action="store_true", help="place a market order of --qty")
    parser.add_argument("--timeout", type=float, default=30.0, help="seconds before shutdown")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    settings = IBConnectionSettings.from_env()
    _log.info(
        "verify: connecting dockerized account=%s IB_PORT=%d submit=%s instrument=%s.%s/%s",
        settings.account_id, settings.port, args.submit,
        args.symbol, args.exchange, args.currency,
    )
    try:
        asyncio.run(_amain(args, settings, args.timeout))
    except RuntimeError as exc:
        # uvloop/asyncio teardown after Nautilus stops its own loop; the
        # verification has already completed and logged by this point.
        _log.info("verify: node shut down (%s)", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
