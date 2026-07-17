"""PROTOTYPE (throwaway) — headless falsification-ladder report.

QUESTION UNDER TEST: Does the exact long/short stock-Treasury strategy from
Harvey, Mazzoleni and Melone still exhibit economically usable mandated-
rebalancing alpha in recent and post-publication data, after correct timing and
realistic costs, and does its aligned return stream improve the existing slow
non-equity trend strategy (Atalanta)?

Run:  uv run python tmp/prototype_mandated_rebalancing/report.py
      (fetch data first: uv run python tmp/prototype_mandated_rebalancing/data.py fetch)

Prints the five falsification stages in order with the evidence each verdict
rests on. Later stages are still printed when an earlier gate fails, but the
final decision takes the FIRST failure (the handoff's stop rule).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import atalanta as atalanta_bridge
import data as data_layer
import engine

POST_PUBLICATION_START = "2025-01-01"  # paper public early 2025 (assumption)
LG_WINDOW = ("2020-01-01", "2025-06-30")  # the practitioner null window
SLEEVE_USD = 11_000.0  # ~EUR 10k

PAIRING_WINDOWS = [
    ("2018 fast gap (assumed 2018-01..2018-04)", "2018-01-01", "2018-04-30"),
    ("2020 V-reversal (assumed 2020-02..2020-05)", "2020-02-01", "2020-05-31"),
    ("2022 joint stock/bond selloff", "2022-01-01", "2022-12-31"),
    ("quiet/whipsaw (assumed 2023-05..2024-06)", "2023-05-01", "2024-06-30"),
]


def window_mask(dates: pd.DatetimeIndex, start: str | None, end: str | None):
    mask = np.ones(len(dates), dtype=bool)
    if start:
        mask &= dates >= pd.Timestamp(start)
    if end:
        mask &= dates <= pd.Timestamp(end)
    return mask


def line(char: str = "-") -> None:
    print(char * 78)


def fmt_backtest(result: engine.BacktestResult) -> str:
    return (
        f"CAGR {result.cagr * 100:6.2f}%  vol {result.volatility * 100:5.2f}%  "
        f"Sharpe {result.sharpe:5.2f}  skew {result.skew:5.2f}  "
        f"maxDD {result.max_drawdown * 100:6.2f}%  "
        f"turnover {result.annual_turnover:5.1f}x/yr  "
        f"cost {result.annual_cost_drag * 100:5.2f}%/yr"
    )


def fmt_regression(reg: engine.RegressionResult) -> str:
    return (
        f"n={reg.observations:5d}  beta {reg.bp_per_sd:+7.1f} bp/sd  "
        f"NW t {reg.t_stat:6.2f}"
    )


def _stats_only(
    dates: pd.DatetimeIndex,
    returns: np.ndarray,
    gross: np.ndarray | None = None,
    weights: np.ndarray | None = None,
) -> engine.BacktestResult:
    """Stats over already-realized daily strategy returns (no re-lagging).

    Turnover/cost inside the window are recovered from the source backtest's
    gross-net gap and weight path when provided (window entry counts as a trade).
    """
    import math

    if len(returns) == 0:
        raise ValueError("empty window")
    equity = np.cumprod(1.0 + returns)
    drawdown = equity / np.maximum.accumulate(equity) - 1.0
    years = len(returns) / engine.TRADING_DAYS
    std = float(np.std(returns, ddof=1))
    turnover = 0.0
    cost = 0.0
    if weights is not None and years > 0:
        traded = np.abs(np.diff(np.concatenate([[0.0], weights])))
        turnover = float(np.sum(traded) * 2.0 / years)
    if gross is not None and years > 0:
        cost = float(np.sum(gross - returns) / years)
    return engine.BacktestResult(
        dates=dates,
        returns=returns,
        gross_returns=returns if gross is None else gross,
        weights=np.zeros_like(returns) if weights is None else weights,
        observations=len(returns),
        cagr=float(equity[-1] ** (1.0 / years) - 1.0) if years > 0 else 0.0,
        volatility=std * math.sqrt(engine.TRADING_DAYS),
        sharpe=float(np.mean(returns) / std * math.sqrt(engine.TRADING_DAYS))
        if std > 0
        else 0.0,
        skew=float(pd.Series(returns).skew()),
        max_drawdown=float(np.min(drawdown)),
        annual_turnover=turnover,
        annual_cost_drag=cost,
    )


def main() -> None:
    line("=")
    print("MANDATED-REBALANCING ALPHA - FALSIFICATION LADDER (throwaway prototype)")
    line("=")

    series = data_layer.load_market_inputs()
    print("\nDATA PROVENANCE")
    dates_fut, stock_fut, bond_fut, notes_fut = data_layer.spread_inputs(
        series, extend_proxy=False
    )
    dates_ext, stock_ext, bond_ext, notes_ext = data_layer.spread_inputs(
        series, extend_proxy=True
    )
    for note in notes_ext:
        print("  *", note)
    for note in data_layer.cross_checks(series):
        print("  *", note)
    if (data_layer.CACHE_DIR / "ibkr_es.csv").exists():
        print("  * futures source: IBKR CONTFUT (repository standard)")
    else:
        print(
            "  * GAP: IBKR historical farm rejected requests (competing session);"
            " using Yahoo continuous futures until `data.py fetch` succeeds on IBKR"
        )

    # Signals built once per universe; windows slice realized returns (frozen rule).
    signals_fut = engine.build_signals(dates_fut, stock_fut, bond_fut)
    signals_ext = engine.build_signals(dates_ext, stock_ext, bond_ext)
    spread_fut = stock_fut - bond_fut
    spread_ext = stock_ext - bond_ext

    frozen_fut = engine.run_backtest(
        dates_fut, stock_fut, bond_fut, signals_fut.weight_combined, engine.GROSS
    )
    frozen_ext = engine.run_backtest(
        dates_ext, stock_ext, bond_ext, signals_ext.weight_combined, engine.GROSS
    )

    # ------------------------------------------------------------------ stage 1
    line()
    print("STAGE 1 - REPRODUCTION CORRECTNESS (gross, exact close-to-next lag)")
    line()
    paper_fut_mask = window_mask(dates_fut, None, data_layer.PAPER_END)
    paper_ext_mask = window_mask(
        dates_ext, data_layer.PAPER_START, data_layer.PAPER_END
    )
    to_end_fut = engine.sessions_to_month_end(dates_fut)
    pressure_mask = (to_end_fut >= 1) & (to_end_fut <= engine.CALENDAR_WINDOW - 1)

    reg_threshold = engine.predictive_regression(
        signals_fut.threshold[paper_fut_mask], spread_fut[paper_fut_mask]
    )
    reg_calendar = engine.predictive_regression(
        np.where(pressure_mask, signals_fut.calendar, np.nan)[paper_fut_mask],
        spread_fut[paper_fut_mask],
    )
    print(f"  threshold signal -> next-day spread   {fmt_regression(reg_threshold)}")
    print(f"  calendar (pressure days only)         {fmt_regression(reg_calendar)}")
    print("  paper target: negative sign, ~-17bp equity/+2-4bp bond per sd, t~4")
    print()
    for label, signal_weights in (
        ("threshold", signals_fut.weight_threshold),
        ("calendar ", signals_fut.weight_calendar),
        ("combined ", signals_fut.weight_combined),
    ):
        result = engine.run_backtest(
            dates_fut, stock_fut, bond_fut, signal_weights, engine.GROSS
        )
        windowed = _stats_only(
            result.dates[paper_fut_mask],
            result.returns[paper_fut_mask],
            result.gross_returns[paper_fut_mask],
            result.weights[paper_fut_mask],
        )
        print(f"  {label} {dates_fut[paper_fut_mask][0].date()}"
              f"..{dates_fut[paper_fut_mask][-1].date()}  {fmt_backtest(windowed)}")
    ext_windowed = _stats_only(
        frozen_ext.dates[paper_ext_mask],
        frozen_ext.returns[paper_ext_mask],
        frozen_ext.gross_returns[paper_ext_mask],
        frozen_ext.weights[paper_ext_mask],
    )
    print(f"  combined + proxy 1997 extension       {fmt_backtest(ext_windowed)}")
    print("  replication targets: futures Sharpe 0.94 (Quantitativo) / 1.24 (QuantReturns)")

    stage1_backtest = _stats_only(
        frozen_fut.dates[paper_fut_mask],
        frozen_fut.returns[paper_fut_mask],
        frozen_fut.gross_returns[paper_fut_mask],
        frozen_fut.weights[paper_fut_mask],
    )
    verdict1 = engine.stage1_reproduction(reg_threshold, stage1_backtest)
    print(f"\n  VERDICT: {'PASS' if verdict1.passed else 'FAIL' if verdict1.passed is False else 'UNDECIDABLE'} - {verdict1.detail}")

    # Long-only negative control (context, not a gate)
    w_stock_lo, w_bond_lo = engine.long_only_control_weights(
        dates_fut, stock_fut, bond_fut
    )
    control = engine.run_two_leg_backtest(
        dates_fut, stock_fut, bond_fut, w_stock_lo, w_bond_lo, engine.GROSS
    )
    control_paper = _stats_only(
        control.dates[paper_fut_mask],
        control.returns[paper_fut_mask],
        control.gross_returns[paper_fut_mask],
        control.weights[paper_fut_mask],
    )
    print(f"  [control] long-only loser rule        {fmt_backtest(control_paper)}")
    print("  [control] practitioner report: Sharpe ~0.78 pre-cost, 20y")

    # ------------------------------------------------------------------ stage 2
    line()
    print("STAGE 2 - RECENCY AND DECAY (frozen combined rule, gross, exact lag)")
    line()
    recency_windows = [
        ("pre-2020        ", None, "2019-12-31"),
        ("2020-2023       ", "2020-01-01", "2023-12-31"),
        ("2024-latest     ", "2024-01-01", None),
        ("post-publication", POST_PUBLICATION_START, None),
        ("L&G null window ", *LG_WINDOW),
    ]
    recent_results: dict[str, tuple[engine.RegressionResult, engine.BacktestResult]] = {}
    for label, start, end in recency_windows:
        mask = window_mask(dates_fut, start, end)
        if mask.sum() < 40:
            print(f"  {label}  insufficient observations ({mask.sum()})")
            continue
        regression = engine.predictive_regression(
            signals_fut.threshold[mask], spread_fut[mask]
        )
        windowed = _stats_only(
            frozen_fut.dates[mask],
            frozen_fut.returns[mask],
            frozen_fut.gross_returns[mask],
            frozen_fut.weights[mask],
        )
        recent_results[label.strip()] = (regression, windowed)
        print(f"  {label}  {fmt_regression(regression)}  Sharpe {windowed.sharpe:5.2f}"
              f"  CAGR {windowed.cagr * 100:6.2f}%")
        if label.startswith("L&G") and regression.t_stat < -2:
            print("                    ^ our public-data run does NOT reproduce the"
                  " L&G null on their window; the decay is concentrated in 2024+")
    print("\n  L&G practitioner claim: no signal-return relationship 2020-01..2025-06")

    reg_recent, bt_recent = recent_results.get(
        "post-publication", recent_results["2024-latest"]
    )
    verdict2 = engine.stage2_recency(reg_recent, bt_recent)
    print(f"\n  VERDICT: {'PASS' if verdict2.passed else 'FAIL' if verdict2.passed is False else 'UNDECIDABLE'} - {verdict2.detail}")

    # ------------------------------------------------------------------ stage 3
    line()
    print("STAGE 3 - IMPLEMENTABLE ECONOMICS")
    line()
    scenarios = [
        ("gross, exact lag      ", engine.GROSS, 0),
        ("realistic, exact lag  ", engine.FUTURES_REALISTIC, 0),
        ("realistic, +1 session ", engine.FUTURES_REALISTIC, 1),
    ]
    modern_mask = window_mask(dates_fut, "2020-01-01", None)
    stage3_result: engine.BacktestResult | None = None
    for label, costs, delay in scenarios:
        result = engine.run_backtest(
            dates_fut, stock_fut, bond_fut, signals_fut.weight_combined, costs, delay
        )
        full = _stats_only(
            result.dates, result.returns, result.gross_returns, result.weights
        )
        recent = _stats_only(
            result.dates[modern_mask],
            result.returns[modern_mask],
            result.gross_returns[modern_mask],
            result.weights[modern_mask],
        )
        print(f"  research spread  {label} full: {fmt_backtest(full)}")
        print(f"                   {'':22} 2020+: Sharpe {recent.sharpe:5.2f}"
              f"  CAGR {recent.cagr * 100:6.2f}%  cost {result.annual_cost_drag * 100:5.2f}%/yr")
        if costs is engine.FUTURES_REALISTIC and delay == 0:
            stage3_result = recent
    print("  (delay case: signals anchor to US close; European-hours execution adds a session)")
    print()
    qspx_notional, mtn_notional, notional_notes = data_layer.contract_notionals(
        series, dates_fut
    )
    for note in notional_notes:
        print("  *", note)
    tn_mask = window_mask(dates_fut, "2010-11-01", None)
    integer_result = engine.run_integer_contract_backtest(
        dates_fut[tn_mask],
        stock_fut[tn_mask],
        (data_layer.futures_returns(series["tn"]).reindex(dates_fut[tn_mask]).fillna(0.0).to_numpy()
         if series["tn"] is not None
         else bond_fut[tn_mask]),
        signals_fut.weight_combined[tn_mask],
        qspx_notional[tn_mask].to_numpy(),
        mtn_notional[tn_mask].to_numpy(),
        SLEEVE_USD,
    )
    print(f"  QSPX-MTN integer ({SLEEVE_USD:,.0f} USD sleeve, SYNTHETIC TN-proxy era 2010+):")
    print(f"    {fmt_backtest(integer_result.backtest)}")
    print(f"    contracts |stock| {integer_result.mean_stock_contracts:.1f}"
          f"  |bond| {integer_result.mean_bond_contracts:.1f}"
          f"  max gross leverage {integer_result.max_gross_leverage:.2f}x"
          f"  TE vs research {integer_result.tracking_error_vs_spread * 100:.2f}%/yr")
    if series.get("qspx") is not None and series.get("mtn") is not None:
        qspx_returns = data_layer.futures_returns(series["qspx"])
        mtn_returns = data_layer.futures_returns(series["mtn"])
        joined = pd.concat(
            [qspx_returns.rename("stock"), mtn_returns.rename("bond")],
            axis=1, join="inner",
        ).dropna()
        overlap = joined.index.intersection(dates_fut)
        if len(overlap) > 60:
            signal_series = pd.Series(signals_fut.weight_combined, index=dates_fut)
            actual = engine.run_integer_contract_backtest(
                pd.DatetimeIndex(overlap),
                joined.loc[overlap, "stock"].to_numpy(),
                joined.loc[overlap, "bond"].to_numpy(),
                signal_series.reindex(overlap).to_numpy(),
                series["qspx"].reindex(overlap).ffill().to_numpy(),
                (series["mtn"].reindex(overlap).ffill() * 100.0).to_numpy(),
                SLEEVE_USD,
            )
            print(f"  QSPX-MTN integer, ACTUAL IBKR quotes "
                  f"({overlap[0].date()}..{overlap[-1].date()}, n={len(overlap)}):")
            print(f"    {fmt_backtest(actual.backtest)}")
            print(f"    contracts |stock| {actual.mean_stock_contracts:.1f}"
                  f"  |bond| {actual.mean_bond_contracts:.1f}"
                  f"  max gross leverage {actual.max_gross_leverage:.2f}x"
                  f"  TE vs research {actual.tracking_error_vs_spread * 100:.2f}%/yr")
            if series.get("tn") is not None:
                tn_returns = data_layer.futures_returns(series["tn"])
                tracked = pd.concat(
                    [mtn_returns.rename("mtn"), tn_returns.rename("tn")],
                    axis=1, join="inner",
                ).dropna()
                if len(tracked) > 60:
                    print(f"    MTN vs TN (Ultra 10y) daily corr "
                          f"{tracked.corr().iloc[0, 1]:.3f} on n={len(tracked)}")
            print("    (window too short for a significance claim; liquidity/tracking evidence only)")
        else:
            print("  QSPX-MTN actual quotes: insufficient overlap with signal history")
    else:
        print("    GAP: actual QSPX/MTN quotes not in cache (IBKR fetch required)")
    print("    Ultra-10y duration mismatch vs the paper's conventional 10y: see cross-checks")

    assert stage3_result is not None
    verdict3 = engine.stage3_implementable(stage3_result)
    print(f"\n  VERDICT (research spread, realistic costs, 2020+): "
          f"{'PASS' if verdict3.passed else 'FAIL' if verdict3.passed is False else 'UNDECIDABLE'} - {verdict3.detail}")

    # ------------------------------------------------------------------ stage 4
    line()
    print("STAGE 4 - ATALANTA PAIRING (established floor-pair measure)")
    line()
    candidate = engine.run_backtest(
        dates_fut, stock_fut, bond_fut, signals_fut.weight_combined,
        engine.FUTURES_REALISTIC,
    )
    candidate_daily = candidate.series()
    atalanta_daily = atalanta_bridge.load_atalanta_daily()
    ce_delta: float | None = None
    worst_decile_mean: float | None = None
    if atalanta_daily is None:
        print("  Atalanta stream unavailable - pairing undecidable (no proxy fabricated)")
    else:
        print("  NOTE: Atalanta is EUR-base production net returns; candidate is a USD")
        print("  futures excess overlay - same-dates alignment, not a currency-merged book")
        pairing = atalanta_bridge.evaluate_pairing(atalanta_daily, candidate_daily)
        common = pairing["common_history"]
        print(f"  common monthly history {common['start']}..{common['end']}"
              f"  ({common['observations']} months)")
        dependence = pairing["dependence"]
        comparison = pairing["comparison"]
        delta = comparison["delta"]
        ce_delta = delta["mppm_certainty_equivalent"]
        worst_decile_mean = dependence["carry_mean_in_trend_worst_decile"]
        print(f"  aligned monthly correlation {dependence['full_sample_correlation']:+.3f}"
              f"  (H1 gate <= 0.2)")
        print(f"  candidate mean in Atalanta worst-decile months {worst_decile_mean:+.4f}"
              f"  (n={dependence['trend_worst_decile_observations']})")
        print(f"  mix (60/40) vs Atalanta alone: Sharpe {delta['sharpe']:+.3f}"
              f"  MPPM CE {ce_delta:+.4f}  maxDD {delta['max_drawdown'] * 100:+.2f}pp"
              f"  skew {delta['skew']:+.2f}")
        for row in pairing["bootstrap"]:
            print(f"  bootstrap (block {row['block_length_months']}m): CE delta 95%"
                  f" [{row['mppm_delta_interval_95'][0]:+.4f},"
                  f" {row['mppm_delta_interval_95'][1]:+.4f}]  Sharpe delta 95%"
                  f" [{row['sharpe_delta_interval_95'][0]:+.3f},"
                  f" {row['sharpe_delta_interval_95'][1]:+.3f}]")
        print("\n  named regime windows (candidate vs Atalanta compounded return):")
        for label, start, end in PAIRING_WINDOWS:
            cand_mask = (candidate_daily.index >= start) & (candidate_daily.index <= end)
            atal_mask = (atalanta_daily.index >= start) & (atalanta_daily.index <= end)
            if cand_mask.sum() < 10 or atal_mask.sum() < 10:
                print(f"    {label}: insufficient overlap")
                continue
            cand_total = float(np.prod(1 + candidate_daily[cand_mask]) - 1)
            atal_total = float(np.prod(1 + atalanta_daily[atal_mask]) - 1)
            print(f"    {label}: candidate {cand_total * 100:+6.2f}%"
                  f"  Atalanta {atal_total * 100:+6.2f}%")

    verdict4 = engine.stage4_pairing(ce_delta, worst_decile_mean)
    print(f"\n  VERDICT: {'PASS' if verdict4.passed else 'FAIL' if verdict4.passed is False else 'UNDECIDABLE'} - {verdict4.detail}")

    # ------------------------------------------------------------------ stage 5
    line("=")
    verdicts = [verdict1, verdict2, verdict3, verdict4]
    print("STAGE 5 - PROSPECTIVE DECISION")
    for verdict in verdicts:
        state = ("PASS" if verdict.passed else
                 "FAIL" if verdict.passed is False else "UNDECIDABLE")
        print(f"  {verdict.stage:16} {state:12} {verdict.detail}")
    line()
    print(f"  FINAL: {engine.final_decision(verdicts)}")
    line("=")


if __name__ == "__main__":
    main()
