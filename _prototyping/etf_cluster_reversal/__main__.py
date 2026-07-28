"""Interactive shell for the ETF cluster-reversal logic prototype."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .model import (
    Action,
    Assessment,
    PrototypeState,
    assessments,
    initial_state,
    transition,
)

if TYPE_CHECKING:
    from .backtest import BacktestResult
    from .ib_history import UniverseLoad

BOLD = "\x1b[1m"
DIM = "\x1b[2m"
RESET = "\x1b[0m"

ACTIONS = {
    "t": Action.TICK,
    "f": Action.FLOW_SHOCK,
    "m": Action.BUCKET_MOVE,
    "d": Action.DUPLICATE_MOVE,
    "g": Action.REGIME_BREAK,
    "v": Action.REVERT,
    "c": Action.FREEZE_CLUSTERS,
    "b": Action.REBALANCE,
}


def main() -> None:
    arguments = _arguments()
    if arguments.backtest:
        _ib_backtest(arguments)
        return
    if arguments.ib:
        _ib_audit(arguments)
        return
    state = initial_state()
    while True:
        _render(state)
        command = input("\n> ").strip().lower()
        if command == "q":
            return
        action = ACTIONS.get(command)
        if action is not None:
            state = transition(state, action)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ETF residual-correlation reversal prototype"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--ib", action="store_true", help="audit the UCITS universe through IB Gateway"
    )
    mode.add_argument(
        "--backtest",
        action="store_true",
        help="run the causal UCITS walk-forward backtest",
    )
    parser.add_argument("--as-of", help="last completed London session, YYYY-MM-DD")
    parser.add_argument("--catalog", type=Path, help="Aegis parquet catalog path")
    parser.add_argument("--gateway-port", type=int, default=4002)
    parser.add_argument("--client-id", type=int, default=43)
    parser.add_argument("--minimum-dollar-volume", type=float, default=250_000.0)
    parser.add_argument("--history-years", type=float, default=5.0)
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--annual-short-borrow-bps", type=float, default=100.0)
    return parser.parse_args()


def _ib_audit(arguments: argparse.Namespace) -> None:
    from .ib_history import load_ucits_universe

    loaded = load_ucits_universe(
        as_of=arguments.as_of,
        catalog_path=arguments.catalog,
        gateway_port=arguments.gateway_port,
        client_id=arguments.client_id,
        minimum_median_dollar_volume=arguments.minimum_dollar_volume,
        progress=lambda message: print(message, file=sys.stderr, flush=True),
    )
    _render_ib_audit(loaded)


def _ib_backtest(arguments: argparse.Namespace) -> None:
    from .backtest import BacktestConfig, HistoricalEligibility, run_backtest
    from .ib_history import load_ucits_universe
    from .model import MINIMUM_HISTORY_SESSIONS

    warmup_days = round(MINIMUM_HISTORY_SESSIONS * 365.25 / 252) + 10
    history_days = round(arguments.history_years * 365.25) + warmup_days
    loaded = load_ucits_universe(
        as_of=arguments.as_of,
        catalog_path=arguments.catalog,
        gateway_port=arguments.gateway_port,
        client_id=arguments.client_id,
        history_calendar_days=history_days,
        minimum_median_dollar_volume=0.0,
        progress=lambda message: print(message, file=sys.stderr, flush=True),
    )
    result = run_backtest(
        loaded.state,
        loaded.execution_returns,
        HistoricalEligibility(
            dollar_volumes=loaded.dollar_volumes,
            family_by_ticker={item.ticker: item.family for item in loaded.included},
            minimum_median_dollar_volume=arguments.minimum_dollar_volume,
        ),
        BacktestConfig(
            transaction_cost_bps=arguments.cost_bps,
            annual_short_borrow_bps=arguments.annual_short_borrow_bps,
        ),
    )
    _render_backtest(loaded, result, arguments)


def _render_backtest(
    loaded: UniverseLoad, result: BacktestResult, arguments: argparse.Namespace
) -> None:
    start = result.daily.index[0].date().isoformat()
    end = result.daily.index[-1].date().isoformat()
    print(f"{BOLD}UCITS ETF RESIDUAL-REVERSAL WALK-FORWARD BACKTEST{RESET}")
    print(f"signal window: {start} .. {end} ({len(result.daily)} sessions)")
    print(f"data window: {loaded.start} .. {loaded.end}")
    print(f"peer universe: {', '.join(result.targets.columns)}")
    print("execution: signal close + 1 session open; hold open-to-open")
    print(
        f"costs: {arguments.cost_bps:.1f} bps per one-way turnover; "
        f"{arguments.annual_short_borrow_bps:.0f} bps annual short borrow\n"
    )
    print(f"gross total return:       {result.gross_total_return:+.2%}")
    print(f"net total return:         {result.net_total_return:+.2%}")
    print(f"annualized net return:    {result.annualized_net_return:+.2%}")
    print(f"annualized volatility:    {result.annualized_volatility:.2%}")
    sharpe = (
        f"{result.sharpe:+.2f}"
        if isinstance(result.sharpe, float)
        else f"undefined ({result.sharpe.reason})"
    )
    print(f"Sharpe (zero cash rate):   {sharpe}")
    print(f"maximum drawdown:         {result.maximum_drawdown:.2%}")
    print(f"transaction-cost drag:    {result.transaction_cost_drag:.2%}")
    print(f"short-borrow drag:        {result.borrow_cost_drag:.2%}")
    print(f"entries / exits:          {result.entries} / {result.exits}")
    print(f"exposure days:            {result.exposure_days}")
    print(f"total one-way turnover:   {result.turnover:.2f}x")
    print(
        "\nExploratory only: the universe is today's curated surviving UCITS set; "
        "OHLCV cannot verify historical spreads, depth, or stock-loan availability."
    )


def _render_ib_audit(loaded: UniverseLoad) -> None:
    state = loaded.state
    print(f"{BOLD}IBKR UCITS UNIVERSE AUDIT — ETF residual reversal{RESET}")
    print(f"window: {loaded.start} .. {loaded.end}")
    print(f"benchmark: {loaded.benchmark} (residualization only)")
    print(f"included / excluded: {len(loaded.included)} / {len(loaded.excluded)}")
    print(f"cluster frozen on: {state.clusters.formed_on}")
    print("signal targets: research only; no orders or live capital\n")

    print(f"{BOLD}Issuer-verified UCITS lines qualified live by IB{RESET}")
    for asset in loaded.included:
        role = "benchmark" if asset.ticker == loaded.benchmark else "peer"
        print(
            f"  {asset.ticker:4} {asset.family:18} {role:9} "
            f"bars={asset.observations:3} median $vol=${asset.median_dollar_volume / 1_000_000:6.1f}m"
        )
    if loaded.excluded:
        print(f"\n{BOLD}Excluded{RESET}")
        for excluded in loaded.excluded:
            print(f"  {excluded.ticker}: {excluded.reason}")

    print(f"\n{BOLD}Frozen market-residual clusters{RESET}")
    for label in sorted(set(state.clusters.assignments.values())):
        members = _cluster_members(state, label)
        stability = min(state.clusters.stability[ticker] for ticker in members)
        print(
            f"  C{label} [{stability:.0%} monthly membership overlap]: {', '.join(members)}"
        )

    print(f"\n{BOLD}Current five-session residual displacements{RESET}")
    for item in _ranked_assessments(state):
        z_score = "n/a" if item.residual_z is None else f"{item.residual_z:+.2f}"
        print(
            f"  {item.ticker:4} C{str(item.cluster):<2} z={z_score:>6} "
            f"volume={item.volume_ratio:4.1f}x gap={item.gap:+.1%}  {item.reason}"
        )


def _render(state: PrototypeState) -> None:
    print("\033[2J\033[H", end="")
    print(f"{BOLD}PROTOTYPE — ETF residual-correlation reversal{RESET}")
    print(
        f"{DIM}Question: do frozen OHLCV peer clusters create a coherent, "
        f"falsifiable residual-reversal state model?{RESET}\n"
    )
    print(f"{BOLD}date{RESET}: {state.returns.index[-1].date()}")
    print(f"{BOLD}cluster frozen on{RESET}: {state.clusters.formed_on}")
    print(f"{BOLD}last action{RESET}: {state.last_action}")
    print(f"{BOLD}active positions{RESET}: {len(state.positions)}")
    print(
        f"{BOLD}target gross / net{RESET}: {_gross(state.targets):.2f} / {sum(state.targets.values()):+.2f}"
    )

    print(f"\n{BOLD}Frozen clusters{RESET}")
    for label in sorted(set(state.clusters.assignments.values())):
        members = _cluster_members(state, label)
        rendered = [
            f"{ticker}→{state.clusters.duplicates[ticker]}"
            if ticker in state.clusters.duplicates
            else ticker
            for ticker in members
        ]
        minimum_stability = min(state.clusters.stability[ticker] for ticker in members)
        print(f"  C{label} [{minimum_stability:.0%} stable]: {', '.join(rendered)}")

    print(f"\n{BOLD}Largest current residuals{RESET}")
    for item in _ranked_assessments(state)[:8]:
        z_score = "  n/a" if item.residual_z is None else f"{item.residual_z:+5.2f}"
        flag = "TRADE" if item.eligible else "hold "
        print(
            f"  {item.ticker:4} C{str(item.cluster):<2} z={z_score} "
            f"vol={item.volume_ratio:4.1f}x gap={item.gap:+.1%} "
            f"{flag}  {DIM}{item.reason}{RESET}"
        )

    print(f"\n{BOLD}Positions and normalized targets{RESET}")
    if not state.positions:
        print(f"  {DIM}none — press b after creating an eligible displacement{RESET}")
    for position in state.positions.values():
        side = "LONG" if position.direction > 0 else "SHORT"
        print(
            f"  {position.ticker}: {side}, age={position.age}, "
            f"entry_z={position.entry_z:+.2f}, C{position.cluster}"
        )
    if state.targets:
        print(
            "  "
            + "  ".join(
                f"{ticker}={weight:+.2f}"
                for ticker, weight in sorted(state.targets.items())
            )
        )

    print(f"\n{BOLD}Actions{RESET}")
    print(f"  {BOLD}f{RESET} {DIM}isolated high-volume flow shock{RESET}")
    print(f"  {BOLD}m{RESET} {DIM}common bucket move (should not trade){RESET}")
    print(
        f"  {BOLD}d{RESET} {DIM}duplicate-wrapper information gap (should exclude){RESET}"
    )
    print(f"  {BOLD}g{RESET} {DIM}inject correlation-regime break{RESET}")
    print(f"  {BOLD}c{RESET} {DIM}freeze new clusters and expose instability{RESET}")
    print(f"  {BOLD}b{RESET} {DIM}apply entry/exit hysteresis{RESET}")
    print(f"  {BOLD}v{RESET} {DIM}partial reversion of active positions{RESET}")
    print(f"  {BOLD}t{RESET} {DIM}ordinary day / age positions{RESET}")
    print(f"  {BOLD}q{RESET} {DIM}quit{RESET}")


def _gross(targets: dict[str, float]) -> float:
    return sum(abs(weight) for weight in targets.values())


def _cluster_members(state: PrototypeState, label: int) -> list[str]:
    return sorted(
        ticker
        for ticker, cluster in state.clusters.assignments.items()
        if cluster == label
    )


def _ranked_assessments(state: PrototypeState) -> tuple[Assessment, ...]:
    return tuple(
        sorted(
            assessments(state),
            key=lambda item: (
                abs(item.residual_z) if item.residual_z is not None else -1.0
            ),
            reverse=True,
        )
    )


if __name__ == "__main__":
    main()
