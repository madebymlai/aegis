"""
PROTOTYPE v2 — throwaway.
Question: Does the RM ratio add independent gating value beyond the
momentum score, after controlling for asset class, OOS splits, RM
lookback, and transaction costs?

Run: .venv/bin/python research/prototypes/rm_vs_momentum_score_v2.py
"""

import numpy as np
import pandas as pd
import vectorbtpro as vbt

SYMBOLS = ["SPY", "IWM", "EEM", "TLT", "GLD", "DBC", "VNQ", "UUP", "XLE", "XLU"]
START = "2010-01-01"
END = "2025-12-31"
COST_BPS = 10  # one-way transaction cost in basis points
FWD_DAYS = 20
RM_LOOKBACKS = [126, 180, 210, 252]

ASSET_CLASSES = {
    "equity": ["SPY", "IWM", "EEM", "XLE", "XLU"],
    "bond": ["TLT"],
    "commodity": ["DBC", "GLD"],
    "currency": ["UUP"],
    "reit": ["VNQ"],
}
SYM_TO_CLASS = {}
for cls, syms in ASSET_CLASSES.items():
    for s in syms:
        SYM_TO_CLASS[s] = cls


def momentum_score(close: pd.DataFrame) -> pd.DataFrame:
    scores = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    for days, weight in [(21, 12), (63, 4), (126, 2), (252, 1)]:
        r = (close / close.shift(days)) ** (252 / days) - 1
        scores += weight * r
    return scores


def rm_ratio(close: pd.DataFrame, window: int) -> pd.DataFrame:
    return close / close.rolling(window).mean()


def fwd_return_with_cost(close: pd.DataFrame, fwd: int, cost_bps: int) -> pd.DataFrame:
    raw = close.pct_change(fwd).shift(-fwd)
    cost = cost_bps / 10_000 * 2  # round-trip
    return raw - cost


# --- rolling OOS splits ---
# 3-year IS window, 1-year OOS, rolling by 1 year
def make_oos_masks(index: pd.DatetimeIndex):
    years = index.year
    unique_years = sorted(years.unique())
    splits = []
    for i in range(3, len(unique_years)):
        oos_year = unique_years[i]
        is_years = [unique_years[i - 3], unique_years[i - 2], unique_years[i - 1]]
        is_mask = years.isin(is_years)
        oos_mask = years == oos_year
        splits.append((f"IS {is_years[0]}-{is_years[-1]} / OOS {oos_year}",
                        is_mask, oos_mask))
    return splits


print("Fetching data...")
data = vbt.YFData.pull(SYMBOLS, start=START, end=END, timeframe="1D", silence_warnings=True)
close = data.get("Close")

scores = momentum_score(close)
gate_score = scores > 0

fwd_ret = fwd_return_with_cost(close, FWD_DAYS, COST_BPS)

splits = make_oos_masks(close.index)

# =====================================================================
print()
print("=" * 78)
print("PART 1: RM lookback sweep — OOS only, per asset class")
print("=" * 78)

for rm_L in RM_LOOKBACKS:
    rm = rm_ratio(close, rm_L)
    gate_rm = rm > 1.0

    print(f"\n--- RM lookback = {rm_L}d ---")
    header = f"{'Asset class':<12} {'Both IN':>9} {'Score>RM':>9} {'RM>Score':>9} {'Both OUT':>9} | {'Agree%':>7} {'fwd BothIN':>10} {'fwd Sc>RM':>10} {'fwd RM>Sc':>10}"
    print(header)
    print("-" * len(header))

    for cls_name, cls_syms in ASSET_CLASSES.items():
        bi_n = so_n = ro_n = bo_n = 0
        bi_ret = []
        so_ret = []
        ro_ret = []

        for split_name, is_mask, oos_mask in splits:
            for sym in cls_syms:
                oos_idx = close.index[oos_mask]
                valid = gate_score[sym].loc[oos_idx].notna() & gate_rm[sym].loc[oos_idx].notna()
                oos_idx = oos_idx[valid]
                if len(oos_idx) == 0:
                    continue

                gs = gate_score[sym].loc[oos_idx]
                gr = gate_rm[sym].loc[oos_idx]
                fr = fwd_ret[sym].loc[oos_idx]

                bi = gs & gr
                so = gs & ~gr
                ro = ~gs & gr
                bo = ~gs & ~gr

                bi_n += bi.sum()
                so_n += so.sum()
                ro_n += ro.sum()
                bo_n += bo.sum()

                bi_ret.extend(fr[bi].dropna().tolist())
                so_ret.extend(fr[so].dropna().tolist())
                ro_ret.extend(fr[ro].dropna().tolist())

        total = bi_n + so_n + ro_n + bo_n
        agree_pct = (bi_n + bo_n) / total * 100 if total > 0 else 0

        bi_mean = np.mean(bi_ret) * 100 if bi_ret else float("nan")
        so_mean = np.mean(so_ret) * 100 if so_ret else float("nan")
        ro_mean = np.mean(ro_ret) * 100 if ro_ret else float("nan")

        print(f"{cls_name:<12} {bi_n:>9} {so_n:>9} {ro_n:>9} {bo_n:>9} | {agree_pct:>6.1f}% {bi_mean:>+9.2f}% {so_mean:>+9.2f}% {ro_mean:>+9.2f}%")


# =====================================================================
print()
print("=" * 78)
print("PART 2: Per-symbol detail at RM=252 — OOS splits only")
print("=" * 78)

rm_L = 252
rm = rm_ratio(close, rm_L)
gate_rm = rm > 1.0

header = f"{'Symbol':<8} {'Class':<10} {'Disagree%':>10} {'fwd BothIN':>10} {'fwd Sc>RM':>10} {'fwd RM>Sc':>10} {'RM helps?':>10}"
print(header)
print("-" * len(header))

for sym in SYMBOLS:
    bi_ret = []
    so_ret = []
    ro_ret = []
    bi_n = so_n = ro_n = bo_n = 0

    for split_name, is_mask, oos_mask in splits:
        oos_idx = close.index[oos_mask]
        valid = gate_score[sym].loc[oos_idx].notna() & gate_rm[sym].loc[oos_idx].notna()
        oos_idx = oos_idx[valid]
        if len(oos_idx) == 0:
            continue

        gs = gate_score[sym].loc[oos_idx]
        gr = gate_rm[sym].loc[oos_idx]
        fr = fwd_ret[sym].loc[oos_idx]

        bi = gs & gr
        so = gs & ~gr
        ro = ~gs & gr
        bo = ~gs & ~gr

        bi_n += bi.sum()
        so_n += so.sum()
        ro_n += ro.sum()
        bo_n += bo.sum()

        bi_ret.extend(fr[bi].dropna().tolist())
        so_ret.extend(fr[so].dropna().tolist())
        ro_ret.extend(fr[ro].dropna().tolist())

    total = bi_n + so_n + ro_n + bo_n
    disagree_pct = (so_n + ro_n) / total * 100 if total > 0 else 0

    bi_mean = np.mean(bi_ret) * 100 if bi_ret else float("nan")
    so_mean = np.mean(so_ret) * 100 if so_ret else float("nan")
    ro_mean = np.mean(ro_ret) * 100 if ro_ret else float("nan")

    # RM helps if: Score>RM bucket has WORSE fwd returns than BothIN
    # (meaning RM correctly vetoed bad entries)
    rm_helps = "YES" if so_mean < bi_mean else "NO"

    print(f"{sym:<8} {SYM_TO_CLASS[sym]:<10} {disagree_pct:>9.1f}% {bi_mean:>+9.2f}% {so_mean:>+9.2f}% {ro_mean:>+9.2f}% {rm_helps:>10}")


# =====================================================================
print()
print("=" * 78)
print("PART 3: Per-OOS-split stability — does the answer flip across time?")
print("=" * 78)

header = f"{'Split':<30} {'Score>RM fwd':>13} {'BothIN fwd':>11} {'RM veto helps?':>15}"
print(header)
print("-" * len(header))

for split_name, is_mask, oos_mask in splits:
    oos_idx = close.index[oos_mask]
    so_rets = []
    bi_rets = []

    for sym in SYMBOLS:
        valid = gate_score[sym].loc[oos_idx].notna() & gate_rm[sym].loc[oos_idx].notna()
        idx = oos_idx[valid]
        if len(idx) == 0:
            continue

        gs = gate_score[sym].loc[idx]
        gr = gate_rm[sym].loc[idx]
        fr = fwd_ret[sym].loc[idx]

        so_rets.extend(fr[gs & ~gr].dropna().tolist())
        bi_rets.extend(fr[gs & gr].dropna().tolist())

    so_mean = np.mean(so_rets) * 100 if so_rets else float("nan")
    bi_mean = np.mean(bi_rets) * 100 if bi_rets else float("nan")
    helps = "YES" if so_mean < bi_mean else "NO"
    print(f"{split_name:<30} {so_mean:>+12.2f}% {bi_mean:>+10.2f}% {helps:>15}")


# =====================================================================
print()
print("=" * 78)
print("VERDICT")
print("=" * 78)
print()
print("RM helps = the Score>RM bucket (where RM would veto a buy)")
print("has WORSE forward returns than BothIN (meaning the veto was correct).")
print()
print("RM hurts = the Score>RM bucket has BETTER forward returns,")
print("meaning RM blocked profitable entries.")
print()
print("If RM helps in some asset classes but hurts in others,")
print("consider using it selectively rather than globally.")
