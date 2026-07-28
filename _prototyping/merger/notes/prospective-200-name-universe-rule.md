---
title: Prospective 200-Name Cash-Merger Discovery Universe
date: 2026-07-18
topic: demeter-cash-merger
status: research-note
related:
  - "[[current-fixed-cash-universe-2026-07-17]]"
  - "[[completion-selection-alpha-evidence]]"
  - "[[finding-a-buildable-convergent-engine]]"
tags:
  - note
  - demeter
  - merger-arbitrage
  - universe
  - survivorship-bias
---

# Prospective 200-Name Cash-Merger Discovery Universe

> [!abstract] Decision
> Build a **prospective, dated 200-name validation cohort**, not a hand-picked list of supposed takeover targets. Retain the currently verified pending fixed-cash deals and fill the remaining places from a current S&P SmallCap 600 cohort. Use it to validate selection-scoped loading and begin forward evidence collection. Do not treat 200 names as the eventual production universe or use today's membership in a historical alpha test.

## Why 200 names are useful—but not enough

The strategy earns after a cash deal is announced; predicting which ordinary company will receive an offer is a separate alpha problem. A real merger-arbitrage methodology therefore starts from **causally announced, pending deals** and then applies deal, size, and liquidity rules. Solactive's merger-arbitrage methodology follows that order and uses 20-day average daily dollar trading value in portfolio construction.[^solactive] Selecting 200 companies because they look like future targets would mix an unproven takeover-prediction model into the completion-selection experiment.

The expected event count also rules out interpreting 200 pre-event names as sufficient breadth. Vijh and Yang study U.S. public firms from 1981–2004 and report annual successful cash-target frequencies of `0.70%`, `0.67%`, `0.53%`, and `0.18%` from the smallest to largest NYSE size quartile.[^vijh] At `0.70%`, a 200-name small-company cohort implies only about `1.4` successful public-acquirer cash targets per year. That estimate does not include every private acquirer, but the prototype then narrows the set further to signed, fixed-cash, supported-filing, positive-net-payoff deals. The defensible conclusion is directional: **200 names can exercise the pipeline; they cannot sustain ten concurrent merger positions.**

Mitchell and Pulvino's transaction-cost-aware merger-arbitrage portfolio reinforces the need for breadth and executable filters: commissions, price impact, illiquidity-driven position limits, and uninvested cash materially reduced the naive return.[^mitchell-pulvino] The universe must preserve opportunities without pretending that every discovered deal is investable.

## Recommended prospective construction

Create a dated cohort with this sequence:

1. **Retain causally admitted pending deals.** Start with the 20 exact InstrumentIds already verified in [[current-fixed-cash-universe-2026-07-17]]. Audit current merger-fund holdings as discovery leads, but admit another name only after primary filings prove a pending, fixed-cash, domestically reported endpoint.[^mrgr] The 2026-07-18 pass added `SLAB.XNAS`, `TMHC.XNYS`, and `ACA.XNYS`; their inclusion is legitimate only for a forward run beginning after this note's evidence cutoff.[^slab][^tmhc][^aca]
2. **Seed the remaining cohort from the current S&P SmallCap 600 opportunity set.** Use State Street's first-party SPSM holdings file. The implemented snapshot is dated 2026-07-16; it is a current holdings source, not a historical constituent database.[^spsm] S&P's methodology requires a U.S. company and applies market-cap, float, liquidity and financial-viability tests when constituents are added.[^sp-us]
3. **Cross-check current listing state.** Join SPSM equities to the SEC's current ticker/exchange/CIK association, then qualify the exact venue-specific InstrumentId through IBKR.[^sec-access] CIK is the durable filing identity; ticker is not.
4. **Require a supported domestic reporting path.** The 20 admitted deals already have primary-filing verification. SPSM supplies the U.S.-company control pool; any future event still has to resolve through the strategy's supported causal filing forms. A foreign-private-issuer path cannot be inferred from broker qualification.
5. **Keep supported securities only.** Admit USD common shares and REIT common shares on the supported U.S. exchanges. Exclude ETFs, closed-end funds, preferred shares, warrants, rights, units, SPAC units, ADRs, foreign-private issuers, test issues, and deficient or bankrupt Nasdaq issues. Resolve multiple share classes independently and retain only the IBKR-qualified line.
6. **Defer selected-deal liquidity to the selected scope.** S&P SmallCap 600 membership supplies a documented baseline liquidity screen. The strategy must still fetch the trailing bars and enforce its own `$1 million` 20-day average daily dollar-volume floor after a public event selects a name. A filed investable merger strategy uses the same `$1 million` turnover floor.[^retail-index] This preserves the staged-loading experiment instead of eagerly downloading bars for 180 controls.
7. **Express affordability as a portfolio constraint.** One share plus estimated entry costs must fit within the strategy's maximum per-deal capital allocation at the snapshot price. For this prototype that is 10% of a `$5,000` shadow book. Do not impose a timeless price rule: the threshold must move with sleeve capital, FX, costs and concentration policy.
8. **Prefer the larger current small-cap constituents without claiming target-prediction alpha.** Exclude already-admitted pending deals and take SPSM constituents in descending holding-weight order after eligibility and affordability. Holding weight is a transparent current size proxy, not a merger signal. The downloaded State Street file did not expose usable sector classifications, so this snapshot makes no sector-neutrality claim; a future refresh should add a point-in-time industry source before imposing sector quotas. Merger waves are associated with industry shocks and aggregate capital liquidity, so a static hot-sector tilt would not be defensible anyway.[^harford]
9. **Freeze the evidence.** Persist the exact InstrumentIds, source observation times, content hashes, applied exclusions, IBKR contract identifiers, prices, and liquidity observations. Membership begins on the freeze date; no name may appear earlier in an evaluation.

## Why this rule is defensible

| Decision | Evidence | Interpretation |
| --- | --- | --- |
| Start with small caps | Cash-target frequency declined monotonically across NYSE size quartiles in Vijh and Yang's U.S. sample.[^vijh] | Small-cap breadth is relevant, but size is not an independent completion-alpha signal. |
| Do not descend into arbitrary microcaps | S&P SmallCap 600 additions must satisfy float, liquidity and financial-viability requirements.[^sp-us] | Current SPSM membership gives the prototype a cleaner control pool than an unconstrained ticker census. |
| Use `$1 million` 20-day dollar volume after event selection | A filed investable merger index requires average daily turnover above `$1 million`; Solactive uses 20-day ADDTV.[^retail-index][^solactive] | This is a selected-deal execution floor, not a reason to fetch 180 unused histories. |
| Avoid takeover-prediction sector bets | Merger waves are strongly associated with industry shocks and aggregate capital liquidity.[^harford] | Current index breadth is preferable to a static hot-sector forecast; this snapshot does not claim sector neutrality. |
| Admit deals only after public evidence | Institutional merger methodologies begin with announced pending transactions.[^solactive] | The event selector, not the candidate-universe builder, owns merger eligibility. |
| Freeze every snapshot | The SEC ticker map is current reference data, whereas CRSP's dedicated historical product stores day-by-day constituent open/close history and dated revisions.[^sec-access][^crsp] | Today's list cannot be projected backward without survivorship and look-ahead bias. |

## Point-in-time contract

> [!warning] Prospective only
> The SPSM holdings, SEC ticker map, and IBKR qualification results establish what was knowable on the snapshot date. They do not reconstruct which securities existed, were eligible, or had the same ticker in 2024 or 2025.

For a forward paper test, refresh and freeze the candidate snapshot on a declared schedule, such as monthly, while allowing a newly announced supported deal to enter only from its public filing timestamp. For a historical alpha test, use a genuine point-in-time security master and constituent history. CRSP's historical index database explicitly supplies daily constituent-open, constituent-close, and pro-forma files from 2012; that product design illustrates the information absent from a current ticker list.[^crsp]

Do not backfill the July 2026 pending deals or the July 2026 SPSM cohort into earlier dates. Doing so would condition on survival, current listing, current index membership, and—among the pending deals—the future merger event itself.

## Implemented snapshot

The prototype config now freezes exactly 200 InstrumentIds:

- 23 independently verified pending fixed-cash deals: the 20-name 2026-07-17 evidence set plus three primary-source additions found in the current MRGR holdings audit;
- 177 SPSM controls from State Street's 2026-07-16 holdings, ordered by current holding weight after removing the admitted deals and enforcing whole-share affordability.

| Added deal | Fixed-cash endpoint | 2026-07-17 IBKR adjusted close | Primary evidence |
| --- | ---: | ---: | --- |
| `SLAB.XNAS` | `$231.00` | `$217.47` | Silicon Laboratories' merger 8-K.[^slab] |
| `TMHC.XNYS` | `$72.50` | `$72.13` | Taylor Morrison's merger 8-K.[^tmhc] |
| `ACA.XNYS` | `$150.00` | `$145.01` | Arcosa's merger 8-K.[^aca] |

IBKR Gateway qualified all 260 names in the audit pool. The final 200 comprise 189 common stocks and 11 REIT common shares, split across 116 NYSE and 84 Nasdaq listings. Every final contract resolved in USD with size increment `1` and advertised `WHATIF` support. IBKR adjusted-close checks on the high-price boundary confirmed that `AGX.XNYS` (`$551.26`), `CVCO.XNAS` (`$566.22`) and `CACC.XNAS` (`$640.00`) could not fit the prototype's `$500` maximum name budget, so they were replaced by the next eligible controls. The highest directly checked retained name was `DAVE.XNAS` at `$440.42`.

The frozen SPSM workbook was retrieved at 2026-07-18 03:52 CEST and has SHA-256 `e787400e9c238cc69350bf7381ebb6b6cbb7246e5dccfaaebb9691d6c4f10504`. The exact admitted InstrumentIds—not the mutable workbook URL—are the authoritative prospective cohort in `shadow.example.yaml`.

This validation establishes a currently resolvable, whole-share control cohort. It does not establish 60-session bar coverage or the `$1 million` selected-deal liquidity test; those belong to the on-demand price stage after a filing selects a security.

## What IBKR validation establishes

The completed Gateway pass validates each exact InstrumentId, primary venue, currency, stock type, whole-share increment and advertised `WHATIF` order support. Direct adjusted-close requests validated the affordability boundary. It does **not** establish 20-day dollar volume, point-in-time historical membership, or that a company is likely to receive an offer. Those facts remain owned by the source, selected-price and event layers above.

## Recommendation for the prototype

Use the resulting 200 names now for three falsifiable checks:

- universe-scoped event data are evaluated for all candidates without eagerly fetching all price histories;
- a causal event selects only supported InstrumentIds and triggers selected-scope OHLCV materialization;
- the exact frozen cohort can run forward without unavailable contracts, fractional-share assumptions, or silent foreign-filer gaps.

Then widen toward the full eligible small-cap source before judging strategy breadth or income quality. A zero-selection result from a 200-name pre-event cohort is expected and does not falsify the event selector; a platform that cannot scale beyond that cohort does falsify the proposed production path.

[^vijh]: Anand Vijh and Ke Yang, [“Are small firms less vulnerable to overpriced stock offers?”](https://www.biz.uiowa.edu/faculty/avijh/Vulnerable.pdf), *Journal of Financial Economics* 110 (2013), especially Table 4.
[^solactive]: Solactive, [Merger-Arbitrage Index Guideline](https://www.solactive.com/downloads/HSIEMA_Guideline-v1.0.pdf), which defines the eligible universe from announced pending deals and uses 20-day average daily traded value.
[^mitchell-pulvino]: Mark Mitchell and Todd Pulvino, [“Characteristics of Risk and Return in Risk Arbitrage”](https://bpb-us-w2.wpmucdn.com/voices.uchicago.edu/dist/d/2771/files/2020/09/JF_riskarb-1.pdf), *Journal of Finance* 56 (2001).
[^spsm]: State Street, [State Street SPDR Portfolio S&P 600 Small Cap ETF](https://www.ssga.com/us/en/institutional/etfs/state-street-spdr-portfolio-sp-600-small-cap-etf-spsm) and its [daily holdings workbook](https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spsm.xlsx), observed 2026-07-18 with holdings dated 2026-07-16.
[^mrgr]: ProShares, [Merger ETF](https://www.proshares.com/our-etfs/strategic/mrgr) and its [daily holdings CSV](https://accounts.profunds.com/etfdata/psdlyhld.csv), observed 2026-07-18 with holdings dated 2026-07-17. MRGR holdings were discovery leads only; their index admits mixed and stock transactions that this prototype excludes.
[^slab]: Silicon Laboratories, [merger announcement on Form 8-K](https://www.sec.gov/Archives/edgar/data/1038074/000119312526036712/d62897d8k.htm), filed 2026-02-04, providing `$231.00` cash per share.
[^tmhc]: Taylor Morrison Home, [merger announcement on Form 8-K](https://www.sec.gov/Archives/edgar/data/1562476/000119312526249694/d111152d8k.htm), filed 2026-06-01, providing `$72.50` cash per share.
[^aca]: Arcosa, [merger announcement on Form 8-K](https://www.sec.gov/Archives/edgar/data/1739445/000173944526000112/aca-20260621.htm), filed 2026-06-22, providing `$150.00` cash per share.
[^sec-access]: U.S. Securities and Exchange Commission, [Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data), including CIK semantics and current ticker/exchange association files.
[^retail-index]: Return Stacked Funds Trust, [filed merger-arbitrage index summary](https://www.sec.gov/Archives/edgar/data/1924868/000199937126009146/rsba-497k_042726.htm), including its major-exchange, deal-size, turnover, completion-estimate, and expected-return eligibility rules.
[^sp-us]: S&P Dow Jones Indices, [S&P U.S. Indices Methodology](https://www.spglobal.com/spdji/en/documents/methodologies/methodology-sp-us-indices.pdf), liquidity and Composite 1500 eligibility.
[^harford]: Jarrad Harford, [“What drives merger waves?”](https://doi.org/10.1016/j.jfineco.2004.05.004), *Journal of Financial Economics* 77 (2005), 529–560.
[^crsp]: CRSP/Morningstar, [CRSPMI Historical Database Guide](https://www.crsp.org/wp-content/uploads/guides/CRSPMI_Historical_Database_Guide.pdf), daily index and constituent history from 2012.
