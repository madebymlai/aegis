---
title: "Immediate Defense - porting brief"
paper: "Hedging the V-Shaped Crash: An Immediate-Defense Sleeve"
tags:
  - brief
---

# Immediate Defense - porting brief

> [!abstract] Thesis
> The crisis responder has a **speed gap**: it confirms the shock too late. This seat is the
> immediate defense. The price-only era concluded "no construction - route to bought gamma";
> **that verdict was a property of OHLCV-only data**, and this paper re-opens it with the richer
> inputs that were out of scope then.

## Folds in (owned here)

| Article | Provisional section |
|---|---|
| [[detecting-fast-crashes-from-price]] | The price-only wall - in-bar signals are coincident, not predictive; the measured ceiling any trigger must climb |
| [[havens-at-regime-turning-points]] | Havens at the turn - the ordering is backwards for an allocation rule |

## Cites (owned elsewhere - do not fold)

[[measuring-crisis-alpha]] · [[the-tiered-strategy-roster]] (① Architecture) ·
[[research/crisis-responder/_brief|crisis-responder]] (② - the responder whose gap this fills).

## Also draws on (notes)

[[monetizing-the-tail-sleeve]] · [[the-ucits-constrained-tail-sleeve]] ·
[[floor-tail-and-robust-strategy-allocation]] - the bought-gamma tail sleeve.

## Deepen / clean up - the reason this is now its own paper

- **The OHLCV-only constraint is lifted.** Re-run the fast-crash construction question with data the
  price-only articles could not use: the **implied-vol surface / term structure**, **order-flow /
  microstructure**, and cross-asset stress signals. `detecting-fast-crashes` is the wall to climb,
  not the conclusion.
- Decide the seat's form: *bought gamma* (a standing tail sleeve) vs a *data-richer coincident
  throttle* - and price each against the false-positive bill in calm years.
