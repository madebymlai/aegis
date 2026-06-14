# Research brief: the optimal orthogonal NON-EQUITY asset universe (tiered, up to ~50)

**For:** an external quantitative research analyst working in a browser. You do **not**
have access to our code, our data, or our backtests, and you are not expected to run
anything. Use your domain knowledge plus public sources (ETF fact sheets, issuer pages,
academic and practitioner research on cross-asset correlations and diversification) to
**propose and rank a universe of tickers**. We will do the backtesting on our side; your
deliverable is the asset list, the tiering, and the reasoning behind it.

You have no predetermined answer. Reason it through, cite sources where you can, and be
honest about uncertainty. Do not copy-paste a "best commodity/FX/bond ETF" listicle -
every ticker must earn its slot on the criteria below, and you must sanity-check each one
for liquidity and trading history.

---

## Background (everything you need is here)

We run a **cross-asset trend-following (time-series momentum) strategy**: long/short,
volatility-scaled, on **daily ETF prices from Yahoo Finance**, backtested from
**2018-01-01**. Trend-following is long-volatility / "long-gamma": it is supposed to make
money when its instruments make large *sustained* moves in either direction, and to bleed
in choppy, directionless markets.

What we learned the hard way: **the universe decides whether this works.**

- On an **equity-heavy** book (US large/small cap, EM equity, sector ETFs, REITs, plus a
  few diversifiers), the strategy failed. The reason: the whole book's day-to-day
  movement was almost perfectly aligned with the equity market - when we measured the
  correlation between "how much the book moved" and "how much the S&P 500 moved," it was
  about **0.97**. There was effectively a single risk factor (equities) driving
  everything, so there was no independent trend axis to harvest, and the lagged signal
  kept getting whipsawed by fast equity reversals. The strategy realized the *opposite*
  of the intended payoff.
- On a **non-equity** book (Treasuries across the curve, TIPS, credit, currencies, broad
  and single commodities, metals, agriculture), it worked. That correlation dropped to
  about **0.52**, a genuinely separable trend axis appeared, and the strategy became
  robustly long-gamma.

So **orthogonality is the lever.** The more genuinely *independent* bets the universe
contains (not just more tickers - tickers that move differently from each other and from
equities), the stronger and more stable the strategy. We picked our non-equity book by
hand. We want you to design a better, more orthogonal one, systematically.

A useful mental model is Grinold's Fundamental Law: skill scales with the square root of
the number of **independent** bets, not the nominal asset count. Ten near-orthogonal
cross-asset instruments are worth far more than fifty that all collapse onto two or three
shared factors.

## The task

From the broad universe of liquid, **non-equity**, US-listed ETFs available on Yahoo
Finance, select and **rank** the tickers that together span the most independent
(orthogonal) risk, then organize the ranking into nested tiers so we can test the
strategy at increasing breadth and see where the benefit saturates.

**Tier structure** (nested: each tier contains the previous one plus its additions):

| Tier | Adds | Cumulative size | Role |
|---|---|---|---|
| 0 - Essentials | 10 | **10** | the orthogonal core: the 10 instruments that span the most independent risk between them |
| 1 - First expansion | +10 | **20** | the next 10 that add the most *new* (non-redundant) risk |
| 2 | +5 | 25 | refinement: next-best 5 |
| 3 | +5 | 30 | |
| 4 | +5 | 35 | |
| 5 | +5 | 40 | |
| 6 | +5 | 45 | |
| 7 | +5 | **~50** | the practical ceiling of useful non-equity breadth |

Order is by **marginal** orthogonality: each added instrument should be the one that adds
the most *new* independent risk given everything already chosen - not its standalone
appeal. An instrument that is excellent but nearly a duplicate of one already in the list
ranks low (keep the more liquid of two near-duplicates).

## Selection criteria (priority order)

1. **Orthogonality / independence.** The whole point. Favour instruments with low
   correlation to each other and, especially, low correlation to the equity market. Span
   distinct macro drivers: the rates curve (short vs long duration), real vs nominal
   rates, credit spread, the US dollar vs other currencies, energy, industrial metals,
   precious metals, agriculture. Two long-duration Treasury ETFs are one bet, not two.
2. **Non-equity.** Core classes: government bonds / duration, inflation-linked, credit,
   currencies, commodities. Exclude instruments dominated by equity beta - equity sector
   ETFs, country/EM *equity*, most REITs, MLP/energy-equity. Note that high-yield credit
   behaves partly like equity in a crisis; flag it.
3. **Trend persistence.** Prefer instruments whose price history shows sustained,
   directional trends (rates regimes, currency cycles, commodity bull/bear runs) rather
   than fast mean-reverting chop. This is what makes a decorrelated book also a *trend*
   substrate.
4. **Liquidity.** Real AUM and average daily dollar volume - enough to trade without
   outsized impact. When two ETFs track the same exposure, keep the liquid leader.
5. **History.** Daily data on Yahoo Finance going back to at least **2018-01-01**, with
   few gaps. Anything launched after 2018 cannot be in the core; flag inception dates.

## A starting candidate pool (expand and prune - not a shortlist to accept)

- **Rates / duration:** SHY, IEI, IEF, TLT, EDV, VGLT, GOVT; ex-US govies BWX, IGOV,
  BNDX; EM bonds EMB, EMLC, VWOB.
- **Inflation-linked:** TIP, STIP, VTIP, SCHP.
- **Credit (half-equity in stress - flag):** LQD, VCIT, HYG, JNK, BKLN, ANGL, EMHY.
- **Currencies:** UUP, USDU, UDN, FXE, FXY, FXB, FXF, FXA, FXC, CEW, CYB.
- **Commodities - broad:** DBC, PDBC, GSG, COMT, BCI, DJP.
- **Energy:** USO, BNO, DBO, USL, UNG, UNL, UGA.
- **Metals:** GLD, IAU, SLV, PPLT, PALL, CPER, DBB, DBP.
- **Agriculture / softs:** DBA, CORN, WEAT, SOYB, CANE, BAL, JO, NIB.

Cautions:
- Avoid **"rented convexity"** instruments - VIX ETPs (VIXY, VIXM), levered/inverse
  products. They bleed a structural premium and are not a trend substrate.
- Watch **known structural issues** - e.g. the 2020 oil-futures dislocation hit some
  crude trackers (USO) hard; prefer cleaner term-structure products where they exist.
- A few currency / single-commodity ETFs are **thin**; confirm liquidity before including.

## What to deliver (text we can read and act on)

For each tier, a table with: `ticker | asset class | what exposure it gives | why it adds
independent risk here | rough liquidity (AUM or volume) | Yahoo inception/history | trend
character`. Then the **bare ticker list per tier** (so we can paste it straight into a
backtest). Finally, a short note on **where you expect the independent-bet count to
plateau** - liquid non-equity ETFs are not infinitely orthogonal, so if the real ceiling
is below 50, say so and recommend the honest number X.

Cite sources for liquidity, inception, and any correlation/diversification claims you
lean on. State confidence honestly: if two instruments are near-substitutes, say which
you kept and why; if a claim rests on a single source or your own reasoning rather than
data, say that. We will validate the proposed universe in our own backtest - your job is
to give us the best-reasoned, best-sourced candidate list to test, not to prove it.
