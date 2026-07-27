#!/usr/bin/env python
"""PROTOTYPE - THROWAWAY. Tests a claim I made without checking, at the user's instruction.

CLAIM UNDER TEST
----------------
I asserted that in `demeter.carry_mix`

    exposure = min(vol_target / sigma_book * richness**carry_gain, 1.0)

the ``vol_target`` term is INERT in calm markets (capped at 1.0) and only becomes active in
stress - making it a pure crash-mute rather than a two-sided risk normaliser, which is the
shape `what-makes-a-convergent-sleeve-an-income-engine` warns removes the negative skew the
sleeve is paid for.

That was an inference from reading the code, not a measurement. This measures it.

WHAT IS REPLICATED (faithfully, from the component source)
  - realized_vol  = 21d (and 63d) rolling std of daily log returns * sqrt(252)   [demeter.realized_vol]
  - shares        = role-tilted inverse-vol, renormalised                        [carry_mix._weights]
  - sigma_book    = (shares * vol).sum(axis=1)  <- COMONOTONE approx, no diversification credit
  - exposure      = min(vol_target / max(sigma_book, 0.01) * lean, 1.0)

LIVE CONFIGURATION (book.toml:138 "SDHY + LQDH, USD legs converted to EUR")
  defensive=1.0 (short-duration HY replaces broad HY), fx_weight=0, at1_weight=0,
  vol_target=0.10 (pinned by mandate).

carry_gain is UNKNOWN for the live candidate (wheel ...cand_ff2), so lean is pinned to 1.0
to ISOLATE the vol_target term. That is the honest way to test the specific claim: if the
cap binds with lean=1, the richness lean can only pull exposure lower, never higher.

    uv run --with yfinance --with pandas --with numpy python _prototyping/voltarget_bind/probe.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eu_variance_premium.yahoo_history import load_close_series  # noqa: E402

VOL_TARGET = 0.10
MIN_VOL = 0.01
START, END = "2012-01-01", "2026-07-24"

# The live legs. Yahoo carries the London lines.
LEGS = {"SDHY.L": "iShares $ Short Duration HY", "LQDH.L": "iShares $ Corp Bond Rate-Hedged"}

STRESS = {
    "COVID crash": ("2020-02-19", "2020-04-30"),
    "2022 credit selloff": ("2022-01-01", "2022-10-31"),
    "SVB / Mar 2023": ("2023-03-01", "2023-04-15"),
}


def realized_vol(close: pd.DataFrame, window: int) -> pd.DataFrame:
    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(window).std(ddof=1) * np.sqrt(252.0)


def sleeve_exposure(vol: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Replicate carry_mix: inverse-vol shares -> comonotone sigma_book -> capped exposure."""
    v = vol.clip(lower=MIN_VOL)
    inv = (1.0 / v).where(np.isfinite(vol), 0.0)
    total = inv.sum(axis=1)
    shares = inv.div(total.where(total > 0, np.nan), axis=0)
    sigma_book = (shares * v).sum(axis=1)
    ratio = VOL_TARGET / sigma_book.clip(lower=MIN_VOL)  # lean pinned to 1.0
    return sigma_book, ratio.clip(upper=1.0)


def main() -> None:
    frames = {}
    for tkr in LEGS:
        load = load_close_series(tkr, start=START, end=END)
        frames[tkr] = load.series
        print(f"  loaded {tkr:<10} {load.observations:>5} obs  {load.source}")
    close = pd.DataFrame(frames).dropna(how="all").ffill().dropna()
    print(f"\n  common sample: {close.index[0].date()} -> {close.index[-1].date()}  ({len(close)} rows)\n")

    for window in (21, 63):
        vol = realized_vol(close, window)
        sigma_book, exposure = sleeve_exposure(vol)
        valid = exposure.dropna()
        capped = (valid >= 1.0 - 1e-12)

        print("=" * 74)
        print(f"vol_window = {window}d")
        print("=" * 74)
        print(f"  sigma_book (comonotone): median {sigma_book.median():.4f}  "
              f"p95 {sigma_book.quantile(0.95):.4f}  max {sigma_book.max():.4f}")
        print(f"  vol_target = {VOL_TARGET}")
        print(f"\n  DAYS CAPPED AT 1.0 (vol_target term INERT): {capped.sum()}/{len(valid)} "
              f"= {100.0 * capped.mean():.2f}%")
        print(f"  days where the term BINDS (exposure < 1):    {(~capped).sum()} "
              f"= {100.0 * (~capped).mean():.2f}%")
        if (~capped).any():
            binding = valid[~capped]
            print(f"    when binding: median exposure {binding.median():.3f}, "
                  f"min {binding.min():.3f}")
            years = binding.groupby(binding.index.year).size()
            print(f"    binding days by year: {years.to_dict()}")

        print("\n  exposure during stress windows:")
        for label, (a, b) in STRESS.items():
            seg = valid.loc[a:b]
            if seg.empty:
                print(f"    {label:<22} (no data)")
                continue
            print(f"    {label:<22} mean {seg.mean():.3f}  min {seg.min():.3f}  "
                  f"capped {100.0 * (seg >= 1.0 - 1e-12).mean():.0f}%")
        print()

    for window in (21, 63):
        counterfactual(close, window)


def counterfactual(close: pd.DataFrame, window: int) -> None:
    """Muted (vol_target live) vs unmuted (exposure pinned to 1.0), same shares.

    Weights are lagged one day: vol is computed on close t, the book can only hold it t+1.
    This is the question the shape test cannot answer - does the mute protect, or does it
    de-risk after the damage and then miss the recovery?
    """
    vol = realized_vol(close, window)
    _, exposure = sleeve_exposure(vol)
    v = vol.clip(lower=MIN_VOL)
    inv = (1.0 / v).where(np.isfinite(vol), 0.0)
    shares = inv.div(inv.sum(axis=1).replace(0.0, np.nan), axis=0)

    ret = close.pct_change()
    muted = (shares.mul(exposure, axis=0).shift(1) * ret).sum(axis=1)
    unmuted = (shares.shift(1) * ret).sum(axis=1)
    both = pd.DataFrame({"muted": muted, "unmuted": unmuted}).dropna()

    print("=" * 74)
    print(f"COUNTERFACTUAL  vol_window={window}d   muted (vol_target on) vs unmuted (exposure=1)")
    print("=" * 74)
    for name, r in both.items():
        eq = (1.0 + r).cumprod()
        dd = (eq / eq.cummax() - 1.0).min()
        ann = r.mean() * 252
        vol_a = r.std() * np.sqrt(252)
        print(f"  {name:<9} CAGR-ish {ann:+.3%}  vol {vol_a:.3%}  Sharpe {ann / vol_a:+.3f}  "
              f"maxDD {dd:+.3%}  skew {r.skew():+.3f}")

    print("\n  COVID window, daily:")
    seg = both.loc["2020-02-19":"2020-06-30"]
    for name, r in seg.items():
        eq = (1.0 + r).cumprod()
        trough = (eq / eq.cummax() - 1.0).min()
        print(f"    {name:<9} drawdown {trough:+.3%}   total return over window {eq.iloc[-1] - 1:+.3%}")
    crash = both.loc["2020-02-19":"2020-03-23"]
    rebound = both.loc["2020-03-24":"2020-06-30"]
    print(f"    crash leg   (19 Feb - 23 Mar): muted {(1 + crash['muted']).prod() - 1:+.3%}  "
          f"unmuted {(1 + crash['unmuted']).prod() - 1:+.3%}")
    print(f"    rebound leg (24 Mar - 30 Jun): muted {(1 + rebound['muted']).prod() - 1:+.3%}  "
          f"unmuted {(1 + rebound['unmuted']).prod() - 1:+.3%}")
    print()


if __name__ == "__main__":
    main()
