---
title: What Can Fill the Concave Floor at EUR 5,000 Now
date: 2026-07-14
topic: strategy-roster
status: decision
related:
  - "[[the-tiered-strategy-roster]]"
  - "[[choosing-the-concave-income-pole]]"
  - "[[insurance-linked-securities-as-the-orthogonal-income-pole]]"
  - "[[the-ucits-constrained-carry-sleeve]]"
  - "[[fx-carry-is-not-yet-a-small-account-demeter-replacement]]"
tags:
  - note
  - demeter
  - concavity
  - carry
  - insurance-linked-securities
  - implementation
---

# What Can Fill the Concave Floor at EUR 5,000 Now

> [!abstract] Decision
> **The €5,000 answer is a static, band-rebalanced insurance-and-credit sleeve, not an active signal.** Use the EUR-hedged short-credit pair `CBUS5E + STEA` for 80% of Demeter and the KRC Cat Bond UCITS ETF (`CATB.LSEETF`, ISIN `IE000UWJUW87`) for 20%. The USD London line is the only listing currently proven through Aegis's complete quote, distribution and dynamic-extension paths; the EUR/USD conversion leg is therefore explicit. Cat bonds are the best economic match because they collect catastrophe-insurance premium with sudden event loss, while their payer is largely separate from the financial shocks that move Atalanta. The 20% is an operational cap for a new, small wrapper, not an optimized portfolio weight. The parent allocator, not these component weights, decides Demeter's share of the commingled book.
>
> Do **not** use covered-call ETFs, AT1, short-horizon reversal, or a generic alternative-risk-premia fund as the floor's core. UBS's defensive put-write ETF is the only credible listed literal short-gamma alternative, but its crash factor is Eurozone equity and the existing Demeter tests did not find a stable allocation plateau. Merger arbitrage is economically valid but the available UCITS fund wrappers are too expensive, too new, or operationally uncertain at €5,000.

## The role, stated without the word “carry”

The floor needs a **convergent income payer**: a stream that accrues while its insured event does not happen and gives back several periods of income when it does. That payoff should be negatively skewed and should not merely duplicate Atalanta's own return driver. It need not be called carry or use a timing signal.

There are only four credible payers under the account constraint:

1. corporate borrowers pay a credit spread;
2. insurers pay a catastrophe-risk premium;
3. option buyers pay an implied-volatility/skew premium;
4. acquirers and target shareholders leave a deal-completion spread.

Mechanical rebalancing has no external payer. Short-horizon reversal is paid liquidity provision, but it needs many cheap trades and a broad cross-section. “Alternative risk premia” is a portfolio label, not a payoff contract. Those mechanisms may improve another sleeve; they do not independently fill this role.

## Decision matrix

| Candidate | Structural payer and loss event | Negative-skew identity | Complement to Atalanta | €5k implementation | History / cost | Decision |
|---|---|---:|---:|---:|---|---|
| `CBUS5E + STEA` static short credit | Borrowers pay spread; default and spread-widening loss | Medium: real credit concavity, diluted by IG | Medium: financially cyclical, but the EUR-hedged wrappers remove the unrelated USD/EUR translation bet | Strong: UCITS ETFs, EUR exposure, whole shares and low turnover | Short-IG share class launched 2015; short-HY share class launched 2017 and charges 0.60%[^ubs-uef8][^pimco-short-hy] | **NOW core** |
| KRC Cat Bond UCITS ETF (`CATB.LSEETF`) | Insurers pay catastrophe premium; trigger can impair principal | **Strong and clean**: quiet coupon, discontinuous meteorological loss | **Highest**: physical peril rather than recession, rates or equity | Strong lot size and daily ETF dealing; USD London line works end to end, with explicit EUR conversion | Launched 2 Dec 2025; $14.0m AUM; 1.28% TER; only 48 holdings and insufficient fund history[^catb] | **NOW starter after broker check; NEXT primary payer** |
| UBS Euro Equity Defensive Put Write (`E50PW` / `UIQ4`, `IE00BLDGHT92`) | Put buyers pay option premium; Euro Stoxx sell-off creates loss | **Strongest literal short gamma** | Low-to-medium: same fast equity crash can hit slow trend before it turns | Strong: UCITS ETF, NAV €153.45, €140.24m AUM, 0.21% fee[^ubs] | Fund since Jul 2020; index portfolio starts Jan 2019 and sells four-week 97%-strike puts, with part of the displayed index history potentially backtested[^putmethod] | **Real instrument, not the core; no allocation now** |
| Covered-call UCITS (`QYLD`, `XYLU`, `SYLD`) | Call buyers pay premium; equity drawdown remains almost fully owned | Negative convexity, but dominated by long-equity delta | Poor: imports a large equity factor and caps rebound | Easy ETF lots | 0.45% fee; monthly at-the-money calls in the Global X implementations[^xylu] | **Reject for this role** |
| Merger-arbitrage UCITS | Deal spread; broken deals gap down | Strong: academically resembles an uncovered put in severe markets | Medium: idiosyncratic deals, but market beta appears in severe declines | Weak: no credible live pure ETF found; mutual-fund dealing, minimum and IBKR eligibility are account-specific | Candriam retail class can charge 1.5% management, 20% performance, and up to 3.5% subscription; Berenberg began only May 2025[^candriam][^berenberg] | **NEXT only if a cheap listed wrapper appears** |
| AT1 / CoCo ETF | Banks pay subordination and bail-in premium; coupon cancellation, conversion or write-down | Strong | Poor: concentrated systemic-financial crash risk | Easy ETF lots | Live UCITS ETFs, but this is a more levered credit payer, not an independent one | **Reject as a separate payer; at most part of credit** |
| Generic alternative-risk-premia / hedge-fund index | Mixed: value, carry, momentum, defensive and arbitrage | Unknown ex ante; may contain both gamma signs | Unknown until decomposed | Usually weak: AQR's cited retail-oriented UCITS class requires €10,000; the listed UBS HFRX ETF was liquidated in 2020[^aqr][^hfrx] | Manager, derivative, model and fee risk; family label is not a return contract | **Reject** |
| Volatility harvesting / fixed rebalancing | No external payer; sells relative winners to buy losers | Not reliably negative-skew; depends on constituent dynamics | Portfolio-level benefit, not an independent stream | Easy inside existing allocator | Research explicitly notes it is not arbitrage and requires the assumed market dynamics to persist[^volharvest] | **Use as plumbing, not a sleeve** |
| Short-horizon mean reversion / pairs | Demander of immediacy pays a liquidity premium; persistent move or crowding breaks convergence | Potentially negative, but implementation-dependent | Potentially good | Poor: breadth, shorting, borrow and turnover are all hostile to €5k | Reversal compensation rises with VIX, but it is cost- and state-dependent liquidity provision[^nagel] | **Use to improve execution, not as Demeter** |

## Why cat bonds are the destination

Cat bonds are genuine insurance carry. The investor earns short-term collateral return plus premium for assuming a specified natural-catastrophe trigger. If the event does not breach the attachment layer, income accrues and principal returns at maturity; if it does, principal can be partly or fully lost. The mechanism therefore has the exact quiet-income/discontinuous-loss shape the roster asks for, without needing leverage, account-level derivatives, shorting, or daily decisions.

The diversification claim is strong but not magical. Academic spanning tests over 2002–2017 find that cat bonds add portfolios unavailable from traditional assets and improve time-varying Sharpe and diversification measures, especially during financial crises and high-volatility episodes.[^catdiv] Earlier crisis evidence shows that cat bonds were not zero-beta during Lehman's collapse, because collateral and liquidity channels briefly linked them to markets, but the effect was much smaller than for conventional risky assets.[^catcrisis] The correct label is **orthogonal insurance seller**, not safe haven.

The currently investable wrapper is no longer hypothetical. HANetf reports for 9 July 2026:

- `IE000UWJUW87`, active Irish UCITS ETF, accumulating;
- $10.37 NAV and $14.0m fund assets;
- 48 holdings, with top named positions around 2–4%;
- Xetra `C47B` and Borsa Italiana `CATB` EUR trading lines;
- 1.28% TER and daily ETF dealing;
- official examples of the underlying Swiss Re Cat Bond Index losing 9.5% in the 2017 hurricane season and 6.2% around Hurricane Ian, while losing only 0.7% in March 2020.[^catb]

That is a real security with an affordable whole-share price, but it is not yet a mature wrapper. Fund history is insufficient to display performance, its AUM is small, and ESMA's 2025 technical advice says large-scale UCITS investment in alternatives such as cat bonds may be better suited to AIFMD; the European Commission is still reviewing eligible-asset rules in 2026.[^esma][^ec] Hence a starter allocation is justified; handing the entire Demeter sleeve to this ETF is not.

## Why put-write is real but second choice

The UBS product is not “equity income” marketing. Its index holds a German cash-rate exposure and systematically sells listed Euro Stoxx 50 puts on Eurex. The published methodology targets four-week maturity and a 97% strike.[^ubs][^putmethod] This is cash-secured put writing: a direct sale of downside volatility with limited operational burden inside the account.

The premium is structural. Historical index-option research documents materially negative buyer returns and a variance-risk premium in put writing, while the put-write return distribution is more negatively skewed and more fat-tailed than equity.[^bondarenko] That makes the instrument a legitimate family member.

It loses the implementation contest for this book for three reasons:

1. the loss event is the same fast equity crash that slow trend cannot hedge immediately;
2. the ETF launched after the March 2020 crash, while its index history begins only in 2019 and may include backtest;
3. the existing clean Demeter extension produced an isolated 30% winner rather than a stable neighboring plateau and then failed the realized family-shape gate.

Therefore `E50PW` is an investable **secondary financial-crash payer**, not the replacement for credit and not the first source of payer diversification.

## Why merger arbitrage waits

Merger arbitrage has the right economics. A target trades below the announced consideration because closing is uncertain; the arbitrageur earns that spread when conditions are satisfied and suffers a gap when the deal breaks. Mitchell and Pulvino's 4,750-deal sample finds about 4% annual excess return after transaction costs and the same nonlinear severe-market exposure as selling an uncovered index put.[^merger]

The wrapper, not the role, fails the €5,000 test. The live products found are traditional UCITS mutual funds rather than robust exchange-traded pure-merger-arbitrage vehicles. Candriam's cited share class combines high management, subscription and performance fees.[^candriam] Berenberg's lower-cost retail class is only about one year old and its broker minimum/dealing availability is unknown.[^berenberg] A strategy that earns a mid-single-digit deal spread cannot donate several percentage points to entry and incentive fees. Revisit only when IBKR offers a daily-dealt class with no front load, a small minimum and all-in ongoing cost below roughly 1%.

## NOW / NEXT / LONG TERM

### NOW — one mature payer plus one capped new payer

Keep Demeter's total book weight unchanged. At the next normal rebalance:

1. retain 80% of Demeter in `CBUS5E + STEA`, split equally between short IG and short HY;
2. allocate 20% of Demeter to `CATB.LSEETF` **only if** the live-account checks below pass;
3. rebalance with the existing wide band, not monthly calendar trades;
4. use limit orders during the overlapping liquid European session and do not chase a premium to NAV.

If Demeter is 28% of a €5,000 book, the starter is about €280. This is intentionally small: it is large enough to make the payer real and small enough that closure, regulatory change or one severe event cannot dominate the portfolio. IBKR's published Western-Europe tiered minimum is €1.25 per order (fixed SmartRouting is €3), so low cadence matters at this account size.[^ibkrfees] Whole shares are preferable because fractional shares are not available through the IBKR API; the official CATB NAV makes whole-share sizing practical.[^ibkrfrac]

If any live-account check fails, **do nothing exotic**: keep 100% of Demeter in `CBUS5E + STEA`. That is still a real, funded convergent sleeve, not a research placeholder.

### NEXT — make insurance the primary payer after wrapper gates

Move toward a 50/50 insurance-credit Demeter only after all of these are true:

- at least 12 months of live ETF NAV, including a full US wind season;
- persistent two-sided quotes and acceptable premium/discount in the actual IBKR account;
- no adverse European Commission change to direct cat-bond eligibility;
- fund assets and creations are no longer consistent with near-term closure risk;
- realized monthly correlation and marginal certainty equivalent beside locked Atalanta are not worse than the credit control.

These are implementation gates, not a search for alpha. The target is payer diversification: meteorological loss plus corporate-default loss.

### LONG TERM — a small payer roster, not one heroic trade

The durable convergent sleeve should contain two independent insurers and, only when cheap access exists, a third event payer:

- 50–70% catastrophe insurance;
- 20–40% short-duration / rate-hedged credit;
- 0–20% merger arbitrage or defensive put-write, but not both by default.

Use fixed strategic weights, wide drift bands and annual mechanism review. Do not time hurricane season, volatility or M&A headlines. As NAV grows, a larger established cat-bond UCITS mutual fund can replace or complement the small ETF if its minimum and dealing terms become economical; direct forwards, options and market-making strategies become relevant only at much larger operational scale.

## IBKR validation required before the starter trade

The running paper gateway qualified the Xetra contract on 14 July 2026, but its exchange-local `C47B` symbol differs from IB's underlying `CATB` symbol and the raw distribution path cannot extend it without an adapter change. The Borsa line requires IB's dotted `BVME.ETF` venue, which the current Aegis `InstrumentId` path cannot express cleanly. The selected `CATB.LSEETF` line uses the same symbol throughout, and the normal pipeline completed through 11 July 2026 with dynamic BID/ASK and distribution coverage. Contract qualification and historical coverage do **not** prove that the live legal entity has opening permission or that the spread is economical.

Before the first starter trade, validate and record:

- opening eligibility for the selected London `CATB` line under this IBKR Europe legal entity, country of residence and permission set, rather than assuming eligibility transfers across listings;
- successful live-account What-If with no PRIIPs/KID, complex-product or closing-only warning;
- SMART versus direct-route commission, exchange fees and the actual minimum charge;
- whole-share order support through the Aegis API; do not assume IBKR's UI fractional eligibility carries into the API;
- live bid/ask spread, quoted depth, last trade, market-maker presence and premium/discount to the published USD NAV;
- EUR trade-currency mechanics versus the fund's unhedged USD base exposure;
- order-type support and behavior outside the main European session;
- tax treatment of an accumulating Irish UCITS ETF for the account owner;
- liquidation, settlement and transfer behavior if the ETF closes or becomes ineligible under revised UCITS rules.

> [!warning] Kill conditions
> Do not open the CATB starter if the security is closing-only, the live spread exceeds 1% without a clear stale-quote explanation, a one-way market prevents a limit fill near NAV, or the expected round-trip commission exceeds 1% of the starter. Do not promote it beyond the starter while the fund lacks a complete wind-season history or EU eligibility remains materially unresolved.

## Sources

[^ubs-uef8]: UBS, [UBS BBG US Liquid Corporate 1-5 UCITS ETF hEUR acc factsheet](https://swissfunddata.ch/sfdpub/docs/fsm-2880_67_04-20250930-en.pdf) — `LU1048315243`; tracks USD investment-grade corporate bonds with one-to-five-year maturities, hedges to EUR and launched on 31 March 2015. IBKR's executable identity is `CBUS5E.XBRU`, not the issuer-page ticker `UEF8`.

[^pimco-short-hy]: PIMCO, [PIMCO US Short-Term High Yield Corporate Bond UCITS ETF EUR Hedged factsheet](https://docs.fundconnect.com/GetDocument.aspx?Isin=IE00BF8HV600&clientid=18svzhes-n8uj-xtdb-oidd-a58dzenasvsr&lang=en-GB&save=false&type=Factsheet) — accumulating `STEA` (`IE00BD26N851`) tracks the EUR-hedged ICE BofA 0-5 Year US High Yield Constrained benchmark; launched 11 December 2017; 0.60% management fee.

[^catb]: HANetf, [KRC Cat Bond UCITS ETF](https://hanetf.com/fund/catb-cat-bond-etf/) and [May 2026 KIID](https://hanetf.com/wp-content/assets/upload/kiid-CATB-IE000UWJUW87-en-GB.pdf) — IE000UWJUW87; official fund mechanics, current NAV/AUM/holdings, listings, fees and issuer-provided historical cat-bond index stress figures. Issuer data; performance illustrations have product-provider conflict and are used only to describe the payoff and wrapper.

[^catdiv]: Demers-Bélanger, K. & Lai, V. S., [“Diversification Benefits of Cat Bonds: An In-Depth Examination”](https://onlinelibrary.wiley.com/doi/10.1111/fmii.12134), *Financial Markets, Institutions & Instruments* 29(5), 2020 — mean-variance spanning, DCC and out-of-sample analysis over 2002–2017. Peer-reviewed primary research.

[^catcrisis]: Carayannopoulos, P. & Perez, M. F., [“Diversification through Catastrophe Bonds: Lessons from the Subprime Financial Crisis”](https://ideas.repec.org/a/pal/gpprii/v40y2015i1p1-28.html), *Geneva Papers on Risk and Insurance* 40(1), 2015 — cat bonds briefly gained market beta during Lehman but retained materially better diversification than conventional risky assets. Peer-reviewed primary research.

[^esma]: ESMA, [Technical Advice on the review of the UCITS Eligible Assets Directive](https://www.esma.europa.eu/sites/default/files/2025-06/ESMA34-2087785638-1548_Final_report_on_the_Technical_Advice_on_the_review_of_the_UCITS_EAD.pdf), 26 June 2025 — cat bonds are among the assets with divergent eligibility interpretations; ESMA considers large-scale alternative exposure conceptually better suited to AIFMD and recommends a look-through framework. Official regulator document.

[^ec]: European Commission, [“UCITS at 40 — what's next for eligible assets?”](https://finance.ec.europa.eu/news/ucits-40-whats-next-eligible-assets-2025-10-27_en), 27 October 2025 — the Commission planned public consultation and market analysis during 2026 after ESMA's advice. Official policy status.

[^ubs]: UBS, [Euro Equity Defensive Put Write SF UCITS ETF factsheet](https://api.fundinfo.com/document/5d98867c6f7ab7688d6fb86b3b77ca3c_129424/MR_CH_en_IE00BLDGHT92_YES_2026-01-31.pdf?apiKey=53baf9a3-cd29-4548-8a18-1bb76473cc9d), 31 January 2026 — IE00BLDGHT92; synthetic fully funded swap; Euro Stoxx 50 put-write plus German money-market return; 0.21% flat fee; €153.45 NAV and €140.24m assets. Official issuer factsheet.

[^putmethod]: Solactive, [Euro Equity Defensive Put Write Index guideline](https://www.solactive.com/downloads/Guideline_SX5E_Put_v12.pdf) and [index page](https://www.solactive.com/indices/?index=DE000SL0AS77&symbol=SAFTFA.IND) — four-week target maturity, 97% target strike, January 2019 portfolio commencement; index provider warns that chart history may partly be backtested. Official index methodology.

[^bondarenko]: Bondarenko, O., [“Historical Performance of Put-Writing Strategies”](https://cdn.cboe.com/resources/education/research_publications/PutWriteCBOE19_v14_by_Prof_Oleg_Bondarenko_as_of_June_14.pdf), 2019, and [“Why Are Put Options So Expensive?”](https://doi.org/10.1142/S2010139214500153), *Quarterly Journal of Finance* 4(3), 2014 — documents the implied-realized volatility gap, put-writing income and its more negative skew/fatter tails. Primary research; the historical-index study was sponsored/published by Cboe.

[^xylu]: Global X, [S&P 500 Covered Call UCITS ETF PRIIPs KID](https://globalxetfs.eu/content/files/PRIIPS_KID_IE0002L5QB31_IE_Distributing.pdf) — one-month at-the-money covered calls, 0.45% annual management fee, plus estimated portfolio transaction costs. Official issuer document.

[^merger]: Mitchell, M. & Pulvino, T., [“Characteristics of Risk and Return in Risk Arbitrage”](https://bpb-us-w2.wpmucdn.com/voices.uchicago.edu/dist/d/2771/files/2020/09/JF_riskarb-1.pdf), *Journal of Finance* 56(6), 2001 — 4,750 mergers, 1963–1998; roughly 4% annual excess return after transaction costs; severe-market payoff resembles selling uncovered index puts. Peer-reviewed primary research.

[^candriam]: Candriam, [Candriam Equities L Merger Arbitrage](https://www.candriam.com/en-lu/professional/funds-lister/fund-detail/LU2223682944/) — official fund objective and cited share-class maximum fees: 1.50% management, 3.50% subscription and 20% performance fee.

[^berenberg]: Universal Investment, [Berenberg Merger Arbitrage factsheet](https://fondsfinder.universal-investment.com/api/v1/DE/LU2986719057/document/Factsheet/en) — UCITS fund launched 13 May 2025, approximately €26m fund volume and 1.45% estimated ongoing charges for the cited share class. Official administrator document.

[^aqr]: AQR, [AQR Style Premia UCITS Fund RAE KID](https://www.fundsquare.net/download/dl?siteId=FSQ&v=gzO4oH6OKkkxypASE8jJQ7VoLXXKq04Ql7zE2+whwAFgHyk7ddwfzQdOSq6aLH7kkHR2bl%2FB0DrqmnJWxMIUFy2GSqXjusmrWui1sGKRR8OvHoucYxs4wqRyzHtqW%2FRIL2NsZIlQ1W0Yo9z0VRsuvG8CCB2y+S0rzKAbAEfRppI%3D) — €10,000 indicated investment and 10% performance fee over €STR for the cited class; styles mix value, momentum, carry and defensive exposures. Official KID via Fundsquare.

[^hfrx]: UBS, [Closure of HFRX Global Hedge Fund Index SF UCITS ETF](https://www.ubs.com/global/en/media/display-page-ndp/en-20201030-closure-hfrx-global-hedge-fund-index-qa.html), 30 October 2020 — the fund was liquidated effective 27 October 2020. Official issuer notice; stale fund databases should not be treated as evidence of a live vehicle.

[^volharvest]: Witte, J. H., [“Volatility Harvesting: Extracting Return from Randomness”](https://arxiv.org/pdf/1508.05241), 2015 — rebalancing growth requires specific market dynamics and is not arbitrage. Primary working paper.

[^nagel]: Nagel, S., [“Evaporating Liquidity”](https://www.nber.org/system/files/working_papers/w17653/w17653.pdf), *Review of Financial Studies* 25(7), 2012 — short-term reversal returns proxy for compensation to liquidity providers and vary sharply with market stress. Peer-reviewed primary research.

[^ibkrfees]: Interactive Brokers Ireland, [European stocks and ETF commissions](https://www.interactivebrokers.ie/en/pricing/commissions-stocks-europe.php) — tiered 0.05% with €1.25 minimum for EUR orders; fixed SmartRouting €3 for typical Western-European trades. Official broker pricing; the account's actual plan still governs.

[^ibkrfrac]: Interactive Brokers Ireland, [Fractional Trading](https://www.interactivebrokers.ie/en/trading/fractional-trading.php?menu=B) — eligible European securities can be traded fractionally from $1, but fractional trading is not available through the IBKR API and eligibility is discretionary. Official broker documentation.
