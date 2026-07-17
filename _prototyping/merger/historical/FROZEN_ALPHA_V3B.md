# PROTOTYPE — frozen cash-merger alpha-v3b breadth-scaling contract

Question: does replacing the monthly control's binary ten-name liquidation rule
with proportional breadth scaling improve its executable result without raising
concentration or break-risk limits?

This mechanical challenger was specified after the alpha-v3 eligibility audit
but before its returns were run.  The audit showed `q70` counts of 7–9 in three
otherwise-off months and confirmed that whole-share affordability never bound.

## Challenger: `q70_monthly_scaled_breadth`

Everything in `q70_monthly_capped` remains unchanged except the treatment of
fewer than ten eligible names:

- `n >= 10`: use the unchanged equal weight `1 / n`.
- `1 <= n < 10`: use `1 / 10` per name.
- Continue applying the unchanged 10% name cap and 2% fallback-break-loss cap.
- Leave the unallocated fraction in the unchanged FRED DTB3 reserve.

Thus the uncapped target gross is `min(1, n / 10)`.  A sparse month reduces
aggregate exposure rather than increasing per-name concentration or switching
the entire strategy off.  No signal, universe, cost, execution or lifecycle
parameter changes.

## Evaluation

Use the same common period as alpha-v3, 1 August 2025 through 15 July 2026.
The challenger survives only if it improves both excess return over bills and
convergent-utility delta versus `q70_monthly_capped` without worsening maximum
drawdown or worst-month loss.  The result is descriptive reused history and
cannot promote the strategy.
