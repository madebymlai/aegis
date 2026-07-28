"""Report shell for the European variance-risk-premium prototype.

Question: does a European CAPM-alpha-style variance risk premium survive past the
August-2012 structural break Dew-Becker & Giglio (Chicago Fed WP 2025-17) find killed it
in the US? No free investable EURO STOXX 50 put-write series exists (see README.md), so
this prints the raw VSTOXX-vs-realized-SX5E-volatility gap instead, split at the same
break date, and is explicit that a raw gap is not a risk-adjusted alpha.

Default mode uses deterministic synthetic data so the statistics can be checked by eye
without the network. ``--live`` fetches real EURO STOXX 50 history via yfinance and pairs
it with the checked-in VSTOXX fixture (see ``stoxx_history.py`` — that source is frozen at
2016-02-12 and is never fetched live) to print the actual verdict.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import model as m
from . import stoxx_history as sh
from . import synthetic as syn
from . import yahoo_history as yh

BOLD = "\x1b[1m"
DIM = "\x1b[2m"
RESET = "\x1b[0m"

DEFAULT_CACHE_DIR = Path(__file__).parent / ".cache"


def main() -> None:
    arguments = _arguments()
    if arguments.live:
        _run_live(arguments)
    else:
        _run_synthetic(arguments)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="European variance-risk-premium structural-break prototype"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="fetch real SX5E history via yfinance (VSTOXX always reads the bundled fixture)",
    )
    parser.add_argument(
        "--start", default="2000-01-01", help="live mode: history start"
    )
    parser.add_argument(
        "--end", default=None, help="live mode: history end (default: today)"
    )
    parser.add_argument("--break-date", default=m.DEFAULT_BREAK_DATE)
    parser.add_argument(
        "--lags",
        type=int,
        default=m.VSTOXX_HORIZON_TRADING_DAYS - 1,
        help="Newey-West lag length (default: horizon - 1, matching the overlap)",
    )
    parser.add_argument(
        "--trend-lookback", type=int, default=m.SLOW_TREND_LOOKBACK_DAYS
    )
    parser.add_argument("--worst-quantile", type=float, default=0.05)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--refresh", action="store_true", help="ignore the local cache and refetch"
    )
    return parser.parse_args()


def _run_synthetic(arguments: argparse.Namespace) -> None:
    market = syn.synthetic_market(break_date=arguments.break_date)
    print(f"{BOLD}PROTOTYPE — European variance risk premium (SYNTHETIC){RESET}")
    print(
        f"{DIM}Mechanism check only: VSTOXX here is realized-vol-plus-a-known-offset by "
        f"construction. Embedded pre/post gap = "
        f"{market.embedded_pre_gap_vol_points:.2f} / {market.embedded_post_gap_vol_points:.2f} "
        f"vol points. Run --live for the real verdict.{RESET}\n"
    )
    _report(
        market.vstoxx_level,
        market.sx5e_log_returns,
        arguments,
        data_note="synthetic — not evidence about Europe",
    )


def _run_live(arguments: argparse.Namespace) -> None:
    print(f"{BOLD}PROTOTYPE — European variance risk premium (LIVE){RESET}\n")
    vstoxx = sh.load_vstoxx_history()
    sx5e = yh.load_sx5e_log_returns(
        arguments.start,
        arguments.end or _today(),
        cache_dir=arguments.cache_dir,
        refresh=arguments.refresh,
    )
    print(
        f"VSTOXX (V2TX): {vstoxx.observations} sessions from {vstoxx.start} to {vstoxx.end}\n"
        f"  {DIM}source: checked-in fixture (originally {vstoxx.source_url}, fetched "
        f"{sh.FETCHED_ON}). This free file is frozen at {vstoxx.end} and is never "
        f"updated — nothing here speaks to 2016-2026.{RESET}"
    )
    print(
        f"{sx5e.ticker}: {sx5e.observations} sessions from {sx5e.series.index[0].date()} "
        f"to {sx5e.series.index[-1].date()} ({sx5e.source})\n"
    )
    _report(
        vstoxx.level,
        sx5e.series,
        arguments,
        data_note=f"real VSTOXX (STOXX) / {sx5e.ticker} (Yahoo Finance)",
    )


def _report(
    vstoxx_level, sx5e_log_returns, arguments: argparse.Namespace, *, data_note: str
) -> None:
    gap = m.variance_gap(vstoxx_level, sx5e_log_returns)
    print(
        f"{BOLD}Test 1 — raw VSTOXX-minus-realized-SX5E variance gap ({data_note}){RESET}"
    )
    print(
        f"{DIM}NOT a risk-adjusted alpha: a positive gap fully explained by market beta is "
        f"compensation for holding the index, not income.{RESET}"
    )
    try:
        break_result = m.structural_break_test(
            gap["gap_vol_points"], arguments.break_date, arguments.lags
        )
    except m.InsufficientHistory as error:
        print(f"  UNTESTABLE: {error}")
        break_result = None
    if break_result is not None:
        _print_break_result(break_result)

    print(f"\n{BOLD}Test 2 — moneyness concentration{RESET}")
    print(
        "  UNTESTABLE on free data: VSTOXX is one constant-maturity, near-the-money-ish\n"
        "  implied-vol point, not a moneyness-sliced surface. No free source of European\n"
        "  index-option implied vol by strike was found."
    )

    print(f"\n{BOLD}Test 3 — put-write CAPM alpha and its structural break{RESET}")
    print(
        "  UNTESTABLE on free data: STOXX's own SX5E3P PutWrite index factsheet discloses\n"
        "  backtested (pre-launch, hypothetical) history, and no downloadable free daily\n"
        "  series or investable UCITS/ETF wrapper could be found (see README.md). Test 1's\n"
        "  raw gap is the closest free-data proxy, and it is a materially weaker claim."
    )

    print(
        f"\n{BOLD}Test 4 — loss-state timing vs. a slow (12-month) trend overlay{RESET}"
    )
    trend_returns = m.slow_trend_returns(sx5e_log_returns, arguments.trend_lookback)
    payoff = m.daily_short_vol_payoff(vstoxx_level, sx5e_log_returns)
    try:
        overlap = m.loss_state_overlap(payoff, trend_returns, arguments.worst_quantile)
        _print_loss_state(overlap, arguments.worst_quantile)
    except m.InsufficientHistory as error:
        print(f"  UNTESTABLE: {error}")


def _print_break_result(result: m.StructuralBreakResult) -> None:
    print(f"  break date: {result.break_date}")
    print(
        f"  pre  [{result.pre.observations:>5} obs]: mean={result.pre.mean:+.2f} vol-pts  "
        f"se={result.pre.standard_error:.2f}  t={result.pre.t_statistic:+.2f}  "
        f"p={result.pre.p_value:.4f}"
    )
    print(
        f"  post [{result.post.observations:>5} obs]: mean={result.post.mean:+.2f} vol-pts  "
        f"se={result.post.standard_error:.2f}  t={result.post.t_statistic:+.2f}  "
        f"p={result.post.p_value:.4f}"
    )
    print(
        f"  difference (post - pre): {result.difference:+.2f} vol-pts  "
        f"t={result.difference_t_statistic:+.2f}  p={result.difference_p_value:.4f}"
    )
    if result.pre.observations < 250 or result.post.observations < 250:
        print(
            f"  {DIM}caveat: one side has under a year of sessions; treat as indicative "
            f"only{RESET}"
        )


def _print_loss_state(overlap: m.LossStateOverlap, worst_quantile: float) -> None:
    print(
        f"  full-sample correlation (short-vol payoff, trend): {overlap.correlation:+.3f}"
    )
    print(
        f"  trend mean return on short-vol's worst {worst_quantile:.0%} "
        f"({overlap.worst_days} days): {overlap.trend_return_on_worst_days_mean:+.4%} "
        f"vs full-sample mean {overlap.trend_return_full_sample_mean:+.4%}"
    )
    print(
        f"  trend positive on {overlap.trend_share_positive_on_worst_days:.0%} of those "
        "worst days"
    )


def _today() -> str:
    import datetime as _datetime

    return _datetime.date.today().isoformat()


if __name__ == "__main__":
    main()
