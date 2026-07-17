# Frozen alpha v4: point-in-time timing state

## Question

Does causal management closing guidance improve next-month expected-net-payoff selection over the unchanged `q70_monthly_capped` control?

## Data contract

- Use only target filings whose filing date lies inside the deal lifecycle.
- A filing-date observation becomes usable on the following trading date.
- Preserve management guidance as an exact date or a quarter, half-year, year, or coarse interval.
- Preserve the contractual outside date separately. It is not an expected close and does not truncate the distribution until extension mechanics are fully structured.
- Reject ambiguous or fiscal-period language rather than manufacture precision.
- Later observations supersede earlier observations only prospectively.
- If guidance is absent or stale, use the median remaining duration among earlier completed deals that had already survived to the same age. Use the transparent 175-day total-duration prior only when fewer than five such outcomes exist.

## Frozen challenger

`q70_monthly_guided_enp` keeps the control's universe, monthly reconstitution, `q_mkt >= 70%` risk gate, ten-name minimum, 10% name cap, 2% fallback-loss budget, liquidity rule, whole-share rule, bill reserve, execution costs, and Aegis simulator.

The only changes are:

1. Discount successful cash consideration over the remaining guidance interval (uniform mass), or the survival-conditioned empirical duration when guidance is unavailable/stale.
2. Estimate next-month completion hazards by deal-age bucket and point-in-time guidance state on the pre-evaluation cohort. A joint cell is used only with at least ten observations; otherwise it falls back to the age hazard.
3. Keep the pooled adverse-resolution hazard because the training cohort is too small to stratify breaks.
4. Rank positive next-month ENP:

   `completion_hazard * success_return - adverse_hazard * fallback_loss - round_trip_cost`

No threshold, interval mapping, minimum-cell size, or portfolio rule is swept.

## Promotion rule

Advance only if the challenger beats the unchanged control on excess return over bills and convergent utility while matching or improving maximum drawdown and worst month. Because this evaluation period has already been viewed, any survivor still requires untouched forward shadowing.
