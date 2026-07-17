"""PROTOTYPE (throwaway) — Gate 1: weekly serial dependence, broad-commodity line.

Pre-registered spec in README.md. Run from aegis-rd/:
    uv run python scripts/prototype_ordinary_market_gates/gate1_commodity_vr.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from data_lines import bcom_index_close, catalog_close  # noqa: E402
from serial_dependence import variance_ratio_test  # noqa: E402

WEEKLY_K = (2, 4, 8, 13)
MONTHLY_K = (2, 3, 6, 12)
DAILY_K = (2, 5, 10, 20)

BOLD, DIM, END = "\x1b[1m", "\x1b[2m", "\x1b[0m"


def log_returns(close: pd.Series, freq: str | None) -> np.ndarray:
    if freq is not None:
        close = close.resample(freq).last().dropna()
    return np.log(close).diff().dropna().to_numpy()


def report(label: str, returns: np.ndarray, horizons: tuple[int, ...]) -> None:
    res = variance_ratio_test(returns, horizons)
    cells = "  ".join(
        f"VR({k})={v:.3f} z={z:+.2f} p={p:.3f}"
        for k, v, z, p in zip(res.horizons, res.vr, res.m2, res.p_horizon)
    )
    print(f"  {label:<44} n={res.n:>5}  {cells}")
    print(f"  {'':<44} joint MV={res.joint_stat:.2f}  {BOLD}joint p={res.p_joint:.4f}{END}")


def weekly_effect_bp(close: pd.Series) -> tuple[float, float]:
    r = log_returns(close, "W-FRI")
    res = variance_ratio_test(r, WEEKLY_K, n_boot=1)  # only VR(2) point estimate needed
    rho1 = res.vr[0] - 1
    return rho1, abs(rho1) * np.abs(r).mean() * 1e4


def main() -> None:
    print(f"{BOLD}Gate 1 — wild-bootstrap VR tests (B=4999, seed 42){END}")

    icom = catalog_close("ICOM.LSEETF-1-DAY-LAST-EXTERNAL")
    bcom = bcom_index_close()
    print(f"{DIM}ICOM {icom.index[0].date()}..{icom.index[-1].date()} ({icom.size} d)  "
          f"^BCOM {bcom.index[0].date()}..{bcom.index[-1].date()} ({bcom.size} d){END}\n")

    print(f"{BOLD}ICOM.LSEETF (the line; full sample = post-2006 by construction){END}")
    report("weekly, full (GATE)", log_returns(icom, "W-FRI"), WEEKLY_K)
    report("monthly, full", log_returns(icom, "ME"), MONTHLY_K)
    report("daily, full (context, below cost wall)", log_returns(icom, None), DAILY_K)
    sub_a, sub_b = icom.loc[:"2021-06-30"], icom.loc["2021-07-01":]
    report("weekly, sub-window 2018-01..2021-06", log_returns(sub_a, "W-FRI"), WEEKLY_K)
    report("weekly, sub-window 2021-07..2024-12", log_returns(sub_b, "W-FRI"), WEEKLY_K)

    print(f"\n{BOLD}^BCOM index (cross-check){END}")
    post = bcom.loc["2006-01-01":]
    report("weekly, post-2006", log_returns(post, "W-FRI"), WEEKLY_K)
    report("monthly, post-2006", log_returns(post, "ME"), MONTHLY_K)
    report("daily, post-2006 (context)", log_returns(post, None), DAILY_K)
    report("daily, pre-2006 (contrast)", log_returns(bcom.loc[:"2005-12-31"], None), DAILY_K)
    report("weekly, sub 2006-01..2016-06", log_returns(post.loc[:"2016-06-30"], "W-FRI"), WEEKLY_K)
    report("weekly, sub 2016-07..2026-07", log_returns(post.loc["2016-07-01":], "W-FRI"), WEEKLY_K)

    print(f"\n{BOLD}Effect size vs the 15-75bp cost wall{END}")
    for name, series in [("ICOM", icom), ("^BCOM post-2006", bcom.loc["2006-01-01":])]:
        rho1, bp = weekly_effect_bp(series)
        print(f"  {name:<18} weekly rho1={rho1:+.4f}  implied |edge| ~ {bp:.1f} bp/event")

    print(f"\n{BOLD}Verdict inputs (pre-registered criteria){END}")
    full = variance_ratio_test(log_returns(icom, "W-FRI"), WEEKLY_K)
    sa = variance_ratio_test(log_returns(sub_a, "W-FRI"), WEEKLY_K, n_boot=1)
    sb = variance_ratio_test(log_returns(sub_b, "W-FRI"), WEEKLY_K, n_boot=1)
    promote = full.p_joint < 0.05 and full.vr[0] < 1 and sa.vr[0] < 1 and sb.vr[0] < 1
    print(f"  ICOM weekly joint p={full.p_joint:.4f}, VR(2)={full.vr[0]:.3f}, "
          f"sub-window VR(2): {sa.vr[0]:.3f} / {sb.vr[0]:.3f}")
    print(f"  -> {BOLD}{'PROMOTE' if promote else 'KILL'}{END}")


if __name__ == "__main__":
    main()
