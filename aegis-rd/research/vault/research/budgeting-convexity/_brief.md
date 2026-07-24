---
title: "Budgeting Convexity - porting brief"
paper: "Budgeting Convexity: Diversifying a Strategy Book by the Sign of Skew"
tags:
  - brief
---

# Budgeting Convexity - porting brief

> [!abstract] Thesis
> Portfolio diversification is budgeting along **one axis - the sign of convexity (skew)**. The
> roster that implements it is an **order of operations**, not a count: each tier fixes a failure
> the previous one cannot. This is the architecture paper; it treats each sleeve as a *role* and
> defers construction to the seat papers.

## Folds in (owned here)

| Article | Provisional section |
|---|---|
| [[skewness-in-asset-returns]] | Foundations - the third-moment primitive the axis rests on |
| [[convexity-as-the-axis-of-strategy-diversification]] | The axis - long-skew vs short-skew poles |
| [[the-tiered-strategy-roster]] | The roster - convergent ⊕ responder → defense → off-axis |
| [[measuring-crisis-alpha]] | Scoring a seat - drawdown-aware objectives, not full-sample Sharpe |
| [[allocating-and-rebalancing-a-multi-strategy-book]] | Allocation - risk budgets, vol targeting, no-trade bands |
| [[when-conditioning-pays]] | Conditioning - when the allocation may go adaptive |

## Cites (owned by the seat papers - role only, do not fold)

- [[research/crisis-responder/_brief|crisis-responder]] - the persistent-crisis responder
- [[research/convergent-engine/_brief|convergent-engine]] - the convergent income engine
- [[research/v-crash-defense/_brief|v-crash-defense]] - the immediate defense

## Also draws on (notes / runs)

[[building-the-tiered-roster-after-demeter-v2]] · [[budgeting-the-divergent-seat]] ·
[[floor-tail-and-robust-strategy-allocation]] · `runs/floor/` diaries.

## Deepen / clean up

- Dedupe the skew/convexity definitions that repeat across the source articles into one foundation.
- Role-specs asserted here depend on the seat papers - plan a **revision round** to reconcile
  after ②③④ deepen (this is the integrative paper; expect it to move last).
