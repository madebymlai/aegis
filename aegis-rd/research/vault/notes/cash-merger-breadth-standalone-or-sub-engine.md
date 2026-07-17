---
title: Cash-merger breadth — standalone sleeve or sub-engine?
date: 2026-07-16
tags:
  - demeter
  - convergence
  - merger-arbitrage
  - breadth
  - implementation
status: research-decision
---

# Cash-merger breadth — standalone sleeve or sub-engine?

Related: [[cash-merger-completion-probability-model]], [[massive-data-for-cash-merger-convergence]], [[finding-a-buildable-convergent-engine]], [[the-tiered-strategy-roster]].

> [!decision]
> **The economic opportunity set is broad enough for merger arbitrage to be a standalone institutional strategy. The current Demeter prototype is not.** Its average `1.7` invested deals and 14 usable historical observations measure a discovery/reconstruction failure, not actual deal scarcity.
>
> For Demeter, cash mergers should remain a **candidate sub-engine** until the local point-in-time tape proves at least ten concurrently eligible deals after liquidity, whole-share and data-quality filters. Fifteen to twenty is the preferred operating range. A proprietary completion model is not the first requirement: the first credible benchmark is a diversified, market-implied high-completion-probability strategy. Cash and short bills are valid when breadth is below the minimum.

## The broad search changed the diagnosis

The earlier prototype asked the wrong question. Its fixed `90%` success assumption turned sparse opportunities into concentrated directional opinions. The research question is instead:

1. Is there a sufficiently broad population of independent signed deals?
2. Does enough of that population remain concurrently open after cash-only, liquidity and executability filters?
3. Can a small book express that breadth without costs and whole-share granularity consuming the premium?
4. Is a learned completion model necessary, or can a transparent priced-risk benchmark be tested first?

The answer to the first two questions is **yes in the market, not yet in our tape**. The answer to the third is **mechanically plausible but economically tight**. The answer to the fourth is **no: do not block the benchmark on a learned model**.

## Historical breadth is not scarce

| Evidence | Deal population | Breadth result | What it establishes |
| --- | --- | --- | --- |
| Baker and Savaşoğlu, 1981–1996[^baker] | 1,335 usable pure-cash offers, about 83 per year | Median resolution for the broader sample was about 120 days | Even the older U.S. listed sample supplied dozens of concurrent positions; fixed costs were already identified as a serious small-investor constraint |
| Van Tassel, 1996–2012[^vantassel] | 2,856 cash deals, 78% successful, average duration `0.31` years | The equal-weight cash portfolio averaged **52 active deals** | This directly rejects the idea that one or two live cash deals is normal market breadth |
| Ricks, 1996–2018[^ricks] | 1,763 manually verified signed deals with U.S. public targets and value of at least $1 billion; 844 were all-cash | About 37 large all-cash signed deals per year before adding smaller targets | Even a restrictive large-deal universe is compatible with roughly ten or more concurrent positions |
| Definitive Merger Agreement Corpus, 2000–2020[^dma] | 7,929 SEC-filed definitive agreements above $100 million | Free agreement text and metadata provide a much wider historical discovery seed | The historical discovery problem can be bootstrapped without treating current tickers or one API taxonomy as the universe |

Van Tassel's counts are internally consistent: about `2,856 / 17 = 168` cash deals per year multiplied by a `0.31`-year average duration gives about `52` open deals. That is the observed average cash-portfolio breadth reported in the paper. It is not an extrapolation from announcement volume alone.[^vantassel]

Ricks is the narrower and more relevant check because every deal had a signed definitive agreement and a public U.S. target. His sample produced 90 outright failures and 17 reductions in consideration out of 1,763 deals; 89.6% completed on the original terms. The market-implied day-one failure probability averaged 12.7%, versus 5.1% realized outright failures, and it was higher for deals that later failed.[^ricks]

> [!important] What the prototype's census means
> `3,000 disclosures → 35 candidates → 14 provisional observations` is not a census of the merger market. It is the recall of one `merger_agreement` taxonomy route plus a conservative text parser and two years of free price history. The literature and live products show an order-of-magnitude wider investable set.

## Live implementations confirm concurrency

The result is not confined to old academic samples:

- The Water Island index methodology expects **30–50 targets** at each twice-monthly reconstitution. SEC filings report 64 long and 17 short positions in August 2024 and 49 long and 16 short positions in August 2025.[^arb]
- ProShares' S&P Merger Arbitrage implementation reported **39 deals, 52 equities and 15.59% cash** on 31 March 2026.[^mrgrfact]
- ProShares' live holdings on 15 July 2026 contained 39 listed target-equity lines before the fund's index swaps and FX hedges.[^mrgr]
- NYLI's MNA fact sheet reported 64 holdings at 31 December 2025.[^mna]

These products include stock and foreign deals, so their headline counts are not identical to a U.S. fixed-cash universe. They nevertheless falsify the premise that the live opportunity set normally contains only one or two merger targets. Ricks' 844 large all-cash transactions supply the cash-only cross-check.[^ricks]

Institutional methods also do not force deployment. ProShares leaves unallocated weight in cash; its March 2026 snapshot held 15.59% cash.[^mrgrfact] The NYLI prospectus similarly directs insufficient target capacity into short-term fixed-income instruments and warns that low deal flow can create significant cash allocations.[^mnaprospectus]

## The minimum breadth is explicit in the evidence

Van Tassel computes returns only in months with at least **ten** qualifying deals and caps every position at **10%**. The high-probability variant admits deals with share-implied success probability of at least `70%`; an `80%` cutoff was reported as a robustness check.[^vantassel]

That gives a defensible hierarchy for Demeter:

| Concurrent eligible deals | Interpretation |
| --- | --- |
| `< 10` | Not a standalone merger sleeve; remain in cash or treat merger as one component of a broader convergence book |
| `10–14` | Minimum diversified benchmark, but 10% name caps and break-risk concentration remain coarse |
| `15–20` | Preferred minimum for risk-based sizing in a small systematic implementation |
| `30–50` | Normal breadth of broad institutional/index implementations |

Ten is a research-backed floor, not proof of safety. A 10% position that loses half its value on a break costs 5% of sleeve NAV. Demeter should additionally cap expected contribution to break loss and hold cash rather than inflate the remaining names.

## A learned completion model is optional for the first benchmark

The fixed `q=0.90` prototype was invalid because it overrode the market with an unsupported belief. That does **not** imply that merger arbitrage requires proprietary prediction alpha before it can earn anything.

Van Tassel constructs a market baseline from target price, offer value and estimated fallback price. A portfolio restricted to deals with market-implied success probability of at least 70% had similar alpha, about half the monthly volatility, and a Sharpe ratio more than 50% higher than the equal-weight all-deal portfolio in that sample.[^vantassel] The interpretation is compensated deal risk with better risk selection, not a claim that the model knows more than the market.

The correct first benchmark is therefore:

$$
q_{mkt,t}=\frac{P_t-B_t}{O_t-B_t},
$$

with point-in-time offer `O`, target price `P`, and conservative pre-announcement fallback `B`. Admit only signed fixed-cash deals with `q_mkt ≥ 70%` or `80%`, nonnegative executable spread, known lifecycle state, and sufficient liquidity. Size with absolute name and break-loss caps. Do not insert an independent `q_model` until it beats `q_mkt` strictly out of time.

This is an important correction to [[cash-merger-completion-probability-model]]: **lack of enough failures for a residual prediction model blocks a proprietary selection claim, not the diversified merger-risk-premium benchmark.**

A new 2026 study shows that residual forecasting edge is possible, but also how demanding the real problem is. Its specialist long-context system classified original-terms completion, improved terms and termination across hundreds of pages of point-in-time evidence. On 404 held-out large global deals it achieved a class-balanced Brier score of `0.151`, versus `0.199` for calibrated market-implied probabilities and `0.186` for a structured XGBoost baseline.[^jajal] The relevant lesson is not “use an LLM now.” It is that any later residual model needs a large historical cohort, three-state labels, current filings, ownership, financing, regulatory state and strict point-in-time evaluation.

## Failure observations are still scarce for machine learning

Breadth for diversification and breadth for probability estimation are different quantities.

- Van Tassel's broader offer population records 22% unsuccessful cash deals, but its inclusion and outcome rules are broader than the signed, original-terms fixed-cash strategy.[^vantassel]
- Ricks' manually verified definitive public-target population records only 90 outright failures and 17 price reductions over 23 years. Rare original-term adverse outcomes, not daily price rows, determine the effective sample size.[^ricks]
- One failed deal contributes one independent terminal outcome. Treating its 100 daily observations as 100 labels is leakage and false precision.

Broader SEC discovery can turn 14 observations into hundreds, but the free two-year Massive price entitlement still spans too few regimes and likely too few signed-deal failures for a flexible completion model. Massive Basic exposes only two years of stock-price history, while the filing endpoints do not themselves solve price/outcome joining.[^massivebars][^massive8k]

The free `dma_corpus` is the cleanest historical bootstrap: it supplies metadata and the original EDGAR filings for 7,929 definitive agreements above $100 million from 2000–2020.[^dma] It does **not** by itself supply cash-only classification, outcome labels, historical tradable identity, offer amendments or survivor-safe prices. Those still require deterministic joins and validation.

## Whole shares are not the primary blocker

The 15 July 2026 ProShares target-equity snapshot provides a useful executable-price sanity check. From its first-party market values and share counts, the 39 target lines ranged from about `$5.21` to `$328.54` per share, with a median around `$46`; 38 of 39 were below `$250`.[^mrgr]

For a €5,000 sleeve:

- a 10-name, 10%-cap benchmark allocates roughly €500 per name and can express at least one share in the observed target set;
- a 20-name, 5%-cap benchmark allocates roughly €250 per name and would exclude or underweight only the highest-priced names in that snapshot;
- whole shares distort exact break-risk weights, but they do not explain why the prototype found only 1.7 positions.

The larger small-book problem is **cost relative to a thin premium**. At `0.31` years average duration, maintaining ten names implies roughly 32 entry/exit cycles per year. At €0.35 per order, fixed commissions alone are approximately €22 annually, or 45 bps on €5,000, before slippage, FX and idle-cash effects. Twenty maintained names roughly doubles that fixed-ticket drag. Baker and Savaşoğlu explicitly identify fixed transaction costs as a reason diversified merger arbitrage is difficult for individuals.[^baker]

Modern return expectations must also be conservative. Mitchell and Pulvino's old implementable portfolio lost most of its gross alpha after transaction costs and practical constraints, while later research documents that merger spreads declined by more than 400 bps after 2002 as capital and trading increased.[^mitchell][^jetley] ProShares reported annualized returns since its December 2012 inception of 2.15% for the fund and 3.17% for the index through March 2026.[^mrgrfact] Breadth solves concentration; it does not guarantee that the remaining premium clears today's cash yield and this account's costs.

## What to build next

The next iteration should test **coverage before cleverness**:

1. Seed historical discovery from the Definitive Merger Agreement Corpus and SEC `8-K`, `DEFM14A`, `Schedule TO`, and `SC 14D-9` filings; use Massive's disclosure taxonomy as a current incremental feed, not as the historical universe.
2. Reconstruct original terms, every amendment, completion and termination by CIK/accession, with next-session availability.
3. Join survivor-safe target prices and dividends, then measure rolling concurrent breadth after fixed-cash, liquidity, whole-share and broker-eligibility filters.
4. Run the transparent `q_mkt ≥ 70%` and `q_mkt ≥ 80%` benchmarks with 10% absolute name caps, break-loss caps, costs and cash.
5. Only after that benchmark exists, test whether a parsimonious residual completion model improves Brier score, log loss and whole-book utility on strictly later deals.

> [!success] Promotion rule
> Promote cash mergers from sub-engine candidate to standalone Demeter candidate only if the reconstructed tape has at least ten eligible concurrent deals in every invested month, preferably 15–20, and the cost-aware strategy has positive marginal utility beside trend on untouched later data. If concurrency regularly falls below ten, preserve the mechanism as a sub-engine and diversify Demeter with another independently triggered convergence premium.

## July 2026 breadth and formula audit

The repaired one-year prototype was rerun with the same point-in-time lifecycle tape, whole-share execution, costs, drift bands and market-implied-probability signal. Only the probability cutoff and lifecycle capacity changed.

| Control | Median / maximum names | Mean target gross | Net return | Excess over three-month bills | Convergent utility delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| `q70`, 20 slots | 20 / 20 | 79.8% | 3.48% | 0.84% | 0.76% |
| `q70`, 30 slots | 23 / 29 | 61.3% | 2.64% | 0.01% | -0.04% |
| `q70`, 40 slots | 23 / 27 | 45.6% | 1.74% | -0.89% | -0.90% |
| All deals, 40 slots | 25 / 30 | 49.0% | 0.76% | -1.87% | -1.91% |
| `q80`, 40 slots | 23 / 27 | 42.8% | 1.38% | -1.25% | -1.25% |

> [!warning] This is not evidence that breadth destroys alpha
> The slot experiment coupled breadth to weight: a 20-slot portfolio used at most 5% per deal, while 30 and 40 slots used at most 3.33% and 2.5%. Because unused simulator cash earned zero, average deployment fell sharply as nominal capacity increased. The comparison therefore mixes breadth, risk and cash yield. It cannot identify a breadth effect.

The useful result is mechanical: the repaired tape supported 23–25 median names and as many as 30, so the earlier scarcity diagnosis is dead. The 20-slot control also remained the strongest in this reused sample, but it held only four terminated deals. Its apparent edge is not a promotion result and must not be optimized further on the same year.

### The probability algebra is right; its state estimates are still naïve

The current formula

$$
q_{mkt,t}=\frac{P_t-B_t}{V_t-B_t}
$$

is the correct two-state market-implied probability identity. The implementation's fixed median of the last 20 pre-announcement closes is a defensible naïve fallback, but it is not the strongest current specification. Jajal et al. use:[^jajal]

$$
V_t=\text{cash consideration discounted to the expected close date},
$$

and

$$
B_t=B_0\exp\!\left(\beta r_{m,[0,t]}\right),
$$

where $B_0$ is the **mean** of the 20 pre-announcement closes, $\beta$ is estimated before announcement and $r_{m,[0,t]}$ is the market's cumulative log return since announcement. Causal offer amendments update $V_t$. They clamp the resulting probability to $[0,1]$ and find that it benefits from out-of-time Platt calibration.

This does not turn `q_mkt` into proprietary alpha. It remains a market price transformed into probability space. Its first job is risk selection and sizing. A genuine deal-selection claim requires a point-in-time forecast of completion, higher bid and negative termination that improves calibration and net portfolio utility beyond this market baseline.

### The portfolio algorithm needs a clean benchmark pair

Published implementations support two distinct controls, neither of which is identical to the prototype's `1 / maximum_slots` lifecycle lock:

1. Van Tassel's academic control enters after the announcement delay, requires at least ten deals, caps names at 10%, and rebalances monthly.[^vantassel]
2. The investable S&P/ProShares construction admits up to 40 deals, initially weights targets at 3%, and holds unused capital in three-month Treasury bills.[^mrgrfact]

The next prototype must therefore compare, without tuning on this year:

- a monthly, capped, equal/risk-weighted `q70` control; and
- a fixed-entry-weight, up-to-40 `q70` control with an explicit bill reserve.

Both should use the beta-adjusted fallback and discounted offer described above. Entry-risk sizing may then cap either construction at a fixed portfolio break-loss contribution. This isolates the economic questions: whether broader deal participation adds value, whether turnover consumes it, and whether the probability filter improves tails rather than merely lowering exposure.

### Frozen alpha-v2 outcome

The corrected pair was frozen before rerunning the reused July 2025–July 2026 history:

- `q70_monthly_capped`: first-observed session monthly reconstitution, at most 40 names, equal weight capped at 10% and 2% portfolio fallback-break loss;
- `q70_fixed_entry_40`: 3% initial entry weight, at most 40 names, the same absolute name and break-loss caps, held to lifecycle resolution.

Both use a causally updated offer, a 175-day default close horizon, a risk-free-discounted success value, a 20-day mean fallback evolved by pre-announcement beta and SPY, whole shares, costs and a three-month-bill reserve. The implementation retained 121 lifecycles, including eight with causally dated offer changes; three lacked reconstructable causal offer history, one lacked price history and two lacked the minimum beta history.

| Frozen construction | Net return | Excess over bills | Utility delta | Mean gross / bill reserve | Median names | Held completions / terminations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Monthly capped | 4.93% | +2.30% | +2.19% | 53.7% / 46.4% | 10 | 22 / 3 |
| Fixed entry | 1.48% | -1.16% | -1.22% | 40.7% / 59.3% | 18 | 29 / 4 |

> [!warning] One integrity repair preceded the accepted result
> A first run synthetically settled completed deals at the filing parser's `latest_offer_price`. CIO exposed the flaw: the parser extracted `$25` while the stock remained near `$6.80`, creating a false one-day gain. The accepted run never substitutes parsed consideration for a market mark; it exits on the last adjusted traded mark. No signal threshold, weight or portfolio rule changed.

> [!decision]
> **Iterate the frozen monthly construction historically; kill the fixed-entry construction under this gate; promote neither.** Monthly clears bills and utility after costs, but only three held terminations and one reused year cannot establish its break-loss distribution or its contribution beside Atalanta. The next test must preserve the frozen construction on longer, untouched lifecycle history rather than tune this sample.

### Two-year entitlement extension

Massive's rolling entitlement permitted a causal census from 17 July 2024 through 16 July 2026. The source reconstructed 555 observations into 232 fixed-cash deals: 147 completed, 22 terminated and 63 pending. Current-reference recall was 94.7%; median active breadth was 39, maximum breadth was 73, and at least ten deals were active on 96.8% of calendar days.

The unchanged alpha-v2 contract retained 206 lifecycles after excluding three without reconstructable causal offers, nine without sufficient price history and fourteen without the frozen minimum beta history. This is the accepted extended result:

| Frozen construction | Cumulative net | CAGR | Bills CAGR | Cumulative excess | Utility delta | Median names | Held completions / terminations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Monthly capped | 8.98% | 4.41% | 2.88% | +3.17% | +1.47% | 13 | 34 / 5 |
| Fixed entry | 4.14% | 2.05% | 2.88% | -1.68% | -0.86% | 18 | 56 / 9 |

The monthly construction averaged only 30.5% target gross and 69.6% in the bill reserve; the result is therefore a sparse event overlay plus cash, not a fully invested equity strategy. Fixed entry averaged 44.2% gross yet still failed bills and utility, reinforcing its kill rather than blaming its result solely on underdeployment.

> [!success] What the extension settles
> The positive monthly result was not confined to the original July 2025–July 2026 window. With its design frozen, the expanded history still cleared bills after whole-share execution, costs and reserve accounting. The mechanism now qualifies for paired whole-book research beside Atalanta.

> [!warning] What it does not settle
> The expanded history is a frozen historical extension, not live out-of-sample evidence. Only five terminated deals were held by the monthly construction, daily and downside L-skew remained positive in this realized sample, and the entitlement does not include a broad merger-break stress regime. Do not promote it to Demeter from these two years; preserve the monthly contract and obtain more adverse lifecycle evidence or forward shadow history.

## 2026-07-17 — What can improve the frozen prototype beyond `q_mkt`

> [!decision]
> **Do not replace the frozen monthly strategy with a generic completion classifier.** The strongest next challenger is a causal **event-time hazard overlay**: retain the `q_mkt >= 70%` risk gate, but rank the surviving deals by their out-of-time probability of resolving successfully during the next holding interval relative to break loss and costs. The second credible challenger is a **two-week non-price reaction model** using target turnover, quoted spread and realized volatility, with `q_mkt` retained as the baseline feature. Contract terms and regulatory milestones belong in the state and risk model; options and media NLP are research leads, not the next implementation.

The wide search found no robust basis for swapping in one more opaque probability. The evidence instead separates four jobs that the naïve probability collapsed:

1. `q_mkt` summarizes the market's current terminal success assessment, conditional on an estimated fallback.
2. A completion and withdrawal **hazard** estimates when each resolution can occur, conditional on the deal still being alive.
3. Deal terms, regulatory milestones and financing conditions describe the **mechanisms** that can change those hazards and the loss conditional on failure.
4. Portfolio construction converts those deal-level estimates into expected net return without concentrating common break states.

The economic ranking target is therefore not completion probability alone. For the next monthly holding interval it is approximately

$$
\operatorname{ENP}_{i,t}
=h^+_{i,t}(V_{i,t}-P_{i,t})
-h^-_{i,t}(P_{i,t}-B_{i,t})
-C_{i,t},
$$

where $h^+$ and $h^-$ are the conditional next-interval completion and adverse-resolution probabilities, $V$ is the discounted prevailing consideration, $B$ is the market-adjusted fallback and $C$ contains executable trading, FX and funding costs. This is a ranking score, not a claim that unresolved deals earn zero mark-to-market return during the interval.

### The decisive lead is event time, not another static deal score

Giglio and Shue estimate completion and withdrawal hazards on more than 5,000 mergers. Completion hazard is strongly hump-shaped over event time, peaking around week 25, while withdrawal hazard is approximately flat. Crucially, the return result survives a split-sample design in which hazards are estimated on an earlier cohort and returns are measured later: a high-hazard strategy earned 105 bps monthly factor alpha versus 33 bps for low-hazard windows and 71 bps for conventional buy-and-hold.[^giglio-shue]

That result maps directly onto the frozen monthly implementation. Monthly reconstitution is already the winning lifecycle rule; it is the natural point at which to update a deal's next-month completion hazard. The paper's `week 20–30` result must **not** become a hard-coded current-sample switch. Estimate a weekly or monthly hazard table only from deals resolved before the evaluation period, stratified parsimoniously by cash consideration and broad size where the training sample permits, then carry the table forward unchanged.

The first challenger is therefore:

- preserve `q70_monthly_capped`, whole shares, bill reserve, costs, 40-name capacity, 10% name cap and 2% fallback-break-loss cap exactly;
- add `deal_age_days` and two out-of-time lookup values, `next_month_completion_hazard` and `next_month_adverse_hazard`;
- admit only the same `q_mkt >= 70%` deals, then rank positive `ENP` rather than equal-ranking every survivor;
- send unused capital to the same bill reserve; never relax the gate or cap to fill the book;
- freeze the hazard estimator before the first evaluation date and compare on strictly later deals.

This is the smallest economically identified change. It asks whether the market underprices the timing of convergence while leaving the existing downside, accounting and execution contract untouched.

### Non-price reactions are the strongest second-stage residual signal

Lee finds that the target's trading-volume, bid–ask-spread and return-volatility reactions during the two weeks after announcement predict renegotiation, slower completion and failure even after controlling for the merger spread and announcement return. A low-predicted-failure portfolio earned positive abnormal returns.[^lee] This is exactly the form of evidence needed for a residual model: observable post-announcement information with incremental content beyond price.

It is not yet the first challenger for this repository. A faithful implementation needs point-in-time quoted spreads as well as survivor-safe volume and prices, and it deliberately waits two weeks before scoring. Dropping the spread feature or measuring it from today's data would turn the paper into a different strategy. Once the quote tape exists, the appropriate model is deliberately small:

$$
\operatorname{logit}(p_{i,t})
=\alpha+\beta\operatorname{logit}(q_{mkt,i,t})
+\gamma_1\Delta\text{turnover}_{i,[0,10]}
+\gamma_2\Delta\text{quoted-spread}_{i,[0,10]}
+\gamma_3\Delta\text{realized-vol}_{i,[0,10]}.
$$

Train and calibrate it on earlier deals only. Its admission test is incremental out-of-time Brier/log loss and, more importantly, net whole-book utility versus the event-hazard challenger. Daily observations from one deal are not independent outcome labels.

### Contract terms are state variables, not free alpha coefficients

The agreement contains economically real failure mechanisms: financing conditions, shareholder votes, regulatory approvals, outside dates, MAE allocation, competing bids and termination provisions. Ricks reports that signed deals requiring an acquirer-side shareholder vote had almost twice the adverse-outcome incidence of deals without that extra veto point.[^ricks] MAC-clause research likewise finds that MAEs underlie a large fraction of terminations and renegotiations and that fewer exclusions are associated with wider spreads.[^mac]

But these clauses are negotiated jointly with deal risk. Termination-fee research explicitly warns that the fee and other deal attributes are endogenous, while later SEC-based work finds earlier conclusions about termination provisions sensitive to biased data.[^bates-lemmon][^boone-mulherin] The frozen prototype should therefore:

- parse and timestamp these terms as lifecycle state;
- use financing conditions, acquirer votes and unresolved material regulatory challenges for scenario tags and risk caps;
- update state only after the relevant filing or official decision is public;
- avoid adding hand-chosen probability points such as `+5% for a termination fee`;
- estimate any coefficient only on the future historical backfill, with agreement vintage and deal type controlled.

Regulatory and contract state should also drive portfolio aggregation. Deals sharing an acquirer, narrow industry overlap, regulator or financing sponsor are not independent merely because they have different tickers. Add report-only concentration by those break mechanisms first; promote caps only after a frozen stress rule is specified.

### Options contain information, but fail the next-build test

Target options can identify the probability mass at a fixed cash offer and predict outcomes beyond the target share price. Van Tassel finds that the estimated option-based risk-neutral probability remains informative after share-implied probability and controls.[^vantassel] Bester, Martinez and Roşu independently estimate a latent success probability and fallback from target shares and calls and find significant incremental predictive power.[^bester-options]

The implementation surface is poor for Demeter's broad small-name universe. In Bester et al.'s 812-deal cash-merger sample, at least one option traded on only 65% of deal-days on average and call bid–ask spreads averaged 27.5%.[^bester-options] This signal should remain a research-only coverage audit. Do not shrink the merger universe to optionable targets or treat stale option midpoints as clean probabilities without first showing that the surviving breadth and quote quality improve the portfolio.

### Media NLP is evidence of alpha but not a clean data contract

Buehlmaier and Zechner find that a media-implied completion probability predicts subsequent merger-arbitrage returns beyond prices; excluding the lowest 28% raised annualized alpha by 9.3 percentage points in their sample.[^media] That is meaningful evidence that public text can contain underreacted information. It is not a clean next build here: historical articles are revised, timestamp entitlement is difficult to audit, and a web-search reconstruction can leak later resolution facts. Revisit it only with an immutable point-in-time news archive and a frozen textual model.

### Exact recommendation for the frozen prototype

1. **Keep `q70_monthly_capped` unchanged as the benchmark.** Do not reinterpret its two-year extension as a training set.
2. **Build only one immediate challenger:** `q70_monthly_event_hazard`, identical except for out-of-time next-month completion/adverse hazards and `ENP` ranking.
3. **Backfill before evaluating.** Estimate hazards and clause effects on a historical cohort ending before the evaluation start; the current two years contain too few held breaks.
4. **Pre-register the comparison:** net return over bills, convergent utility delta, fees, turnover, mean gross, held completions/terminations, worst break contribution, and paired utility beside Atalanta. Also report Brier/log loss for the hazard probabilities, but do not optimize the portfolio on them.
5. **Queue the non-price residual model behind quote-history availability.** It is the next genuine probability improvement, not a substitute feature approximation.
6. **Do not implement options, media NLP or a broad ML classifier now.** They add data and leakage surface before the simple event-time hypothesis is tested.

> [!success] Promotion criterion
> The hazard challenger advances only if it beats the unchanged monthly control on an untouched later cohort after bills and executable costs, while preserving or improving worst-break contribution and paired utility. If it merely changes exposure or wins through one fewer break, retain the simpler control and continue forward shadowing.

> [!note] Supersession
> The dated section above supersedes the older final recommendation where they conflict. The two-year census has now satisfied the local breadth condition; the unresolved gates are adverse-regime history, untouched evaluation and paired utility beside Atalanta.

## 2026-07-17 — Event-time and sparse-breadth prototype evaluation

Two challengers were frozen and evaluated on the common period from 1 August 2025 through 15 July 2026. The evaluation boundary is a runner input, not strategy state: hazard training ends automatically on the preceding day, and each training label runs from a monthly observation to the next calendar-month boundary.

The unchanged `q70_monthly_capped` control remained the leader:

| Construction | Net return | Excess over bills | Utility delta | Cash-excess Sharpe | Maximum drawdown | Mean deal gross | Held completions / terminations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `q70_monthly_capped` | 4.81% | +2.31% | +2.31% | 1.16 | -0.83% | 56.7% | 24 / 4 |
| `q70_monthly_event_hazard` | 2.50% | 0.00% | 0.00% | 0.00 | 0.00% | 0.0% | 0 / 0 |
| `q70_monthly_scaled_breadth` | 3.61% | +1.11% | +1.07% | 0.44 | -1.73% | 75.5% | 26 / 5 |

### Event-time ENP is killed in its tested form

The out-of-time training cohort supplied only 226 monthly survival observations, 43 next-month completions and five adverse resolutions. Completion incidence was 17.3% in weeks 0–11, 23.9% in weeks 12–35 and unobserved in the three late observations; pooled adverse incidence was 2.21%.

After the unchanged `q_mkt >= 70%` gate, positive expected-net-payoff breadth ranged from zero to three deals per month. It never reached the unchanged ten-name minimum, so the challenger correctly remained entirely in bills. This is not evidence against event-time effects generally. It kills this locally estimated ENP implementation: its training cohort is too small, especially for adverse and late-event hazards, to support a diversified portfolio.

### The ten-name switch is selective, not merely wasteful

The eligibility audit found that whole-share affordability never removed a deal. Causal offer coverage was also nearly complete. The main reductions were:

1. The valid two-state payoff condition, which removed roughly half of raw active lifecycles because price did not lie between the estimated fallback and discounted offer.
2. The $1 million trailing median dollar-volume requirement.
3. The `q70` risk gate.

The final `q70` count was below ten in four of twelve evaluation months: 3, 8, 9 and 7. A predeclared proportional rule therefore held each sparse-month name at at most 10%, instead of liquidating the sleeve. It increased invested-day fraction from 64% to 100% and mean deal gross from 56.7% to 75.5%, but halved excess return and utility, reduced Sharpe from 1.16 to 0.44, and doubled drawdown. Most damage occurred in September and October 2025. It also admitted one additional termination, STAA, alongside two additional completions.

> [!decision]
> **Kill both challengers and retain the simpler `q70_monthly_capped` control.** The event-hazard model cannot form a diversified positive-ENP book from the available out-of-time cohort. The binary breadth rule improved this reused sample by avoiding weak sparse months; replacing it with continuous exposure made the strategy worse. Do not tune either failure. The surviving control can proceed to paired floor evaluation, but still cannot be promoted from only four held terminations in the common period.

Prototype evidence: `_prototyping/merger/historical/FROZEN_ALPHA_V3.md`, `_prototyping/merger/historical/FROZEN_ALPHA_V3B.md`, and `_prototyping/merger/historical/alpha-report-v3b.json`.

## 2026-07-17 — Closing guidance is an interval; the strategy needs a hazard

> [!decision]
> **Do not replace the 175-day fallback with another guessed completion date.** Preserve management guidance as a point-in-time interval, preserve the contractual outside date and its extension rights separately, and convert both into a conditional completion-time distribution. Timing then enters expected net payoff directly. A successful-close annualized spread is useful only as a scenario report, not as the selection score.

### The filings answer different questions

The SEC filing lifecycle provides enough public information to build a causal timing state, but no single field is “the closing date.” Form 8-K Item 1.01 requires the material terms of a signed agreement and material amendments; SEC staff guidance says that, for a business combination, those terms generally include material closing conditions and anticipated timeframes for the proxy or tender filings and closing. Item 1.02 covers termination.[^sec-8k-form][^sec-8k-cdi]

Use the documents according to their economic role:

| Lifecycle fact | Primary point-in-time source | Meaning for the model |
| --- | --- | --- |
| Signed terms and outside-date mechanics | Item 1.01 Form 8-K and the merger agreement, usually Exhibit 2.1 | Contractual conditions, termination rights, automatic or elective extensions; **not** the expected close |
| Initial management guidance | Announcement release, commonly Exhibit 99.1 to the 8-K | A soft forecast such as “Q4 2026,” “second half” or “in 2026” |
| One-step merger process | `PREM14A`, then `DEFM14A`, with the agreement commonly annexed | Updated timing, vote date, conditions and transaction background |
| Tender process | Schedule TO and Offer to Purchase; target Schedule 14D-9 | Scheduled offer expiry, extension rules, conditions and target response |
| Changed terms or deadline | Item 1.01 8-K plus amendment exhibit; `SC TO-T/A` or `SC 14D-9/A` for tenders | A new observation that supersedes prior state only from its publication time |
| Vote, closing or termination | Items 5.07, 2.01 or 1.02 of Form 8-K, respectively | A realized milestone or absorbing lifecycle state |

An actual Informatica filing illustrates why the distinction matters: the agreement had a 26 May 2026 outside date subject to two extensions of up to three months for regulatory approvals.[^informatica-outside] The outside date is therefore neither a promised closing date nor necessarily an automatic failure date. Tender offers have an additional explicit clock: Schedule TO disclosure includes the scheduled expiration and how the offer may be extended, while amendments report extensions, expiry and changed terms.[^tender-rules][^schedule-to-example] A registration statement can say only that the parties expect to close “in 2026” while warning that the actual date cannot be predicted because conditions remain outside their control.[^s4-guidance-example]

### Preserve the observation before interpreting it

Each guidance or outside-date record should be immutable and carry at least:

- `observed_at`, accession number, source form and source authority;
- the raw phrase and nearby qualifying text;
- `window_start`, `window_end` and `precision`;
- contractual extension count, length, trigger and exercising party for an outside date;
- a link to the observation it supersedes.

Normalize language without manufacturing precision:

| Filed language | Causal representation |
| --- | --- |
| Exact date | One-day interval |
| `Q4 2026` | 1 October through 31 December 2026 |
| `H2 2026` / second half | 1 July through 31 December 2026 |
| `in 2026` | 1 January through 31 December 2026 |
| `by year end` | Interval ending 31 December, beginning no earlier than the observation date or the previously stated window |
| `early`, `mid`, `late`, `summer` | Explicit coarse interval with low precision; never silently convert to one day |

The filing becomes usable no earlier than its accepted timestamp and, for a date-only daily process, on the next trading session unless the timestamp proves it was available before the trading mark. Later guidance changes history only prospectively. Never backfill a revised quarter into earlier observations.

### Expected close is a conditional distribution

Jajal et al. infer expected time to close from company guidance and discount fixed cash consideration over that horizon; when guidance is missing, their benchmark uses the 175-day median for U.S. public deals.[^jajal] That is a useful research baseline, but a scalar date discards the uncertainty in quarter-, half- and year-level guidance. Giglio and Shue's competing-risk evidence is the stronger production shape: completion hazard is hump-shaped in deal age, while withdrawal hazard is much flatter, and both must be conditioned on the deal having survived so far.[^giglio-shue]

The clean model therefore keeps three separate objects:

1. `guidance_interval`: management's soft timing forecast;
2. `outside_date_state`: the current contractual boundary and extension mechanics;
3. `completion_hazard` and `adverse_hazard`: the probability mass of each resolution conditional on survival.

Management guidance shapes the completion-hazard prior by assigning probability mass across its interval; it does not collapse that mass onto the midpoint. The outside date constrains or changes the tail only according to the actual termination and extension clauses. Votes, regulatory decisions, financing changes and revised guidance update the hazards prospectively. If no guidance exists, use a hazard estimated on an earlier frozen cohort, stratified only as far as the data supports, rather than pretending every deal will close exactly 175 days after announcement.

Staleness is also informative. Once a guidance window passes without closing, retain the observation but increase `guidance_age`, reduce its weight and shrink toward the empirical survival hazard. Do not move the expected date forward mechanically. Surviving past an expected window or approaching an extendable outside date changes the conditional distribution; it does not imply either immediate completion or automatic failure.

### Timing belongs inside expected net payoff

With completion-time mass $\pi^+_{i,t}(u)$ and adverse-resolution probability $\pi^-_{i,t,\Delta}$ over the next holding interval $\Delta$, rank by:

$$
\operatorname{ENP}^{\Delta}_{i,t}
=\sum_{u\in(t,t+\Delta]}\pi^+_{i,t}(u)
\left[O_{i,t}D(t,u)-P_{i,t}\right]
-\pi^-_{i,t,\Delta}\left[P_{i,t}-B_{i,t}\right]
-C_{i,t},
$$

where $O$ is prevailing cash consideration, $D(t,u)$ is the risk-free discount factor, $B$ is the causal fallback estimate and $C$ includes executable trading, FX and funding costs. This replaces the single-date success value with the expected discounted offer over possible completion dates. It also avoids dividing a noisy spread by a guessed number of days, which can make a tiny timing error dominate the rank.

Practitioner spread annualization remains useful as a sensitivity table. The same 1.67% spread has a radically different headline annualized return if completion is assumed in one month rather than six months.[^aima-timing] Report successful-close gross IRR at the guidance-window start, midpoint and end—or at the completion distribution's 10th, 50th and 90th percentiles—clearly labeled conditional on success and before break losses and costs. Residual days between the public completion announcement and cash receipt also create real holding cost.[^jetley] Selection and promotion must continue to use net calendar-time returns over the bill reserve, not a chain of hypothetical annualized event returns.[^mitchell]

### Exact next experiment

1. Keep `q70_monthly_capped` unchanged as the benchmark.
2. Backfill immutable guidance and outside-date observations, including amendments and tender extensions, before evaluating any timing challenger.
3. Replace the challenger's fixed 175-day timestamp with an out-of-time conditional completion distribution shaped by the guidance interval, deal-age hazard and contractual extension state.
4. Rank the challenger by next-month `ENP`, with expected discounted consideration integrated over completion time; preserve all existing costs, caps, bill reserve and whole-share rules.
5. Report timing-scenario IRRs only as diagnostics. Judge the strategy by net calendar-time utility and its paired contribution beside Atalanta.
6. If a historical point-in-time guidance and amendment tape cannot be reconstructed, do not claim a historical timing alpha. Keep the 175-day version as the transparent benchmark and shadow the new state prospectively.

> [!warning]
> Closing guidance improves timing, not deal-break forecasting by itself. It does not supply the independent success probability that the original fixed 90% assumption lacked. A genuine risk model still needs causal market-implied probability and/or out-of-time deal-risk features; the timing hazard determines **when** each terminal state can occur.

## 2026-07-17 — Massive-only point-in-time timing prototype

The timing contract above was implemented in the throwaway prototype without scraping SEC filing URLs. The source boundary is Massive's structured 8-K text API. Each observation becomes usable on the next trading day; guidance remains an interval; stale guidance falls back to the median remaining duration of earlier completed deals that had already survived to the same age; and outside dates remain separate contractual facts. The outside date does not truncate expected close because the structured source does not fully encode automatic and elective extension mechanics.

Coverage over the 206 retained, priceable fixed-cash lifecycles was:

| Point-in-time fact | Deals covered | Coverage |
| --- | ---: | ---: |
| Closing guidance | 54 | 26.2% |
| Outside date | 70 | 34.0% |
| Both | 20 | 9.7% |

The pre-evaluation cohort contained 226 monthly survival observations, 43 next-month completions and five adverse resolutions. Guidance-conditioned cells were too small to use: for example, `early:in_guidance` had four observations and `high:in_guidance` had five. The frozen minimum-cell rule therefore correctly shrank them to the broader event-age hazard rather than fitting extreme 50%–60% rates from a handful of observations.

The timing-aware `q70_monthly_guided_enp` challenger found between zero and three positive-ENP names in every evaluation month and never reached the unchanged ten-name diversification floor. It therefore remained entirely in bills:

| Construction | Net return | Excess over bills | Utility delta | Mean deal gross |
| --- | ---: | ---: | ---: | ---: |
| Unchanged `q70_monthly_capped` | 4.81% | +2.31% | +2.31% | 56.7% |
| `q70_monthly_guided_enp` | 2.50% | 0.00% | 0.00% | 0.0% |

> [!failure] Iteration decision
> **Kill the Massive-only guided-ENP challenger and retain the unchanged `q70` control.** This does not reject point-in-time timing. It rejects claiming that Massive's structured 8-K item text is sufficient to backtest it: the missing exhibit, proxy and tender text leaves most deals unguided, while the historical failure cohort remains too small for an independent physical-probability model. Do not fill the gap by scraping SEC submissions or by treating the outside date as expected close.

Prototype evidence: `_prototyping/merger/historical/FROZEN_ALPHA_V4.md` and `_prototyping/merger/historical/alpha-report-v4.json`.

## 2026-07-17 — The missing timing data exists, but not in Massive alone

> [!important] Revised decision boundary
> Do **not** kill timing-aware merger arbitrage. Kill only the claim that Massive's structured 8-K item text is a sufficient timing source. The failed challenger measured provider incompleteness: it did not establish that point-in-time timing has no value.

The provider search found three distinct data jobs that should not be conflated:

| Data job | Best accessible source | What it supplies | Remaining limitation |
| --- | --- | --- | --- |
| Live normalized timing | [Wall Street Horizon through IBKR](https://www.wallstreethorizon.com/interactive-brokers) | Expected exact close date, or close month/quarter/half plus year; status, approval date, consideration and references | The current Gateway returned IBKR error `10276: News feed is not allowed`, so this account/session is not presently entitled. The ordinary live record must not be assumed to contain past revisions. |
| Causal historical timing | [Wall Street Horizon historical data](https://www.wallstreethorizon.com/historical-data) | M&A history archived as published; WSH reports roughly eight years of M&A history and offers history files separately | Public pages do not quote the archive price or confirm that it is included in the retail IBKR feed. Obtain a sample or entitlement confirmation before relying on it. |
| Full filed terms and amendments | [sec-api.io](https://sec-api.io/pricing) | Every EDGAR filing, exhibit and attachment from 1993 onward through a supported API rather than direct SEC-page scraping | The documents are not normalized merger terms. Expected-close language, outside dates and extension clauses still require a conservative, versioned extractor. |

WSH is the cleanest first repair. Its documented M&A record contains `close_date`, `close_time_period` and `close_year`; WSH says those fields reflect official company statements, while the close date can later become the actual close date.[^wsh-mergers] That last behavior is precisely why a latest-state record is unsafe for historical simulation. The required backtest asset is an **as-published revision tape**, keyed by the observation timestamp, not a final table of completed deals.

The lack of a normalized outside date should not block the first repaired challenger. Closing guidance answers **when** expected completion may occur and can replace the arbitrary 175-day horizon. The outside date is a contractual tail boundary whose effect depends on automatic and elective extensions; it should remain a later risk diagnostic until those clauses are represented correctly. It must not be substituted for expected close.

The affordable implementation path is therefore:

1. Use sec-api.io as the authoritative historical and live filing ledger. Its personal plan is currently $55 monthly or $49 monthly billed annually and includes historical filings and exhibits.[^sec-api-pricing]
2. Extract versioned offer terms, management closing guidance, outside-date mechanics and lifecycle changes from each filing as of `filedAt`. Keep market-implied completion probability as the risk gate; use closing guidance only to shape time-to-resolution.
3. Use WSH only as an optional normalized cross-check. Do not make the engine depend on it or assume its retail live record exposes prior revisions.
4. Re-run the timing challenger from immutable sec-api.io responses. If a reliable versioned extraction cannot be demonstrated, retain the `q70` control; do not manufacture historical timing from final records.

This sequencing uses one source for both historical and live event evidence, with IBKR remaining authoritative for prices and execution. Benzinga's M&A API also exposes expected and completed dates plus an update timestamp and forward webhooks, but its public documentation does not establish retrievability of prior record versions; it is therefore a forward-collection alternative, not a proven causal backfill.[^benzinga-ma]

## 2026-07-17 — sec-api.io trial call budget

The 100-call trial is enough to validate the document-to-ledger seam, but not enough for a market-wide backfill. The trial should answer one narrow question: can a conservative extractor reconstruct offer consideration, expected-close guidance, outside-date mechanics, approvals, amendments and resolution **as each filing became public** for a small set of already-known cash mergers?

The cheapest official path is the Filing Query API followed by complete-submission downloads:

- Use one date-bounded Query API request for four to six known target CIKs and the relevant form families. CIK is preferable to ticker for historical work because it survives ticker changes. A query returns at most 50 filings, including `filedAt`, accession number, filing URLs and `documentFormatFiles`; paginate only if the returned `total` exceeds 50.[^sec-api-query]
- Include `8-K`, `8-K/A`, `PREM14A`, `DEFM14A`, `SC TO-T`, `SC TO-T/A`, `SC 14D9`, `SC 14D9/A`, `SC 13E3` and `SC 13E3/A`. Within 8-Ks, retain Items 1.01, 1.02, 2.01, 5.07, 7.01 and 8.01. This covers agreement entry/termination/completion, votes and updates, plus merger proxies and tender/going-private lifecycles. sec-api.io specifically documents monitoring the `SC TO-T` and `SC 14D9` families and 8-K Items 1.01 and 2.01 for M&A.[^sec-api-stream]
- For each retained accession, download `linkToTxt` **once** through the Filing Download API. The complete-submission text contains the primary filing and all exhibits, while the Query response already lists every attachment and its type. Do not separately fetch `EX-2.*` merger agreements or `EX-99.*` press releases unless the combined text is genuinely unusable.[^sec-api-download]
- Use `filedAt`, which represents EDGAR's accepted timestamp in Eastern Time, as the observation time. Never infer availability from a date printed inside a contract or press release.[^sec-api-stream]
- Do not spend trial calls on the PDF Generator, XBRL converter, 10-K/10-Q/8-K section extractor, mapping API or broad Full-Text Search. None is required when candidate CIKs are already known and the complete submission is available. Reserve the Stream API for the later live path; it is forward-only and does not replace historical Query API retrieval.[^sec-api-stream]

A disciplined validation budget is:

| Phase | Maximum calls | Purpose |
| --- | ---: | --- |
| Filing census | 2 | One 50-result Query page; one contingency page only if necessary |
| Six deal lifecycles | 30 | At most five complete submissions per deal: announcement, definitive terms, approval/update, amendment and terminal filing |
| Targeted recovery | 6 | At most one individual exhibit download per deal if the complete submission cannot be parsed |
| Reproducibility check | 0 | Re-run entirely from immutable local response cache |
| Unspent reserve | 62 | Preserve for a second design, missed lifecycle documents or broader validation after the first extraction audit |

Treat every authenticated Query or Download request as one trial call. The pricing page says only that the first 100 API calls are free; it does not state that Download API GETs are excluded, even though paid plans separately meter download volume and publish much higher download rate limits.[^sec-api-pricing] Therefore the implementation must count requests locally, refuse to exceed the configured budget, and content-address every successful response before parsing it. Failed or repeated requests must be assumed to consume a call until sec-api.io documents otherwise.

The promotion test is not extraction accuracy on one polished filing. Across all six causal lifecycles, the extractor must either emit a sourced, versioned fact or explicitly reject ambiguity; later amendments must supersede rather than rewrite earlier observations; and no terminal fact may appear before its own `filedAt`. If that works within roughly 38 calls, the remaining credits can expand the sample. If it does not, stop before spending the reserve: the failure is the normalization contract, not insufficient API volume.

### Trial result after nineteen authenticated requests

The bounded source and extraction test used four Query API requests and fifteen downloads, then stopped with at least 81 of the nominal 100 calls unspent. Nothing was requested from SEC.gov directly, and the token was neither written to the repository nor included in configuration. The first six calls established source feasibility; the remaining thirteen supplied standardized complete submissions and the terminal records needed for the six-deal causal audit.

The first query requested six known announcement accessions spanning completed, terminated and pending cash deals. One response returned all six 8-K records with exact `filedAt` timestamps and complete attachment manifests. Every announcement contained both an `EX-2.1` merger agreement and an `EX-99.1` press release. Four targeted downloads then tested two contrasting lifecycles:

| Deal | Agreement evidence | Guidance evidence |
| --- | --- | --- |
| ZIMV | $19.00 cash consideration; 20 January 2026 outside date; termination and failure-to-close mechanics | Expected to close by year-end 2025, subject to stockholder and regulatory approval |
| STAA | $28.00 cash consideration; end date on the agreement's twelve-month anniversary; automatic three-month extension when specified conditions remain | Anticipated to close in approximately six to twelve months, subject to regulatory and shareholder approval |

This validates the source seam that Massive lacked: the same point-in-time announcement supplies the offer, soft closing interval, contractual tail boundary, conditions and extension mechanics. It does **not** yet validate the parser across heterogeneous wording or establish investment alpha.

The broad lifecycle query requested relevant event-form families across the same six CIKs and returned a total of 133 filings, of which the API's first 50-result page included announcement 8-Ks, PREM14A/DEFM14A proxies, DEFA14A updates, tender materials and later 8-K events. A narrower two-page query excluding generic solicitation noise still returned 63 candidate filings. That confirms lifecycle breadth but also rejects a naïve “download every filing” design. Production discovery must narrow by event-specific form, 8-K item and lifecycle date window, then download one complete submission only when it can change the ledger.

### Deterministic six-deal extraction audit

A throwaway pure-state prototype parsed the cached complete submissions locally with no further network access. Every emitted field retains accession, `filedAt`, document type and a bounded evidence excerpt. Offer consideration is accepted only when the press-release value is corroborated by the merger agreement; guidance remains an interval or an explicit coarse label; outside and termination dates remain separate from guidance; extensions are represented independently; and terminal state requires both the relevant 8-K item and corroborating filing language.

| Deal | Offer | Guidance | Initial contractual boundary | Extensions | Causal status |
| --- | ---: | --- | --- | --- | --- |
| ZIMV | $19.00 | By year-end 2025 | 20 January 2026 | None stated | Completed 20 October 2025 |
| STAA | $28.00 | Six to twelve months | 4 August 2026 | Three months | Terminated 6 January 2026 |
| IMXI | $16.00 | H2 2026 | 11 May 2026 | 10 August, then 10 November 2026 | Pending at cutoff |
| PBPB | $17.12 | Q4 2025 | 9 March 2026 | 9 July 2026 | Completed 23 October 2025 |
| DAWN | $21.50 | Q2 2026 | 6 December 2026 | 150 days | Completed 23 April 2026 |
| PAYO | $7.40 | Mid-2027, deliberately not forced to exact dates | 12 June 2027 | Three months | Pending at cutoff |

The batch verdict was six of six fully extracted, six of six lifecycle-consistent and zero guessed/rejected fields. The strongest finding is a correction to the previous Massive-derived census: PBPB and DAWN are completions, not terminations. Their terminal filings contain Item 2.01 and completion language; Item 1.02 can coexist because the pre-closing agreement terminates when the merger is consummated. STAA is the genuine adverse resolution: its terminal filing contains Item 1.02 without Item 2.01 and explicitly reports termination.

> [!warning]
> Six-of-six validates the source contract and state shape, not a production parser or investment alpha. The phrase rules were refined against this sample and now require a disjoint holdout of unfamiliar agreements. Production promotion also requires event identity beyond CIK—DAWN contained two separate deals in the queried period—and an out-of-sample paired return test.

Prototype: `/tmp/aegis-sec-event-extractor-prototype`. Reproduce the verdict with `python /tmp/aegis-sec-event-extractor-prototype/app.py --audit`.

### Sealed holdouts and the q70 adverse-event audit

The six-deal result did not generalize as written. A first sealed twelve-deal holdout produced zero deals satisfying the original “every field must exist” contract and recognized only seven terminal states. The failure separated three problems that the development sample had hidden:

- many issuers do not publish closing guidance, so absence must be represented as an observable state rather than a parse error;
- target filings may place the press release in another `EX-99.*`, summarize the consideration only in the 8-K, or disclose it solely in the `EX-2.1` agreement;
- Item 1.02 is not a termination label when Item 2.01 also exists. Completion takes precedence because financing, voting and pre-closing agreements routinely terminate at consummation.

After those rules were changed using the first holdout as training data, eleven of twelve deals supplied the mandatory offer, contractual boundary and causal terminal state. The exception, BATL, was correctly incomplete: Massive had identified a 2024 amendment as the announcement of a merger signed in 2023, so the filing could not contain the original outside-date definition.

A second sealed eight-deal holdout recognized all eight lifecycles but extracted every mandatory term for only four. Two failures were unsupported but recoverable grammars—`Common Unit` consideration and “on or before” outside-date wording. The other two again exposed bad Massive anchors: the supposed AAN announcement was a later filing without the signed agreement, and GMS was labeled terminated even though its terminal filing contained Item 2.01 and reported completion. After the generic grammar repair, seven of eight were complete; AAN remained deliberately rejected.

The third holdout therefore froze only six CIK/date seeds, used one SEC Query response to choose the actual 8-K containing `EX-2.1` and the event-matched terminal 8-K, and then downloaded the twelve complete submissions. With no parser change after sealing, five of six contained every mandatory fact and all six lifecycles were resolved. FARO's outside-date grammar was the only mandatory miss. Only one of six supplied usable management timing guidance. HOFV and KLG, both provisionally classified as terminations by Massive, were SEC-confirmed completions.

#### Event-local break classification

The terminal classifier must operate on an identified agreement, not on a ticker, CIK or filing-level item list. Key each event by target plus the signed agreement's date/accession and parties; amendments version that event, while a newly signed agreement with a different buyer creates a new event. A terminal filing is admissible only when its text identifies the same agreement and says that its merger was consummated or that the agreement was actually terminated. An Item 1.02 or 2.01 heading is discovery metadata, not proof by itself.[^sec-8k-form][^sec-8k-cdi]

Apply precedence **within that event**:

- completion text for the same agreement wins over Item 1.02 text about credit, financing, voting or other pre-closing agreements ending at consummation;
- Item 1.02 without same-event Item 2.01 is a break only when the body says the identified merger agreement was terminated or the identified transaction will not be consummated;
- when the old agreement is terminated while Item 1.01 and a new `EX-2.1` establish a different acquisition agreement, label the old event `replaced`, open a new event, and do not count the replacement as an adverse break. H&E's United Rentals cash agreement was terminated in the same filing that announced a new Herc cash-and-stock agreement, illustrating why filing-level `terminated` is economically wrong.[^hees-original][^hees-replacement]
- reject unrelated or ambiguous terminal text rather than inferring a state from the item number.

The local corpus already contains unambiguous genuine breaks suitable for ledger tests: MMLP says its merger agreement was terminated and became of no further force, SGRP says the merger missed its closing deadline and the company terminated, and CCRN says the buyer terminated after the end date passed.[^mmlp-break][^sgrp-break][^ccrn-break] BATL separately reports termination of its identified 2023 cash agreement, and STAA reports termination after the merger failed to receive the required shareholder vote.[^batl-break][^staa-break] These are cleaner adverse exemplars than replacement deals or filings containing both Items 1.02 and 2.01.

| Identified event | Cash consideration | Event-local terminal state | Ledger classification |
| --- | ---: | --- | --- |
| SGRP / Highwire | $2.50 per share | Closing deadline missed; company terminated | **Adverse break** |
| BATL / Fury Resources | $7.00 per common share | Identified merger agreement terminated | **Adverse break**; agreement began before the two-year price window |
| MMLP / Martin Resource Management | $4.02 per common unit | Agreement terminated and no longer effective | **Adverse break** |
| CCRN / Aya | $18.61 per share | Buyer terminated after the contractual end date | **Adverse break** |
| STAA / Alcon | $28.00 per share | Shareholders rejected the merger; agreement terminated | **Adverse break** |
| HEES / United Rentals | $92.00 per share | Old agreement terminated while a different buyer signed | **Replaced**, not an adverse break |
| SOHO / KWHP | $2.25 per share | Provisional “terminal” accession concerned an unrelated parking-property sale; the merger later completed | **False match / completion**, not a break[^soho-false-terminal][^soho-completion] |

These five genuine breaks are enough to test ledger mechanics and reproduce loss attribution. They are not enough to estimate a stable physical break probability or promote a selector. Crucially, none of the five appears among the four supposed terminations held by the frozen `q70_monthly_capped` evaluation.

> [!warning] Controlling q70 verdict
> The frozen `q70_monthly_capped` report claimed four held terminated deals: K, SHCO, EB and ONTF. SEC Query metadata and the terminal complete submissions show that **all four completed**. Each contains Item 2.01; SHCO, EB and ONTF also state completion in the filing text, while K's Item 1.02 refers to agreements ending concurrently with closing. The backtest's market-mark P&L is not mechanically rewritten by this correction, but its adverse-event count is zero rather than four. It therefore does not test the payoff feature that matters most.

This invalidates two stronger claims from the prior prototype. First, the positive q70 history cannot establish risk-gate value when none of its held events is an actual break. Second, the hazard and ENP challengers were trained on contaminated lifecycle labels and incomplete timing coverage; their failure does not establish that event-aware selection lacks alpha. It establishes that the Massive-derived event ledger was not fit for that test.

The targeted break audit stopped after a conservative 84 authenticated requests, leaving 16 of the nominal 100-call allowance unused. The source decision is now clear:

1. SEC Query metadata owns announcement discovery, event identity and terminal classification.
2. Complete submissions own consideration, boundaries, amendments, guidance and corroborating lifecycle text.
3. Massive may provide recent market/reference data, but it cannot own the causal event ledger or adverse count.
4. Missing guidance falls back to an earlier frozen hazard prior; it must not make a deal ineligible or be guessed.
5. The existing q70 return is a completion-only pilot. Do not promote, and do not spend the remaining trial calls on another small random sample that is unlikely to contain a genuine break.

## 2026-07-17 — How alpha can actually be established

> [!important]
> The six-deal audit proves data feasibility, not alpha. “Alpha” must be decomposed into three increasingly strong claims: the opportunity set earns a premium, the model selects better deals from that same opportunity set, and the selected stream improves the complete Atalanta book. A good result at one level cannot substitute for the next.

### Freeze the benchmark ladder before the historical run

| Claim | Candidate | Required comparator | What a positive difference means |
| --- | --- | --- | --- |
| **Event-resolution premium** | Every causally eligible fixed-cash deal, diversified with only hard risk and tradability exclusions | Bills/cash reserve | Taking contractual resolution and break risk was compensated after execution costs |
| **Risk-gate value** | The unchanged `q_mkt >= 70%` construction | The all-eligible portfolio with identical sizing and costs | The market-implied probability gate removes more break loss than premium |
| **Selection alpha** | Filing-timing/ENP ranker | The unchanged `q70` portfolio on the exact same opportunity set, gross risk, caps and rebalance dates | Public filing state adds information beyond the spread already embedded in price |
| **Allocator value** | Atalanta plus the winning merger stream | Atalanta alone at the same book volatility | The stream earns its Demeter slot rather than merely looking good standalone |

The all-eligible baseline is load-bearing. Bills alone can show that merger risk earns a premium, but only a same-universe passive deal portfolio can show whether the ranker adds alpha. The ranker must not receive credit for being invested when its comparator is forced to cash, using fewer names, taking more gross risk or trading on different dates.

### Corrected-break alpha pilot

The first same-universe comparison used the 206 priceable lifecycles in the existing two-year tape. Both variants used the same monthly construction, whole-share Aegis simulator, next-close execution, 5 bp slippage, $0.35 fixed fee, 10% name cap, 2% fallback break-loss cap and bill reserve. The only difference was whether deals below `q_mkt = 70%` were excluded.

| Construction | Net total return | Excess over bills | Cash-excess Sharpe | Max drawdown | Utility delta vs bills | Mean deal gross |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| All eligible | 3.73% | -2.09% | -0.28 | -2.68% | -1.12% | 46.1% |
| `q70` | 8.98% | +3.17% | 1.01 | -0.90% | +1.47% | 30.5% |

The `q70` point estimate improved total return by 5.26 percentage points and convergent utility by 2.59 percentage points despite using less deal gross. A paired circular three-month block bootstrap over the 25 common monthly observations gave a median 5.12-point increment, a two-sided 95% interval of **-0.44 to +11.69 points**, and 96.3% positive resamples. The interval crossing zero is controlling: the result is promising, not established.

The corrected event-local ledger explains part of the tail difference but also exposes how little adverse evidence exists. Of the five SEC-confirmed breaks, only CCRN and STAA were ever held by the all-eligible monthly portfolio. `q70` retained CCRN at a maximum 4.54% weight rather than 10%, and excluded STAA rather than holding it at up to 6.67%. SGRP, BATL and MMLP were not held by either monthly construction. Massive's other “termination” counts remain inadmissible because the audited examples include completions mislabeled as breaks.

> [!warning] Alpha verdict
> This pilot supports a **market-price risk-gate lead**, not independent selection alpha. The all-eligible implementation failed to earn an event-resolution premium over bills, while `q70` produced a positive point estimate; however, only two genuine held breaks, reused history and a bootstrap interval crossing zero prevent promotion. Because `q_mkt` is inferred from the spread, it cannot establish that filing state adds information beyond price. Keep `q70` as the frozen benchmark and require a correct point-in-time ledger with at least 100 resolved deals and ten adverse resolutions—or prospective shadow evidence—before claiming alpha.

### Causal experimental contract

1. Build the point-in-time ledger using only facts available by `filedAt`; daily decisions use them no earlier than the next executable session. Freeze event identity, inclusion, sizing, exit, costs and reserve accounting before inspecting strategy returns.
2. Split by calendar time, never randomly by deal. Estimate break-price and completion-hazard inputs only from already resolved deals, roll or expand the training window, and preserve one final untouched evaluation era.
3. Keep the first frozen comparison small: all-eligible, unchanged `q70`, and one timing-aware ENP challenger. Every later rule or parameter tried on the same history increments the trial count.
4. Simulate actual whole shares, commissions, spread/slippage, FX conversion, residual cash and delisting/completion marks. A theoretical fraction or closing-price fill is not evidence for the executable strategy.
5. Attribute every terminal P&L to its event. Report completed, repriced, withdrawn and unresolved deals separately; do not let many overlapping daily observations masquerade as independent evidence.

### Primary decision statistics

The final ranker already exists: `composite_allocator_utility` is the MPPM certainty-equivalent difference between Atalanta plus the convergent stream and Atalanta alone, normalized to the same book volatility. That is the primary allocator statistic because it prices the stream's calm income and its joint crash placement in one quantity. Standalone `convergent_income_utility`, net excess return over bills, downside L-skew, tail budget, maximum drawdown, turnover, gross exposure, cash fraction, deal count, completion count, adverse-resolution count and worst-event loss remain report metrics.

Use paired inference because every construction trades the same dates and opportunity set:

- stationary or circular block bootstrap the **daily return difference** for net excess return and certainty-equivalent differences, preserving serial dependence;
- separately resample whole deal lifecycles as clusters so one long deal does not become dozens of independent observations;
- report point estimate and confidence interval, not only a Sharpe ratio;
- record every tried configuration and use a reality-check/deflated-Sharpe diagnostic when the field grows beyond the three frozen constructions.[^ledoit-wolf][^white-reality][^deflated-sharpe]

Merger arbitrage must not be certified by ordinary CAPM alpha alone. Mitchell and Pulvino show that its beta rises in sharply falling markets and that transaction costs explain much of the gap between headline and executable excess returns.[^mitchell] Report conditional beta and return separately for ordinary months and severe equity-down months, plus the actual behavior of simultaneous deal breaks. Van Tassel's option-based evidence also supports treating market-implied completion probability as priced risk information, not an independent alpha forecast.[^vantassel]

### Frozen promotion and failure language

Use the following project thresholds as decision rules, explicitly labeled engineering choices rather than universal statistical constants:

| Result | Decision |
| --- | --- |
| Fewer than 100 causally resolved out-of-time deals or fewer than 10 adverse resolutions | **Insufficient evidence**; continue the prospective ledger, neither promote nor kill |
| All-eligible portfolio has non-positive net excess return over bills after full costs | **Reject the mechanism for this implementation** |
| `q70` fails to improve the all-eligible portfolio | Drop the gate; do not claim risk-model value |
| ENP challenger fails to improve `q70` at matched exposure and costs | Retain `q70`; reject selection-alpha claim |
| Challenger's paired `composite_allocator_utility` is non-positive versus Atalanta alone | Do not allocate Demeter, even if standalone return is positive |
| Positive point estimates but confidence intervals cross zero | Keep in shadow; call it promising, not proven |
| Positive net premium, positive selection increment, and positive allocator-utility difference with a positive lower one-sided 95% paired-bootstrap bound | Promote to a live-shadow candidate, then require prospective confirmation before capital |

The prospective shadow is the final holdout: immutable filing snapshots, decisions timestamped before the next mark, and broker-realistic fills recorded without changing the rules. Capital promotion requires the shadow ledger to reproduce the historical mechanism; it does not require every short window to be profitable.

## Final recommendation

**Do not abandon merger arbitrage because the first prototype was sparse. Do not productionize it because the market is broad.** The wide search says:

- Actual deal scarcity is not the primary problem.
- sec-api.io resolves the source-coverage seam, but a deterministic parser reached only five of six mandatory-complete deals on its third sealed holdout; market-wide lifecycle reconstruction remains unfinished.
- Massive's lifecycle labels are not admissible evidence: every one of the four “terminated” deals held by the frozen q70 control was an SEC-confirmed completion.
- Two free years remain inadequate for claiming learned completion-probability alpha.
- A learned probability is not required for the first valid strategy: use market-implied probability, diversification and cash.
- Whole-share implementation is feasible at the ten-name floor in the current price cross-section, but costs and risk-weight granularity are meaningful.
- Until the local census demonstrates `≥10` eligible live deals and net paired utility, merger arbitrage belongs as a **sub-engine candidate**, not the whole convergent sleeve.

## Sources

[^baker]: Malcolm Baker and Serkan Savaşoğlu, [“Limited Arbitrage in Mergers and Acquisitions”](https://www.hbs.edu/ris/Publication%20Files/arbitrage_af05900b-acd4-44db-8210-70a9fbc3cf6c.pdf), *Journal of Financial Economics* 64, 2002.
[^vantassel]: Peter Van Tassel, [“Merger Options and Risk Arbitrage”](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr761.pdf), Federal Reserve Bank of New York Staff Report 761, 2016. See Table 1, Section 4.1 and footnote 30.
[^ricks]: Morgan Ricks, [“Deal Breakage in Domestic and Cross-Border Mergers and Acquisitions: New Data and Avenues for Research”](https://scholarship.law.vanderbilt.edu/cgi/viewcontent.cgi?article=1028&context=vjtl), *Vanderbilt Journal of Transnational Law* 53, 2020.
[^dma]: Peter Adelson et al., [“Introducing a New Corpus of Definitive M&A Agreements, 2000–2020”](https://doi.org/10.1111/jels.12410), *Journal of Empirical Legal Studies* 22, 2025; [public corpus](https://github.com/padelson/dma_corpus).
[^arb]: AltShares Trust, [2024 prospectus supplement](https://www.sec.gov/Archives/edgar/data/1779306/000110465924103617/a24-19195_3497k.htm) and [2025 prospectus supplement](https://www.sec.gov/Archives/edgar/data/1779306/000110465925093813/tm2522610d4_497k.htm), SEC EDGAR.
[^mrgrfact]: ProShares, [MRGR fact sheet](https://www.proshares.com/globalassets/proshares/fact-sheet/prosharesfactsheetmrgr.pdf), data as of 31 March 2026.
[^mrgr]: ProShares, [MRGR holdings](https://www.proshares.com/our-etfs/strategic/mrgr), data as of 15 July 2026. Share-price figures are inferred from reported market value divided by shares.
[^mna]: New York Life Investments, [NYLI Merger Arbitrage ETF fact sheet](https://www.newyorklifeinvestments.com/assets/documents/index-nyli/mna-nyli-merger-arbitrage-etf-fs.pdf), data as of 31 December 2025.
[^mnaprospectus]: NYLI Merger Arbitrage ETF, [summary prospectus](https://www.sec.gov/Archives/edgar/data/1415995/000199937124010813/mna-497k_082824.htm), SEC EDGAR, 2024.
[^massivebars]: Massive, [“Custom Bars (OHLC)”](https://massive.com/docs/rest/stocks/aggregates/custom-bars), accessed 16 July 2026.
[^massive8k]: Massive, [“8-K Disclosures”](https://massive.com/docs/rest/stocks/filings/8-k-disclosures), accessed 16 July 2026.
[^mitchell]: Mark Mitchell and Todd Pulvino, [“Characteristics of Risk and Return in Risk Arbitrage”](https://bpb-us-w2.wpmucdn.com/voices.uchicago.edu/dist/d/2771/files/2020/09/JF_riskarb-1.pdf), *Journal of Finance* 56, 2001.
[^jetley]: Gaurav Jetley and Xinyu Ji, [“The Shrinking Merger Arbitrage Spread: Reasons and Implications”](https://doi.org/10.2469/faj.v66.n2.3), *Financial Analysts Journal* 66, 2010.
[^jajal]: Hinal Jajal et al., [“Global Merger-Arbitrage Forecasting with Language Models”](https://arxiv.org/abs/2607.09921), 2026.
[^giglio-shue]: Stefano Giglio and Kelly Shue, [“No News Is News: Do Markets Underreact to Nothing?”](https://stefanogiglio.org/papers/giglio-shue-rfs-2014.pdf), *Review of Financial Studies* 27, 2014.
[^lee]: Sangwon Lee, [“Failure Risk, Risk Arbitrage, and Outcomes of Mergers and Acquisitions”](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2941200), working paper, revised 2020.
[^mac]: Antonio J. Macias, [“Material Adverse Change Clauses and Acquisition Dynamics”](https://doi.org/10.1017/S0022109013000100), *Journal of Financial and Quantitative Analysis* 48, 2013.
[^bates-lemmon]: Thomas W. Bates and Michael L. Lemmon, [“Breaking Up Is Hard to Do? An Analysis of Termination Fee Provisions and Merger Outcomes”](https://doi.org/10.1016/S0304-405X(03)00120-X), *Journal of Financial Economics* 69, 2003.
[^boone-mulherin]: Audra L. Boone and J. Harold Mulherin, [“Do Termination Provisions Truncate the Takeover Bidding Process?”](https://doi.org/10.1093/rfs/hhl036), *Review of Financial Studies* 20, 2007.
[^bester-options]: C. Alan Bester, Victor H. Martinez and Ioanid Roşu, [“Option Prices and the Probability of Success of Cash Mergers”](https://doi.org/10.1093/jjfinec/nbaa048), *Journal of Financial Econometrics* 21, 2023.
[^media]: Matthias M. M. Buehlmaier and Josef Zechner, [“Financial Media, Price Discovery, and Merger Arbitrage”](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2858999), *Review of Finance* 25, 2021.
[^sec-8k-form]: U.S. Securities and Exchange Commission, [Form 8-K](https://www.sec.gov/info/edgar/forms/form8-k.pdf), Items 1.01, 1.02, 2.01 and 5.07.
[^sec-8k-cdi]: U.S. Securities and Exchange Commission, [Exchange Act Form 8-K Compliance and Disclosure Interpretations](https://www.sec.gov/rules-regulations/staff-guidance/compliance-disclosure-interpretations/exchange-act-form-8-k), guidance on Item 1.01 business-combination disclosure and Item 1.02 termination.
[^informatica-outside]: Informatica Inc., [Form 8-K filed 27 May 2025](https://www.sec.gov/Archives/edgar/data/1868778/000119312525128808/d930092d8k.htm), description of the outside date and regulatory extensions.
[^tender-rules]: U.S. Securities and Exchange Commission, [Regulation M-A Item 1004, Terms of the Transaction](https://www.law.cornell.edu/cfr/text/17/229.1004), including tender-offer expiration and extension disclosure.
[^schedule-to-example]: U.S. Securities and Exchange Commission, [Schedule TO filing with Offer to Purchase and merger agreement exhibits](https://www.sec.gov/Archives/edgar/data/1121404/000119312526009651/d37469dsctot.htm), and [Schedule TO amendment reporting expiry without extension](https://www.sec.gov/Archives/edgar/data/1600620/000114036126020397/ef20072576_scto-ta.htm), 2026.
[^s4-guidance-example]: U.S. Securities and Exchange Commission, [Form S-4 example](https://www.sec.gov/Archives/edgar/data/885725/000110465926021633/tm266847-1_s4.htm), 2026, distinguishing broad expected-closing guidance from an unpredictable actual closing date.
[^aima-timing]: Alternative Investment Management Association Canada, [“Merger Risk Arbitrage”](https://www.aima.org/asset/676DA5D6-8CE4-42D7-A2C6171EAC6382DC/), practitioner example showing the sensitivity of annualized spread to assumed time to completion.
[^wsh-mergers]: Wall Street Horizon, [“Merger Events”](https://www.wallstreethorizon.com/merger-events) and [M&A event-class field specification](https://www.wallstreethorizon.com/upload/WSHEclassesandfieldsforIBAPI2022-12-23.pdf), accessed 17 July 2026.
[^sec-api-pricing]: sec-api.io, [pricing and coverage](https://sec-api.io/pricing), accessed 17 July 2026.
[^benzinga-ma]: Benzinga, [Mergers and Acquisitions API](https://docs.benzinga.com/api-reference/calendar-api/get-ma) and [webhook engine](https://docs.benzinga.com/webhook-reference/webhook-engine), accessed 17 July 2026.
[^ledoit-wolf]: Olivier Ledoit and Michael Wolf, [“Robust Performance Hypothesis Testing with the Sharpe Ratio”](http://www.ledoit.net/Robust_Sharpe_2008.pdf), *Journal of Empirical Finance* 15, 2008.
[^white-reality]: Halbert White, [“A Reality Check for Data Snooping”](https://www.ssc.wisc.edu/~bhansen/718/White2000.pdf), *Econometrica* 68, 2000.
[^deflated-sharpe]: David H. Bailey and Marcos López de Prado, [“The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality”](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf), *Journal of Portfolio Management* 40, 2014.
[^sec-api-query]: sec-api.io, [Filing Query API](https://sec-api.io/docs/query-api), especially CIK baskets, `size: 50` pagination, `filedAt` and attachment metadata, accessed 17 July 2026.
[^sec-api-stream]: sec-api.io, [Real-Time Filing Stream API](https://sec-api.io/docs/stream-api), especially M&A form families, acceptance timestamps, complete-submission links and the forward-only stream boundary, accessed 17 July 2026.
[^sec-api-download]: sec-api.io, [Filing Download API](https://sec-api.io/docs/sec-filings-render-api), especially original complete-submission and individual-exhibit downloads, accessed 17 July 2026.
[^hees-original]: H&E Equipment Services, [Form 8-K announcing the United Rentals agreement](https://www.sec.gov/Archives/edgar/data/1339605/000119312525005785/d866014d8k.htm), accession 0001193125-25-005785, 14 January 2025.
[^hees-replacement]: H&E Equipment Services, [Form 8-K terminating the United Rentals agreement and announcing the Herc agreement](https://www.sec.gov/Archives/edgar/data/1339605/000119312525029610/d936853d8k.htm), accession 0001193125-25-029610, 19 February 2025.
[^mmlp-break]: Martin Midstream Partners, [Form 8-K reporting termination of its merger agreement](https://www.sec.gov/Archives/edgar/data/1176334/000117633424000178/mmlp-20241226.htm), accession 0001176334-24-000178, 26 December 2024.
[^sgrp-break]: SPAR Group, [Form 8-K reporting termination after the closing deadline](https://www.sec.gov/Archives/edgar/data/1004989/000143774925018341/sgrp20250522c_8k.htm), accession 0001437749-25-018341, 23 May 2025.
[^ccrn-break]: Cross Country Healthcare, [Form 8-K reporting termination after the end date](https://www.sec.gov/Archives/edgar/data/1141103/000095010325015716/dp238334_8k.htm), accession 0000950103-25-015716, 4 December 2025.
[^batl-break]: Battalion Oil, [Form 8-K reporting termination of the Fury Resources merger agreement](https://www.sec.gov/Archives/edgar/data/1282648/000110465924130519/tm2431670d1_8k.htm), accession 0001104659-24-130519, 20 December 2024.
[^staa-break]: STAAR Surgical, [Form 8-K reporting the failed shareholder vote and merger termination](https://www.sec.gov/Archives/edgar/data/718937/000119312526004699/d823468d8k.htm), accession 0001193125-26-004699, 6 January 2026.
[^soho-false-terminal]: Sotherly Hotels, [Form 8-K terminating an unrelated parking-property sale agreement](https://www.sec.gov/Archives/edgar/data/1301236/000119312525282339/soho-20251112.htm), accession 0001193125-25-282339, 14 November 2025.
[^soho-completion]: Sotherly Hotels, [Form 8-K reporting completion of the KWHP merger](https://www.sec.gov/Archives/edgar/data/1301236/000119312526056144/d107217d8k.htm), accession 0001193125-26-056144, 18 February 2026.
