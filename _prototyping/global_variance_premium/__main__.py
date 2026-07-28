"""Report shell for the cross-market variance-risk-premium prototype.

Question: Dew-Becker & Giglio (Chicago Fed WP 2025-17) find the US index-option variance
risk premium's CAPM alpha collapsed to zero at a structural break dated August 2012. Does
the US raw variance gap (implied minus forward-realized volatility — NOT the same object
as their risk-adjusted alpha; see README.md "What this can and cannot establish") flatten
uniquely around that date, or do other markets' raw gaps flatten too?

Two modes:
  --probe (default): check which candidate volatility-index tickers are actually
    retrievable via yfinance and print a coverage table. No structural-break analysis —
    this is the "do not assume, check" step the brief asked for, kept runnable rather
    than only recorded as a point-in-time README table.
  --live: load every market in universe.MARKETS via yfinance, plus Europe from
    eu_variance_premium's checked-in VSTOXX fixture, run the *same* pre/post-2012-08
    structural-break test on each market's raw gap (one break date, one horizon, one lag
    count — see --break-date/--horizon/--lags — applied identically everywhere, not
    tuned per market), and compare each non-US market's change against the US's.

Unlike eu_variance_premium, there is no synthetic mode here. The statistical mechanism
(variance_gap / newey_west_mean_test / structural_break_test) was already verified there
against synthetic data with a known embedded gap; this prototype's job is establishing
what real free data covers and what it shows, which a synthetic series cannot speak to.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from _prototyping.eu_variance_premium import model as m
from _prototyping.eu_variance_premium import stoxx_history as sh
from _prototyping.eu_variance_premium import yahoo_history as yh

from . import cross_market as cm
from . import market_history as mh
from .universe import FAILED_CANDIDATES, MARKETS, TOO_SHORT_FOR_A_PRE_2012_COMPARISON

BOLD = "\x1b[1m"
DIM = "\x1b[2m"
RESET = "\x1b[0m"

DEFAULT_CACHE_DIR = Path(__file__).parent / ".cache"
US_LABEL = "US (S&P 500)"
EUROPE_LABEL = "Europe (EURO STOXX 50 / VSTOXX)"

# Non-US markets the cross-sectional "does the US differ from everyone else" question
# is actually asked about. US-Nasdaq/US-Dow are robustness checks on the US result
# itself, not distinct countries, so they are reported but not cross-compared.
CROSS_MARKET_LABELS = ("India (Nifty 50)", "Australia (ASX 200)", EUROPE_LABEL)


def main() -> None:
    arguments = _arguments()
    if arguments.live:
        _run_live(arguments)
    else:
        _run_probe(arguments)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cross-market variance-risk-premium structural-break prototype"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="load every market and run the pre/post-2012-08 structural-break "
        "comparison (default: --probe only, no analysis)",
    )
    parser.add_argument(
        "--start", default="1990-01-01", help="live mode: history start"
    )
    parser.add_argument(
        "--end", default=None, help="live mode: history end (default: today)"
    )
    parser.add_argument("--break-date", default=m.DEFAULT_BREAK_DATE)
    parser.add_argument(
        "--horizon",
        type=int,
        default=m.VSTOXX_HORIZON_TRADING_DAYS,
        help="forward realized-vol window in trading days, applied identically to "
        "every market (default 21 = the 30-calendar-day constant maturity all these "
        "vol indices are documented to share — not tuned per market)",
    )
    parser.add_argument(
        "--lags",
        type=int,
        default=None,
        help="Newey-West lag length (default: horizon - 1, matching the overlap)",
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--refresh", action="store_true", help="ignore the local cache and refetch"
    )
    return parser.parse_args()


def _run_probe(arguments: argparse.Namespace) -> None:
    print(f"{BOLD}PROTOTYPE — cross-market variance risk premium (PROBE){RESET}")
    print(
        f"{DIM}Checking which candidate volatility-index and equity-index tickers are "
        f"actually retrievable via yfinance. No analysis runs in this mode; use --live "
        f"for the structural-break comparison.{RESET}\n"
    )
    print(f"{BOLD}Included markets — vol ticker / equity ticker{RESET}")
    for spec in MARKETS:
        for ticker in (spec.vol_ticker, spec.equity_ticker):
            result = mh.probe_ticker(ticker, end=arguments.end)
            _print_probe_row(f"{spec.label}", ticker, result)
    print(f"\n{BOLD}Excluded — real ticker, but history starts after the break{RESET}")
    for label, ticker, why in TOO_SHORT_FOR_A_PRE_2012_COMPARISON:
        result = mh.probe_ticker(ticker, end=arguments.end)
        _print_probe_row(label, ticker, result, extra=why)
    print(
        f"\n{BOLD}Tried and not usable (empty, delisted, or garbage single-row data){RESET}"
    )
    for label, ticker in FAILED_CANDIDATES:
        result = mh.probe_ticker(ticker, end=arguments.end)
        _print_probe_row(label, ticker, result)


def _print_probe_row(
    label: str, ticker: str, result: mh.ProbeResult, *, extra: str = ""
) -> None:
    if result.available:
        status = f"OK  {result.start}..{result.end} ({result.observations} obs)"
    else:
        status = f"FAIL  {result.detail}"
    suffix = f"  {DIM}{extra}{RESET}" if extra else ""
    print(f"  {label:38s} {ticker:14s} {status}{suffix}")


def _run_live(arguments: argparse.Namespace) -> None:
    print(f"{BOLD}PROTOTYPE — cross-market variance risk premium (LIVE){RESET}")
    print(
        f"{DIM}NOT a risk-adjusted alpha test: every gap below is implied minus "
        f"forward-realized volatility, which is compensation for market beta as well as "
        f"any true premium. See README.md for what this design can and cannot "
        f"establish.{RESET}\n"
    )
    end = arguments.end or _today()
    lags = arguments.lags if arguments.lags is not None else arguments.horizon - 1

    results: dict[str, m.StructuralBreakResult] = {}

    for spec in MARKETS:
        market = mh.load_market(
            spec,
            start=arguments.start,
            end=end,
            cache_dir=arguments.cache_dir,
            refresh=arguments.refresh,
        )
        results[spec.label] = _report_market(
            market.label,
            market.vol_ticker,
            market.equity_ticker,
            market.vol_level,
            market.equity_log_returns,
            arguments.break_date,
            arguments.horizon,
            lags,
            vol_note=f"{market.vol_source}/{market.equity_source}",
        )

    europe = _load_europe(arguments, end)
    if europe is not None:
        vol_level, log_returns, vol_note = europe
        results[EUROPE_LABEL] = _report_market(
            EUROPE_LABEL,
            "V2TX (fixture)",
            "^STOXX50E",
            vol_level,
            log_returns,
            arguments.break_date,
            arguments.horizon,
            lags,
            vol_note=vol_note,
        )

    _report_cross_market(results)


def _load_europe(arguments: argparse.Namespace, end: str):
    vstoxx = sh.load_vstoxx_history()
    sx5e = yh.load_log_returns(
        "^STOXX50E",
        arguments.start,
        end,
        cache_dir=arguments.cache_dir,
        refresh=arguments.refresh,
    )
    note = (
        f"VSTOXX frozen at {vstoxx.end} (STOXX fixture, never re-fetched — see "
        f"eu_variance_premium/README.md) / {sx5e.source}"
    )
    return vstoxx.level, sx5e.series, note


def _report_market(
    label: str,
    vol_ticker: str,
    equity_ticker: str,
    vol_level,
    log_returns,
    break_date: str,
    horizon: int,
    lags: int,
    *,
    vol_note: str,
) -> m.StructuralBreakResult | None:
    print(f"{BOLD}{label}{RESET}  ({vol_ticker} / {equity_ticker}, {vol_note})")
    try:
        gap = m.variance_gap(vol_level, log_returns, horizon=horizon)
    except m.InsufficientHistory as error:
        print(f"  UNTESTABLE: {error}\n")
        return None
    try:
        result = m.structural_break_test(gap["gap_vol_points"], break_date, lags)
    except m.InsufficientHistory as error:
        print(f"  UNTESTABLE: {error}\n")
        return None
    print(f"  break date: {result.break_date}")
    print(
        f"  pre  [{result.pre.observations:>5} obs]: mean={result.pre.mean:+.2f} "
        f"vol-pts  se={result.pre.standard_error:.2f}  t={result.pre.t_statistic:+.2f}  "
        f"p={result.pre.p_value:.4f}"
    )
    print(
        f"  post [{result.post.observations:>5} obs]: mean={result.post.mean:+.2f} "
        f"vol-pts  se={result.post.standard_error:.2f}  t={result.post.t_statistic:+.2f}  "
        f"p={result.post.p_value:.4f}"
    )
    print(
        f"  change (post - pre): {result.difference:+.2f} vol-pts  "
        f"t={result.difference_t_statistic:+.2f}  p={result.difference_p_value:.4f}"
    )
    if result.pre.observations < 250 or result.post.observations < 250:
        print(
            f"  {DIM}caveat: one side has under a year of sessions; treat as "
            f"indicative only{RESET}"
        )
    print()
    return result


def _report_cross_market(results: dict[str, m.StructuralBreakResult]) -> None:
    print(
        f"{BOLD}Cross-market comparison — is the US change distinguishable "
        f"from each other market's?{RESET}"
    )
    print(
        f"{DIM}Independent-samples z-test on the two markets' post-minus-pre changes. "
        f"Treats the markets as statistically independent, which understates their "
        f"true (positive) covariance and so is an optimistic bound on distinguishability "
        f"— see cross_market.py.{RESET}"
    )
    us_result = results.get(US_LABEL)
    if us_result is None:
        print("  UNTESTABLE: no US result to compare against.")
        return
    for label in CROSS_MARKET_LABELS:
        other_result = results.get(label)
        if other_result is None:
            print(f"  {label}: UNTESTABLE (no result)")
            continue
        comparison = cm.compare_break_changes(
            us_result, other_result, reference_label=US_LABEL, other_label=label
        )
        print(
            f"  US change {comparison.reference_change:+.2f} vs {label} change "
            f"{comparison.other_change:+.2f} vol-pts  "
            f"(difference {comparison.difference_of_changes:+.2f}, "
            f"z={comparison.z_statistic:+.2f}, p={comparison.p_value:.4f})"
        )


def _today() -> str:
    import datetime as _datetime

    return _datetime.date.today().isoformat()


if __name__ == "__main__":
    main()
