---
title: WSH Cash-Merger Convergence Design
date: 2026-07-15
topic: demeter-cash-merger
status: blocked-on-survivorship-safe-prices
related:
  - "[[the-tiered-strategy-roster]]"
  - "[[finding-a-buildable-convergent-engine]]"
  - "[[massive-data-for-cash-merger-convergence]]"
tags:
  - note
  - demeter
  - convergent
  - merger-arbitrage
  - ibkr
  - wsh
---

# WSH Cash-Merger Convergence Design

> [!note] Status
> **Mechanism accepted; alpha unproven.** Definitive fixed-cash merger arbitrage belongs in Demeter's convergent income-engine slot. IBKR Wall Street Horizon (WSH) is the current preferred live event source because it exposes structured merger fields through the broker connection already used for market data and execution. The strategy remains a candidate until a production-path Run demonstrates a positive premium after breaks and costs and positive marginal utility beside the locked trend responder.

## Roster classification

Cash merger arbitrage has the mechanism required by [[the-tiered-strategy-roster]]:

- **Ordinary state:** the target price converges toward the contractual cash offer.
- **Income:** the investor collects the deal spread.
- **Convergence horizon:** deal completion.
- **Failure state:** termination, rejection, financing failure, adverse amendment or extended delay.
- **Payoff shape:** frequent small gains with occasional large break losses, usually negatively skewed.

The proposed floor is therefore:

$$
\text{cash-merger convergence engine} \;\oplus\; \text{broad trend responder}
$$

This is a cleaner conceptual convergence mechanism than the rejected credit-ETF constructions because the endpoint is explicit: a declared cash consideration rather than an inferred yield or spread relationship. Negative skew describes the likely implementation, but it does not qualify the sleeve by itself.

## Qualification contract

Demeter earns the floor slot only if the Run establishes all three roster conditions:

1. A positive premium after broken deals, commissions, bid-ask costs, financing, FX and cash drag.
2. A legible convergence-break mechanism, including clustered terminations and delayed closes.
3. Positive marginal whole-book utility when paired with the locked broad-trend responder.

Failure is a valid conclusion. Correct family classification does not imply that the available universe, event history or implementation has a tradeable alpha.

## WSH data contract

`WSH` is an authored Array shortcut, analogous to `OHLCV`, that expands before the Execution Bundle is built. Components receive only normalized Arrays:

- `WshCashOffer`
- `WshStatus`
- `WshExpectedCloseDays`
- `WshConsiderationType`
- `WshAvailable`
- `WshAgeDays`

The Indicator and Strategy must not know about IBKR requests, callback payloads, `conId` mapping, broker sessions or catalog mechanics. They consume the same `MarketDataBundle` in RD, Trader backtests and live execution.

## Ownership and parity

IBKR-specific acquisition, validation, identity matching, immutable observation storage and causal WSH Array materialization belong to one deep module under Aegis Data's IBKR adapter. No generic `WshPort` is justified while IBKR is the sole WSH provider.

Research and live share the normalized observation model and the same pure materializer:

```text
live IBKR WSH observations ─┐
                            ├─> causal WSH Array materializer ─> MarketDataBundle
catalog observations ───────┘
```

The live implementation must reuse the existing IBKR data-client connection. It must not open a second Gateway session. A non-IBKR data adapter does not provide dummy WSH methods; a book requesting unsupported Arrays fails during assembly.

## Causality and historical limitation

Each observation is available only from its recorded observation time. Array materialization may forward-fill a known state until it is superseded, but it must never backward-fill a finalized state into dates before retrieval. `WshAvailable = 0` represents a genuine absence of known event state; it is not a replacement for missing historical observations.

Live WSH can establish prospective parity immediately. A trustworthy 2018-2026 Run still requires point-in-time observations or another defensible historical reconstruction. Current finalized WSH records cannot be treated as proof of what was known on earlier dates.

## Prototype decision

Before production WSH plumbing is built, a throwaway prototype must answer one question through the existing Run Config, registered Components, portfolio simulation and convergent Metrics:

> Does a causal fixed-cash merger rule produce evidence of a net convergence premium and improve the paired trend book, or is it merely a correctly classified mechanism without usable alpha?

The prototype may use a deliberately small verified event tape, but it must not replace the production pipeline with an ad hoc return calculation. Its verdict is feasibility evidence, not promotion evidence; a small event sample cannot establish robustness.

## Live-Gateway prototype result

The 2026-07-15 throwaway prototype queried the paper Gateway directly and recovered 1,528 WSH merger records, of which 226 passed a conservative resolved fixed-cash filter. It then requested exact-`conId` daily history for five completed and five cancelled deals before invoking any performance metric.

The outcome coverage failed asymmetrically:

| Outcome | Sampled | Complete pre-event-to-resolution history from IBKR |
| --- | ---: | ---: |
| Completed | 5 | 0 |
| Cancelled | 5 | 4 |

IBKR returned `No security definition has been found for the request` for every completed/delisted sample, while surviving broken targets such as `PNM`, `ROG`, `TSEM`, and `FHN` remained retrievable. A backtest built from that corpus would omit successful convergence while retaining most break losses. This is outcome-dependent survivorship bias, so the prototype correctly refused to calculate `convergent_income_utility` or paired-floor utility.

> [!failure] Current verdict
> **Do not build the historical strategy from WSH plus IBKR HMDS alone.** WSH is viable for prospective event capture and live state, but alpha validation remains blocked until a survivorship-safe OHLCV source covers completed and cancelled targets symmetrically. Massive Developer or another point-in-time vendor remains the cleanest identified price-history seam.

The proposed cost contract remains valid for the eventual Run: `next_close` execution; €0.35 fixed commission per order; 5 bps slippage; 3 bps FX conversion cost per foreign trade; 3.67% annual margin debit when cash is negative; and the existing 2% drift bands. The Indicator's generic round-trip deduction is zero so broker, market, and FX costs are not counted twice. Deal-specific economic costs may be added only when the production simulator cannot observe them.
