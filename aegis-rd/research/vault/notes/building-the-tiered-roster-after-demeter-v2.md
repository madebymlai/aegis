---
title: Building the Tiered Roster After Demeter V2
date: 2026-07-13
topic: strategy-roster
status: decision
related:
  - "[[the-tiered-strategy-roster]]"
  - "[[paired-floor-strategy-evaluation]]"
  - "[[demeter-duration-neutral-credit-carry-v2]]"
  - "[[insurance-linked-securities-as-the-orthogonal-income-pole]]"
tags:
  - note
  - roster
  - carry
  - demeter
  - portfolio-construction
---

# Building the Tiered Roster After Demeter V2

> [!abstract] Decision
> Demeter V2 falsified one **active ETF-ranking rule**; it did not falsify credit income, carry as a family, or the tiered roster. Build the deployable roster with locked Atalanta, the simple locked defensive credit-income book as a **provisional** concave pole, and the locked tail target. Run CATB as the shadow challenger for the concave role. Leave the expansion tier empty until an off-axis [[what-is-a-strategy|strategy]] earns promotion.

## What failed and what survived

The V2 duration-neutral optimizer found an average ex-ante pickup of only `3.1 bp/year`. Its gross realized advantage was likewise only about `3 bp/year`, before the active portfolio's additional fixed fees. No turnover rule can make that opportunity economically material. The correct response is to retire the active four-fund richness hypothesis, not to declare that no income sleeve exists.

Three distinct claims must remain separate:

1. **Economic premium:** corporate credit spreads can compensate investors for default, liquidity and recession risk.
2. **Vehicle:** a defensive short-duration credit-fund basket can expose the book to that premium.
3. **Active alpha:** public fund-level yield and duration data can identify which of four ETFs is temporarily rich.

V2 rejected claim 3. It did not reject claims 1 or 2. A sleeve does not need a successful tactical ranker to be carry; holding a priced risk and collecting its spread is already a carry implementation. The roster cares about the realized payoff shape and the sleeve's contribution beside the other pole, not how complicated its signal is.

## The roster that can be built now

| Tier and role | Current expression | Status | Required decision |
|---|---|---|---|
| Floor: divergent pole | `configs/atalanta/trend_floor.yaml` | Locked champion | Keep. It is the slow drawdown payer. |
| Floor: concave income pole | `configs/demeter/carry_floor.yaml` (`SDHY` + `LQDH`, no spread lean or EM leg) | Provisional locked implementation | Use as simple `credit_income`; make no claim of active richness alpha. |
| Floor: orthogonal income challenger | `configs/demeter/cat_bond.yaml` (`CATB`) | Shadow only | Accumulate forward executable history and compare against credit; do not promote from its short ETF history. |
| Target: fast-crash sleeve | `configs/aegis/tail_target.yaml` | Locked champion | Keep separate from the slow floor; it owns the fast crash Atalanta cannot react to. |
| Expansion | None | Deliberately empty | Add only after a breadth-capable off-axis strategy passes its own evidence standard. |

This is not a claim that the provisional credit pole has passed a fresh promotion test. The latest paired evaluation found that credit reduced drawdown and improved Sharpe beside Atalanta, but lowered the fixed `60/40` composite certainty equivalent; all bootstrap intervals included zero. Its correct label is therefore `credit_income challenger`, not `proven floor champion`.

The earlier pairing diagnosis remains useful rather than contradictory: monthly trend-credit correlation was near zero and the apparent daily co-crash was dominated by March 2020. That establishes that the pairing is plausible. The later fixed-weight evaluator establishes that the realized return sacrifice is not yet demonstrably worth a `40%` capital allocation. Dependence and allocation utility are different questions.

> [!important] The roster is role-complete before it is evidence-complete
> The files above provide executable representatives for the required roles. Promotion confidence can remain provisional. If the credit pole is not acceptable at that confidence level, allocate its budget to cash rather than relabeling another convex hedge as income. An explicitly empty role is more honest than a false diversifier.

## Why CATB is the preferred successor, but not the immediate answer

Catastrophe bonds preserve the required concave shape—regular insurance spread with occasional principal loss—while moving the loss trigger from the financial cycle to insured physical events. That makes them a better economic match for Atalanta than another recession-sensitive credit sleeve. Peer-reviewed work finds meaningful multi-asset diversification benefits, while also documenting a residual liquidity correlation during the Lehman shock.[^demers][^carayannopoulos]

The investable vehicle now exists: KRC Cat Bond UCITS ETF is an Irish UCITS ETF with LSE, Xetra and Borsa Italiana lines, daily dealing and disclosed holdings.[^catb] Its problem is evidence length, not accessibility: the ETF launched in December 2025. Six or seven months of its own price history cannot validate catastrophe cycles, major-event drawdowns or a floor allocation.

CATB should therefore run in shadow beside the credit incumbent. Artemis market history can provide slow market context, but it cannot backfill the ETF's executable marks, fees, spread or tracking behavior. Promotion requires observed vehicle history through time and preferably at least one material catastrophe mark, not a synthetic splice presented as realized ETF performance.

## What to use if credit eventually fails

Use this ordered fallback, without changing the role definition:

1. **CATB after sufficient forward evidence:** best match to the orthogonal concave-income thesis.
2. **A UCITS merger-arbitrage fund as a separately researched challenger:** it is a genuine convergent premium, but deal breaks cluster in equity downturns and transaction costs matter, so it is less orthogonal than catastrophe risk.[^mitchell]
3. **Cash or short bills:** not a concave income engine, but the correct placeholder when no candidate clears the promotion standard.

Do not fill the role with covered calls or put writing merely because they have negative skew; they reload the equity crash factor already present elsewhere. Do not revive commodity-roll, FX-carry or small-cross-section reversal proxies without an investable universe and a causal signal. Those would satisfy a label more readily than the roster's actual job.

## Next evidence, not another redesign

1. Re-run the authoritative paired-floor report with locked Atalanta and locked `carry_floor.yaml`; preserve the preregistered comparison and label reused-history inference honestly.
2. Add a risk-matched diagnostic alongside the existing fixed-capital `60/40` report. The current comparison partly asks whether replacing a high-return trend allocation with lower-return credit improves utility; it does not isolate diversification at equal portfolio risk. Report both, but do not tune the leverage or weight to win.
3. Freeze the active V2 result as a falsification. No further band, frequency or parameter sweep is justified by a `3 bp/year` gross signal.
4. Continue forward CATB collection and compare static credit versus CATB on the same monthly paired-floor measures when the vehicle has enough observations.
5. Keep the expansion tier empty. The floor and target tiers do not become invalid merely because expansion has not been sourced.

## Sources

[^demers]: Demers-Bélanger, K. and Lai, V. S. (2020), “Diversification benefits of cat bonds: An in-depth examination,” *Financial Markets, Institutions & Instruments* 29(5), 165–228. Cat bonds expanded the attainable portfolio set and improved diversification measures, especially in crisis and high-volatility periods. https://doi.org/10.1111/fmii.12134

[^carayannopoulos]: Carayannopoulos, P. and Perez, M. F. (2014), “Diversification through Catastrophe Bonds: Lessons from the Subprime Financial Crisis,” *The Geneva Papers on Risk and Insurance*. Cat bonds developed significant market correlation during the Lehman liquidity shock, though the change was smaller than for conventional risky assets. https://doi.org/10.1057/gpp.2014.14

[^catb]: HANetf, “KRC Cat Bond UCITS ETF.” Official product page: Irish UCITS ETF, inception 2 December 2025, accumulating, with LSE/Xetra/Borsa Italiana trading lines and daily holdings disclosure. https://hanetf.com/fund/catb-cat-bond-etf/

[^mitchell]: Mitchell, M. and Pulvino, T. (2001), “Characteristics of Risk and Return in Risk Arbitrage,” *Journal of Finance*. Risk-arbitrage returns resemble risk-free returns plus short-put exposure; market correlation rises in downturns and transaction costs materially affect results. https://www.aqr.com/Insights/Research/Journal-Article/Characteristics-of-Risk-and-Return-in-Risk-Arbitrage
