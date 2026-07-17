# PROTOTYPE — frozen cash-merger alpha-v3 event-time contract

Question: does an out-of-time event-time hazard lookup improve the frozen
`q70_monthly_capped` cash-merger benchmark when both are evaluated with the
same executable portfolio contract?

This contract was written before running alpha-v3.  Results from the later
evaluation period must not be used to alter its controls.

## Training and evaluation split

- Hazard training observations: 17 July 2024 through 31 July 2025.
- Common evaluation period: 1 August 2025 through 15 July 2026.
- The runner supplies the common evaluation start; hazard training ends on the
  preceding calendar day.  These dates are evaluation state, not strategy
  constants.
- A training observation is a deal active on the first observed session of a
  month.  Its outcome interval ends at the next calendar-month boundary and is
  used only when that full interval precedes the training cutoff.
- Completion hazards use three externally specified event-age buckets from
  Giglio and Shue's cash-deal cutoffs: early (`< 12` weeks), high (`12–35`
  weeks), and late (`>= 36` weeks).
- Adverse-resolution hazard is pooled across event ages, reflecting the
  paper's approximately flat withdrawal hazard and the scarcity of local
  failures.
- No evaluation-period outcome enters the hazard table.

## Strategies

### Control: `q70_monthly_capped`

The unchanged alpha-v2 monthly construction: signed fixed-cash deals,
`q_mkt >= 70%`, positive discounted spread, $1 million trailing median dollar
volume, at least ten eligible deals, at most forty positions, monthly
reconstitution, equal weights capped at 10% per name and 2% portfolio fallback
break loss.

### Challenger: `q70_monthly_event_hazard`

Identical universe, gate, rebalance, capacity, caps, costs, reserve and
execution.  For each eligible deal, compute the next-interval expected net
event payoff per invested dollar:

```text
ENP = completion_hazard * success_return
    - adverse_hazard * fallback_break_loss
    - estimated_round_trip_cost_rate
```

The success return uses the same discounted causal offer as `q_mkt`; fallback
loss uses the same beta-adjusted pre-announcement fallback.  Estimated ranking
cost includes two 5 bp slippage legs and two $0.35 commissions at the maximum
position allowed by the existing name and break-loss caps.  Admit only
positive-ENP deals and rank descending by ENP.  Final fills and realized costs
still come from the existing Aegis simulator.

## Unchanged accounting and execution

- Causal offer amendments and filing availability.
- 175-day expected close fallback.
- Beta-adjusted 20-day pre-announcement fallback.
- Whole shares, next-close fills and 2% drift bands.
- 5 bp slippage and $0.35 per order.
- FRED DTB3 on lagged unallocated target weight.
- Resolution exits use actual adjusted market marks, never parsed synthetic
  consideration.

## Required diagnostic

For every monthly control reconstitution in the evaluation period, report the
deal count after active-lifecycle, causal-offer, valid-payoff, affordability,
liquidity and `q70` filters.  This determines whether the benchmark's binary
off months are caused by the ten-name gate or by earlier signal/data filters.

## Decision rule

This is a small, reused-history prototype, not promotion evidence.  The hazard
challenger survives only if, on the common later period, it improves both net
excess return over bills and convergent-utility delta versus the unchanged
control without worsening maximum drawdown or worst-month loss.  A result
driven by one avoided termination is reported as fragile and requires forward
shadowing.  Failure retains the simpler control and kills the hazard overlay.
