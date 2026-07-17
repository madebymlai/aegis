"""PROTOTYPE (throwaway) — Gate 2: dealer-gamma-conditioned autocorrelation.

Pre-registered spec in README.md. Run from aegis-rd/:
    uv run python scripts/prototype_ordinary_market_gates/gate2_gamma_autocorr.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from data_lines import catalog_close, squeezemetrics_frame  # noqa: E402
from serial_dependence import (  # noqa: E402
    ConditionalAcResult,
    conditional_autocorrelation,
    rolling_percentile_rank,
    terciles,
)

GROUPS = ("bottom", "mid", "top")
BOLD, DIM, END = "\x1b[1m", "\x1b[2m", "\x1b[0m"


def report(label: str, res: ConditionalAcResult) -> str:
    print(f"  {BOLD}{label}{END}  n={res.n}")
    for g, n, b, ab, sd in zip(res.groups, res.n_per_group, res.slope, res.mean_abs_r, res.stdev_r):
        print(f"    {g:<7} n={n:>5}  b={b:+.4f}  mean|r|={ab * 1e4:6.1f}bp  sd={sd * 1e4:6.1f}bp")
    verdict = "significant" if res.p_one_sided < 0.05 and res.delta_b < 0 else "not significant"
    print(f"    delta_b(top-bottom)={res.delta_b:+.4f}  one-sided p={res.p_one_sided:.4f}  ({verdict})")
    top_bp = abs(res.slope[2]) * res.mean_abs_r[2] * 1e4
    print(f"    {DIM}implied top-tercile fade edge ~ {top_bp:.1f} bp/event{END}")
    return verdict


def daily_frame(r: pd.Series, regime_pct: pd.Series, lag_regime: int) -> pd.DataFrame:
    df = pd.DataFrame({"r": r})
    df["r_next"] = df["r"].shift(-1)
    df["pct"] = regime_pct.reindex(df.index).shift(lag_regime)
    return df.dropna()


def run(df: pd.DataFrame, label: str) -> ConditionalAcResult:
    gid = terciles(df["pct"].to_numpy())
    res = conditional_autocorrelation(
        df["r"].to_numpy(), df["r_next"].to_numpy(), gid, GROUPS, bottom=0, top=2
    )
    report(label, res)
    return res


def main() -> None:
    print(f"{BOLD}Gate 2 — gamma-regime-conditioned lag-1 autocorrelation (B=4999, seed 42){END}")
    sq = squeezemetrics_frame()
    pct = pd.Series(
        rolling_percentile_rank(sq["gex"].to_numpy(), window=252, min_obs=126), index=sq.index
    )
    spx_r = np.log(sq["price"]).diff()
    print(f"{DIM}GEX/SPX {sq.index[0].date()}..{sq.index[-1].date()} ({len(sq)} d); "
          f"regime = rolling 252d percentile of GEX{END}\n")

    print(f"{BOLD}(a) US close-to-close — SPX{END}")
    spx = daily_frame(spx_r, pct, lag_regime=0)
    res_daily = run(spx, "daily, full")
    mid = spx.index[len(spx) // 2]
    res_sub1 = run(spx.loc[:mid], f"daily, sub ..{mid.date()}")
    res_sub2 = run(spx.loc[mid + pd.Timedelta(days=1):], f"daily, sub {mid.date()}..")

    wk_r = np.log(sq["price"].resample("W-FRI").last().dropna()).diff()
    wk_pct = pct.resample("W-FRI").mean()
    wk = pd.DataFrame({"r": wk_r, "r_next": wk_r.shift(-1), "pct": wk_pct}).dropna()
    res_weekly = run(wk, "weekly, full (regime = week-mean percentile)")

    print(f"\n{BOLD}(b) European-hours prints — CSPX.LSEETF (regime = GEX[t-1] tercile){END}")
    cspx = catalog_close("CSPX.LSEETF-1-DAY-LAST-EXTERNAL")
    cspx_r = np.log(cspx).diff()
    eu = daily_frame(cspx_r, pct, lag_regime=1)
    res_eu = run(eu, "daily, full 2018-01..2024-12")
    run(eu.loc[:"2021-06-30"], "daily, sub 2018-01..2021-06")
    run(eu.loc["2021-07-01":], "daily, sub 2021-07..2024-12")

    print(f"\n{BOLD}Robustness (reported, not a gate): GEX/SPX^2 full-sample terciles{END}")
    alt_pct = (sq["gex"] / sq["price"] ** 2).rank(pct=True)
    run(daily_frame(spx_r, alt_pct, lag_regime=0), "SPX daily, GEX/SPX^2 regime")

    print(f"\n{BOLD}Verdict inputs (pre-registered criteria){END}")
    a_holds = (
        (res_daily.p_one_sided < 0.05 and res_daily.delta_b < 0)
        or (res_weekly.p_one_sided < 0.05 and res_weekly.delta_b < 0)
    )
    stable = res_sub1.delta_b < 0 and res_sub2.delta_b < 0
    b_holds = res_eu.p_one_sided < 0.05 and res_eu.delta_b < 0
    print(f"  (a) daily p={res_daily.p_one_sided:.4f} weekly p={res_weekly.p_one_sided:.4f} "
          f"-> holds={a_holds}; sub-window delta_b {res_sub1.delta_b:+.4f}/{res_sub2.delta_b:+.4f} "
          f"-> stable={stable}")
    print(f"  (b) CSPX p={res_eu.p_one_sided:.4f} delta_b={res_eu.delta_b:+.4f} -> holds={b_holds}")
    promote = a_holds and stable and b_holds
    print(f"  -> {BOLD}{'PROMOTE' if promote else 'KILL'}{END}")


if __name__ == "__main__":
    main()
