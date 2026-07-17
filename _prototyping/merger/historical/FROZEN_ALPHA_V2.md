# PROTOTYPE — frozen cash-merger alpha-v2 contract

Question: does a transparent, diversified fixed-cash merger-risk premium clear
three-month bills after small-book execution costs when market-implied deal risk,
unused cash, and portfolio construction are represented consistently?

This design was frozen before running alpha-v2. The July 2025–July 2026 history
must not be used to alter its parameters or choose a winner.

## Signal

- Universe: signed U.S. public-target fixed-cash deals in the repaired Massive
  lifecycle census.
- Availability: filing facts become usable only after their filing-day close.
- Offer: latest causally available cash offer; amendments enter only from their
  own filing availability date.
- Expected close: announcement plus 175 calendar days when no causal company
  guidance is available.
- Discounted success value: cash offer discounted at contemporaneous FRED DTB3
  over the remaining expected-close horizon.
- Initial fallback: mean of the last 20 pre-announcement closes.
- Dynamic fallback: initial fallback compounded by the target's pre-announcement
  beta times SPY cumulative log return since announcement.
- Beta: OLS on all aligned pre-announcement log returns available in the existing
  50-calendar-day causal price window; require at least 20 paired returns. No
  clipping or post-outcome fitting.
- Market-implied probability:
  `clamp((target close - dynamic fallback) / (discounted offer - dynamic fallback), 0, 1)`.
- Admission: probability at least 70%, positive discounted spread, $1 million
  trailing 20-session median dollar volume, and at least ten eligible deals.

## Fixed portfolio constructions

1. `q70_monthly_capped`
   - Reconstitute on the first observed trading session of each calendar month.
   - Hold at most 40 eligible deals.
   - Equal weight, capped at 10% per name and 2% portfolio fallback-break loss.
   - Remove resolved deals immediately; admit replacements only at the next
     monthly reconstitution.

2. `q70_fixed_entry_40`
   - Admit a deal once when it first qualifies.
   - Initial weight 3%, capped at 10% and 2% portfolio fallback-break loss.
   - Hold the entry risk budget until resolution; at most 40 deals and 100% gross.

Both constructions use whole shares, next-close fills, 2% drift bands, 5 bp
slippage, and $0.35 per order through the Aegis production simulator. Unallocated
target weight accrues the contemporaneous FRED DTB3 daily return as an explicitly
reported reserve overlay because the simulator models debit interest but not
positive cash interest.

## Decision rule

This reused one-year sample is descriptive. Neither construction can be promoted
from it. Alpha-v2 is worth extending historically only if at least one fixed
construction has positive net excess return and positive convergent-utility delta
versus bills after the reserve and execution costs. No parameter is selected from
the stronger in-sample construction.

## Observed outcome

The first completed run exposed and rejected a synthetic-settlement artifact: a
generic filing parser labeled a `$25` number as CIO's latest offer while its market
price remained near `$6.80`. Substituting that number for the final traded mark
created a false gain. The corrected run uses the last adjusted market mark at
resolution and never a parsed synthetic payout; signal parameters and portfolio
parameters were unchanged.

Corrected descriptive result, 16 July 2025 through 15 July 2026:

- `q70_monthly_capped`: 4.93% net, 2.30% over bills, +2.19 percentage
  points of convergent-utility delta, 10 median names, 22 completed and 3
  terminated held deals.
- `q70_fixed_entry_40`: 1.48% net, 1.16% below bills, -1.22 percentage
  points of convergent-utility delta, 18 median names, 29 completed and 4
  terminated held deals.

Verdict: extend the frozen monthly construction to a genuinely longer historical
sample; do not promote it. The fixed-entry construction fails this frozen gate.

## Two-year extension

The same frozen contract was then run from 17 July 2024 through 15 July 2026,
the usable boundary of Massive's rolling two-year price entitlement. The causal
census contained 232 deals and 22 terminations; 206 lifecycles survived causal
offer, price, and beta-history filters.

- `q70_monthly_capped`: 8.98% cumulative net return, 4.41% CAGR, versus
  5.82% cumulative and 2.88% CAGR for bills; +3.17 percentage points cumulative
  excess, +1.47 percentage points convergent-utility delta, 13 median names, 34
  completed and 5 terminated held deals.
- `q70_fixed_entry_40`: 4.14% cumulative net return, 2.05% CAGR, 1.68
  percentage points below bills cumulatively, -0.86 percentage points of
  convergent-utility delta, 18 median names, 56 completed and 9 terminated held
  deals.

The two-year extension confirms the frozen decision: monthly capped qualifies for
the next research stage; fixed entry remains killed. Five held terminations are
still insufficient for production promotion or for characterising the full tail.
