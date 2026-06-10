"""
PROTOTYPE — throwaway.
Question: Does the RM ratio (price / SMA) add independent gating info
beyond the multi-period momentum score's sign?

Run: python research/prototypes/rm_vs_momentum_score.py
"""

import pandas as pd
import vectorbtpro as vbt

SYMBOLS = ["SPY", "IWM", "EEM", "TLT", "GLD", "DBC", "VNQ", "UUP", "XLE", "XLU"]
START = "2015-01-01"
END = "2025-12-31"

# --- fetch ---
data = vbt.YFData.pull(SYMBOLS, start=START, end=END, timeframe="1D", silence_warnings=True)
close = data.get("Close")

# --- indicator 1: multi-period momentum score ---
def momentum_score(close: pd.DataFrame) -> pd.DataFrame:
    scores = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    for days, weight in [(21, 12), (63, 4), (126, 2), (252, 1)]:
        r = (close / close.shift(days)) ** (252 / days) - 1
        scores += weight * r
    return scores

# --- indicator 2: RM ratio (price / SMA) ---
def rm_ratio(close: pd.DataFrame, window: int = 252) -> pd.DataFrame:
    return close / close.rolling(window).mean()

scores = momentum_score(close)
rm = rm_ratio(close)

# binary gates
gate_score = scores > 0       # momentum score says "in"
gate_rm = rm > 1.0             # RM says "in" (price above SMA)

# drop warmup
valid = scores.notna() & rm.notna()
gate_score = gate_score[valid].dropna(how="all")
gate_rm = gate_rm[valid].dropna(how="all")
common_idx = gate_score.index.intersection(gate_rm.index)
gate_score = gate_score.loc[common_idx]
gate_rm = gate_rm.loc[common_idx]

# --- analysis ---
both_in = (gate_score & gate_rm)
both_out = (~gate_score & ~gate_rm)
score_only = (gate_score & ~gate_rm)
rm_only = (~gate_score & gate_rm)
total = len(common_idx)

print("=" * 70)
print("PROTOTYPE: RM ratio vs momentum score — gating agreement")
print(f"Period: {common_idx[0].date()} to {common_idx[-1].date()}")
print(f"Trading days: {total}")
print("=" * 70)

# per-symbol breakdown
header = f"{'Symbol':<8} {'Both IN':>9} {'Both OUT':>9} {'Score>RM':>10} {'RM>Score':>10} {'Agree%':>8} {'Disagree%':>10}"
print(header)
print("-" * len(header))

for sym in SYMBOLS:
    bi = both_in[sym].sum()
    bo = both_out[sym].sum()
    so = score_only[sym].sum()
    ro = rm_only[sym].sum()
    sym_total = bi + bo + so + ro
    agree = (bi + bo) / sym_total * 100
    disagree = (so + ro) / sym_total * 100
    print(f"{sym:<8} {bi:>9} {bo:>9} {so:>10} {ro:>10} {agree:>7.1f}% {disagree:>9.1f}%")

print()
all_agree = sum((both_in[s].sum() + both_out[s].sum()) for s in SYMBOLS)
all_disagree = sum((score_only[s].sum() + rm_only[s].sum()) for s in SYMBOLS)
all_total = all_agree + all_disagree
print(f"Overall agreement: {all_agree / all_total * 100:.1f}%")
print(f"Overall disagreement: {all_disagree / all_total * 100:.1f}%")

print()
print("=" * 70)
print("DISAGREEMENT BREAKDOWN — who is right when they disagree?")
print("=" * 70)
print()
print("When Score=IN but RM=OUT (score says buy, RM vetoes):")
print("  → This means momentum is positive but price is still below its SMA.")
print("  → Typical at the START of a recovery — momentum turns positive")
print("    before price crosses above the long SMA.")
print()
print("When RM=IN but Score=OUT (RM says buy, score vetoes):")
print("  → Price is above SMA but composite momentum is negative.")
print("  → Typical at the START of a decline — price hasn't crossed below")
print("    SMA yet but momentum has already turned negative.")
print()

# forward returns when they disagree
fwd_5d = close.pct_change(5).shift(-5)
fwd_10d = close.pct_change(10).shift(-10)
fwd_20d = close.pct_change(20).shift(-20)

print("Mean forward returns when gates DISAGREE (pooled across symbols):")
print(f"{'Condition':<25} {'5d fwd':>8} {'10d fwd':>9} {'20d fwd':>9}  {'N days':>7}")
print("-" * 70)

for label, mask in [
    ("Score=IN, RM=OUT", gate_score & ~gate_rm),
    ("Score=OUT, RM=IN", ~gate_score & gate_rm),
    ("Both IN", gate_score & gate_rm),
    ("Both OUT", ~gate_score & ~gate_rm),
]:
    vals_5 = fwd_5d[mask].stack().dropna()
    vals_10 = fwd_10d[mask].stack().dropna()
    vals_20 = fwd_20d[mask].stack().dropna()
    n = len(vals_5)
    if n > 0:
        print(f"{label:<25} {vals_5.mean()*100:>+7.2f}% {vals_10.mean()*100:>+8.2f}% {vals_20.mean()*100:>+8.2f}%  {n:>7}")
    else:
        print(f"{label:<25} {'—':>8} {'—':>9} {'—':>9}  {0:>7}")

print()
print("=" * 70)
print("CORRELATION between raw signals (continuous, not binary)")
print("=" * 70)
print()

for sym in SYMBOLS:
    corr = scores[sym].corr(rm[sym])
    print(f"  {sym:<6} score vs RM correlation: {corr:.3f}")

print()
print("=" * 70)
print("VERDICT")
print("=" * 70)
print()
pct_disagree = all_disagree / all_total * 100
if pct_disagree > 10:
    print(f"Disagreement rate is {pct_disagree:.1f}% — RM carries independent info.")
    print("Check forward returns above to see if the disagreement is USEFUL")
    print("(i.e., does the veto improve or hurt outcomes).")
else:
    print(f"Disagreement rate is only {pct_disagree:.1f}% — RM is mostly redundant")
    print("with the momentum score. Consider dropping it to simplify.")
