---
title: "Convergent Income Engine - porting brief"
paper: "The Convergent Income Engine: Funding the Book Through Ordinary Markets"
tags:
  - brief
---

# Convergent Income Engine - porting brief

> [!abstract] Thesis
> The convergent seat earns a compensated return in **ordinary markets** by selling insurance;
> its **negative skew is the inventory it sells**, not a risk to minimize. Carry is a *candidate*
> for the role, not its definition - and rank on contribution to the paired book, not standalone
> smoothness.

## Folds in (owned here)

| Article | Provisional section |
|---|---|
| [[what-makes-a-convergent-sleeve-an-income-engine]] | The role - portfolio job, ranked on ΔΘ contribution |
| [[the-skew-is-the-product]] | Skew is the inventory - every standalone lever liquidates it |
| [[carry-as-the-short-gamma-income-pole]] | Carry as the pole - where the negative skew actually lives (FX) |
| [[carry-is-not-one-premium]] | Carry is not one premium - an accounting definition, not one bet |
| [[commodity-carry-constructions]] | Commodity carry - a curve-signal family, construction-dependent |
| [[insurance-linked-securities-as-the-orthogonal-income-pole]] | Orthogonal income (ILS) - cat bonds, physical jump risk |
| [[short-horizon-reversal-in-small-cross-sections]] | Reversal - execution overlay first, standalone sleeve second |

## Cites (owned by ① Architecture - do not fold)

[[convexity-as-the-axis-of-strategy-diversification]] · [[skewness-in-asset-returns]] ·
[[the-tiered-strategy-roster]]. (`the-skew-is-the-product` bridges to ① - keep it here, cite from ①.)

## Also draws on (notes)

[[the-ucits-constrained-carry-sleeve]] - wrapper feasibility.

## Deepen / clean up

- Separate the **income** from the **crash** cleanly (the articles show optimizers will split them).
- Reconcile the UCITS-wrapper route and the cat-bond ($19bn UCITS universe) feasibility into one
  buildability verdict.

## Carried from ① - the payer is capacity-constrained, and that changes the premise

① revised §2.2/§2.4 after an external challenge to the short pole's persistence. Sources were verified
independently in
[[research/budgeting-convexity/_challenge-verification|budgeting-convexity/_challenge-verification]];
the argument as it now stands is in ①'s §2.4. This seat inherits the consequence, because this seat
*is* the short pole.

**The verified finding.** Inelastic insurance demand is necessary but not sufficient for a premium.
Price is set by the constrained capacity of the specialists supplying the risk-bearing, so the premium
is rent on that constraint and decays as capital enters, which no publication triggers and no
disclosure prevents. Two unrelated markets show the same path: the S&P 500 variance risk premium has
earned approximately zero since around 2010 as dealer net index gamma stopped being reliably negative
(Dew-Becker & Giglio, 2025; break dated 2012 in their own statistics, 2017 in Bates, 2022), and
cat-bond premia are proportional to the intermediary's capital constraint, falling after the financial
crisis on institutional inflows and barely reacting to the record 2017 insured losses (Tomunen, 2026,
*RFS*). Sign by venue is set the same way: end users are net buyers of index options and net suppliers
of single-stock options, and the premium's sign follows (Gârleanu, Pedersen & Poteshman, 2009).

**What this asks of the seat.**

- The thesis line has positive content available. "Carry is a candidate for the role, not its
  definition" is currently a negative claim; the constraint framing supplies the definition, which is
  *bearing unhedgeable risk where the specialist is capital-constrained*. Carry is one occupancy of the
  job, not the job. This also promotes `carry-is-not-one-premium`'s aside that several rows can load on
  the same intermediary constraint from a footnote to a spine: the folded articles may be one premium
  observed in several venues, discriminated by whether the constraint still binds.
- The seat lacks an **economic** admission gate. "Rank on contribution to the paired book" is a
  portfolio test. The constraint framing supplies an ex-ante, observable one (intermediary positioning;
  specialist capital against the risk on offer), which is what `research/README` demands.
  **Caveat before adopting it:** a positioning/flow variable used to decide whether a premium is
  available sits uncomfortably close to the return-forecasting line ① draws in §5.5, and ① had to
  remove exactly that contradiction once already (the Uysal & Mulvey concession). If this seat adopts
  such a gate it owes an explicit argument for which side of the line it is on. Do not inherit it
  silently.
- **ILS orthogonality needs demoting, and its buildability question now has a prior question.** The
  orthogonality claim in `insurance-linked-securities-as-the-orthogonal-income-pole` is contradicted by
  cat-bond dependence on corporate credit spreads strengthening in crisis (Gürtler, Hibbeln &
  Winkelvos; Carayannopoulos & Perez) and by the 2008 Lehman total-return-swap counterparty failures
  (Ajax Re, Newton Re, Carillon, Willow Re, which were rating and collateral impairments rather than
  confirmed principal losses). Orthogonality was a design goal that failed in the one state it was held
  for. Before the UCITS-wrapper/$19bn reconciliation above, ask whether the premium is still there at
  all, given Tomunen.

**Open lead, deliberately not cited in ① (needs sourcing before use).** There is a "shadow gamma"
result holding that dealers' *crash-scenario* short exposure has not gone away even where conventional
local gamma flipped positive. If it holds, it materially defends the pole: the payer would still be
short crash risk, and the post-2010 compression would be a repricing of ordinary variance rather than
the payer leaving. ① left it out because the only located source is an unpublished conference paper
whose authors and title could not be pinned down, and ① had just cleared a strict integrity gate. **Do
not cite it until it is identified and verified.** Finding it, or establishing that it does not exist,
is a cheap and high-value early task for this seat.
