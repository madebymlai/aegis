---
title: Public-Filings Special Situations as Atalanta's Pair
date: 2026-07-17
topic: strategy-roster
status: research-decision
aliases:
  - Public-filings special-situations strategy
  - Public-filings event book
related:
  - "[[what-is-a-strategy]]"
  - "[[the-tiered-strategy-roster]]"
  - "[[accessible-ordinary-market-income-after-an-open-search]]"
  - "[[cash-merger-breadth-standalone-or-sub-engine]]"
  - "[[building-the-tiered-roster-after-demeter-v2]]"
tags:
  - research
  - atalanta
  - special-situations
  - public-filings
  - event-driven
  - corporate-actions
---

# Public-Filings Special Situations as Atalanta's Pair

> [!note] Status
> Demoted from `research/` to `notes/` on 2026-07-17: this is a dated roster decision record, not general research. Its general core - the strategy-vs-holding definition - was extracted into [[what-is-a-strategy]].

> [!abstract] Decision
> Combine **approved investment-trust realizations**, **SPAC cash redemptions**, and **explicit odd-lot tender priority** into one research family: **public-filings special situations**. They share a free-filings discovery engine, an event ledger, deadline handling, and forward event-loss budgeting. They do **not** share one valuation formula, so each remains a separate sub-book.
>
> This is the best home for shortlist items 3 and 4, but it is **not yet Atalanta's funded Floor pair**. The filings establish real contractual exits; the evidence does not establish a durable, retail-executable return stream after costs. At €5,000, eligible events will be sparse and concentrated, and the strategy must be allowed to hold zero positions. Build a prospective shadow book first. Promote only if its aligned net return stream improves the complete Atalanta book.

## What the strategy is—and is not

This is not “hold investment trusts” or “hold SPACs.” A holding is an asset exposure ([[what-is-a-strategy]] generalizes this distinction). The strategy acts only when a public filing creates a bounded event:

1. **State:** a security trades below a conservative contractual or approved-realization value.
2. **Action:** buy the eligible instrument and, where required, submit a corporate-action election.
3. **Exit:** receive cash or distributed assets through the event; never drift into an unevaluated residual holding.
4. **Payer / edge:** complexity, deadlines, proration rules, limited capacity, forced selling, or uncertainty about timing—not a generic promise that discounts revert.
5. **Failure:** the event changes, eligibility fails, the deadline is missed, value deteriorates, or costs consume the spread.

“Convergent” describes the expected path from price toward a cash or realizable-value anchor, but convergence is not why the family earns a roster seat. The admission test is whether the repeatable rule earns net ordinary-market returns from a mechanism sufficiently distinct from Atalanta's slow non-equity trend. A contractually convergent trade that is too rare, too costly, or too concentrated still fails.

The correct unit is therefore an **event**, not an asset. Cash between events is unallocated capacity, not a fourth strategy.

## Search method: open first, narrow second

The Exa search began without naming SPACs, tenders, or trusts. It asked where public corporate-action rules create an observable state and exit for a small unlevered investor. Only after mapping the field did the search narrow to the three mechanisms in this note.

> [!info]- Representative open-ended Exa queries
> - “Original research and official documents about repeatable public-filings-driven special-situation trading strategies with explicit contractual or catalyst exits, suitable for small unlevered investors; survey all corporate-action types rather than assuming mergers.”
> - “Empirical studies of public corporate actions where small position size is an advantage because institutional capacity, proration, administrative costs, or shareholder inattention creates predictable value transfer.”
> - “Official regulatory filings and academic research on securities that trade below a verifiable cash or net-asset anchor before a redemption, tender, liquidation, exchange, or open-ending event.”
> - “Research on combining multiple sparse event-driven arbitrage strategies into one portfolio, including opportunity frequency, capital idleness, event risk, correlations, and realistic transaction costs.”
> - “Primary evidence evaluating whether odd-lot tenders, issuer self-tenders, split-offs, SPAC redemptions, rights offerings, and liquidations still earn positive net returns in modern samples.”

The narrow phase then searched exact filing forms, current offer documents, redemption mechanics, EEA eligibility, IBKR election deadlines, fees, and evidence that distinguishes headline returns from the return available to a secondary-market buyer.

> [!warning] Evidence standard
> An offer document proves that a contractual mechanism exists; it does not prove alpha. An academic event study may prove an average historical return; it does not prove that the exact common-only, post-announcement implementation available to this account earned it. Those two claims are kept separate throughout.

## The one family contains three sub-books

| Sub-book | Entry anchor | Intended exit | Strongest evidence | Main reason not ready |
| --- | --- | --- | --- | --- |
| **Approved-realization discounts** | Conservative realizable NAV after a formally approved wind-down, liquidation, uncapped cash exit, or completed asset sale | Distributions, cash election, or sale near conservative realization value | Governance catalysts can close discounts; current trusts execute approved realization programs | Announcement gains may occur before entry; timing, NAV and EEA eligibility remain uncertain |
| **SPAC cash redemptions** | Filing-verified pro-rata trust value net of permitted deductions | Redemption or liquidation cash before de-SPAC exposure | SEC rules and prospectuses clearly establish the redemption right | Published high returns mostly include IPO units and free warrants, not secondary common-only trades |
| **Odd-lot tender priority** | Fixed cash price or conservative Dutch-auction outcome, with an explicit priority clause | Tender settlement | Current Schedule TO outcomes show odd lots accepted in full while other holders were heavily prorated | Broad tender alpha disappeared after costs; no clean modern study isolates odd-lot priority |

They belong together operationally because all three require:

- primary-document discovery and amendment monitoring;
- beneficial-owner and jurisdiction eligibility checks;
- issuer and broker deadline management;
- a conservative net-payoff calculation;
- an explicit election or realization path;
- zero exposure after the intended event unless a new thesis is approved.

They must remain separate analytically. Trust NAV is an uncertain asset-realization estimate, SPAC trust cash is a filing-derived cash claim, and an odd-lot tender is a priority rule embedded in an offer. Hiding those differences behind one “discount” number would make the module shallow and the risk controls false.

## Sub-book A: approved-realization investment-trust discounts

The viable version is **not** “buy a wide discount and wait.” Closed-end-fund discounts can be persistent and nonlinear. The strategy acts only after a hard catalyst has crossed from possibility into an approved or committed realization process.[^discountdynamics]

### Eligible catalyst hierarchy

1. **Approved liquidation or managed wind-down.** This is the cleanest trust event. Enter only after approval and value the remaining assets, liabilities, costs, retentions, and time conservatively.
2. **Full or genuinely uncapped tender, open-ending, or cash option.** The account must be eligible; the record date must not have passed; the cash option and value formula must be clear.
3. **Signed asset sale plus committed capital return.** Count only closed or substantially unconditional sales with disclosed proceeds and a usable timetable.
4. **Continuation-vote failure followed by an approved realization.** A continuation vote alone is a precursor, not an exit.

Reject as entry signals:

- generic discount mean reversion;
- an activist stake, strategic review, or buyback without a binding exit;
- a merely proposed vote;
- capped tenders whose residual shares can re-widen;
- opaque or stale private-asset NAVs;
- offers excluding the EEA or whose record date has passed.

US activist attempts from 1988–2003 reduced target-fund discounts by more than ten percentage points on average, showing that governance can unlock NAV.[^activistcef] But open-ending studies find that a large part of the gain arrives around the announcement, before a post-announcement retail entry.[^openending] More damagingly, closed-end-fund tender arbitrage in 2000–2015 produced only about 0.5% abnormal return and was insignificant after transaction costs.[^tenderreexam] The evidence supports **approved realization at a remaining net discount**, not routine pre-expiry tender trading.

A current approved wind-down can generate successive tenders and distributions rather than one clean payment, as the Schroders Capital Global Innovation Trust history illustrates.[^scgit] That improves observability but adds duration, asset-sale, retention, and NAV-write-down risk. The conservative value must therefore be:

$$
V_{trust}=NAV_{current}-h_{asset}-c_{realization}-c_{tax/FX}-b_{time}-b_{model}
$$

where every haircut is declared before entry. The rule buys only when the market price is below this value by both a percentage hurdle and a meaningful euro hurdle.

### EU-account constraint

Eligibility is a first-class data field. A 2025 CQS Natural Resources Growth and Income tender excluded EEA residents, so an Italian investor could not assume access merely because the shares traded through IBKR.[^cqstender] Other offers fix entitlement at a historical record date or guarantee only a capped basic entitlement.[^esct] A screen that discovers the event but ignores residence, ownership date, or cap has not discovered an executable trade.

## Sub-book B: SPAC cash redemptions

The SEC's 2024 rules and current prospectuses confirm the core mechanics: IPO proceeds are substantially held in trust; before a de-SPAC transaction, public shareholders are generally offered the choice to redeem for their pro-rata share of trust cash, subject to the filing's permitted deductions and procedures.[^secspacrule] Current 2026 prospectuses also state that a shareholder may redeem irrespective of how it voted, while requiring timely identification and delivery of the shares.[^spacprospectus]

The trade contract is narrower:

- **State:** secondary-market common shares trade below a conservative, filing-verified trust value before an eligible redemption or liquidation event.
- **Action:** buy common shares only after settlement and broker deadlines leave a safe buffer.
- **Exit:** submit redemption and receive cash; otherwise sell before the right expires.
- **Prohibition:** never carry the position into the operating-company de-SPAC thesis.

The conservative value is:

$$
V_{spac}=\frac{cash_{trust}+eligible\ interest-permitted\ withdrawals-taxes-expenses}{redeemable\ public\ shares}-fees-FX-buffer
$$

Every variable comes from the latest filing or is treated as unknown. Extension contributions, tax withdrawals, sponsor loans, caps, share-class changes, and amendments must be monitored rather than inferred from a screener.

The published return literature does **not** validate this exact implementation. Gahng, Ritter, and Zhang report a 23.9% annualized “optimal redemption” return for 2010–2020 SPAC-period investors, but their strategy buys IPO or first-day **units** and includes warrants or rights.[^spacsrfs] Klausner and coauthors likewise find attractive returns for redeeming IPO investors, largely supported by free warrants and rights, alongside poor post-merger economics.[^soberspac] Those results cannot be assigned to a secondary-market common-only strategy.

An asset manager describes buying secondary SPAC common below trust and redeeming, but its broader program also participates in IPOs and warrants; this is useful implementation evidence with a direct commercial conflict, not independent proof of the common-only return.[^aqrspac]

> [!important] SPAC conclusion
> The cash claim is real and the failure boundary is clear. The edge is not yet demonstrated for this account's exact implementation. The first deliverable is a prospective, common-only shadow ledger showing observable price, verified trust value, IBKR cutoff, election success, cash date, and all costs.

> [!failure] Superseded 2026-07-24 - the universe has collapsed
> This sub-book is closed on **breadth**, which is a harder kill than the implementation doubt
> recorded above. Total SPAC trust assets fell roughly 90% from about USD 187.5bn across 2022-23 to
> about USD 20bn by June 2025, and around 25% of live deals now trade at a **premium** to trust
> rather than a discount. The diversified basket of below-trust names this sub-book required no
> longer exists at anything like the size the evidence was drawn from, so the shadow ledger above
> would be measuring a handful of idiosyncratic situations rather than a repeatable rule.
>
> Sourced from industry data rather than peer-reviewed measurement; re-check before reversing.
> Sub-books A and C are unaffected. See [[income-must-accrue-not-be-captured]].

## Sub-book C: explicit odd-lot tender priority

An odd-lot clause can exempt holders below 100 shares from general proration. This is a genuine contractual capacity niche—but only when the latest offer explicitly says so.

Current filings show that the clause still operates. In Anebulo's 2026 issuer tender, 134,306 odd-lot shares were accepted in full while the general proration factor was only 3.47392%.[^anebulo] In Optimum's 2026 tender, odd lots were accepted in full while general proration was approximately 48.6%.[^optimum] Other current offers explicitly make odd lots subject to proration, proving that the rule must be parsed rather than assumed.[^nooddlot]

The preferred order is:

1. **Fixed-price cash tender with explicit odd-lot priority.** Cleanest payoff.
2. **Dutch auction with a sufficiently conservative lowest acceptable outcome.** The clearing price remains uncertain.
3. **Stock-for-stock split-off with odd-lot priority.** Reject initially unless delivery value can be hedged or its market risk can be bounded without violating account constraints.

The contract is:

- **State:** the current Schedule TO gives aggregate beneficial owners of fewer than 100 shares priority, and a conservative tender outcome exceeds the all-in acquisition cost.
- **Action:** acquire fewer than 100 shares in aggregate and tender all, completing every required election.
- **Exit:** tender cash or approved delivered securities.
- **Failure:** withdrawal or amendment, ownership aggregation, a low Dutch clearing price, missed broker cutoff, failed delivery, or market loss on rejected shares.

“Odd lot” does not require buying 99 shares. Ninety-nine is the maximum under a typical clause; at €5,000, an expensive security may use fewer shares and leave cash idle.

The historical evidence demands restraint. A modern re-examination found that the roughly 9% tender profits in older studies disappeared during 2000–2015.[^tenderreexam] That paper does not separately identify the tiny explicit-priority subset, so it neither proves nor disproves this exact rule. No clean peer-reviewed modern sample found in the Exa sweep establishes a durable after-cost odd-lot return. The clause is a hypothesis generator, not a sleeve-level track record.

## Free discovery and the event ledger

Paid merger or credit data is unnecessary for the first test. EDGAR is free, its submissions APIs require no authentication, and its daily and full indexes support discovery when the issuer is not known in advance.[^edgaraccess][^edgarapi]

The US scanner should monitor at least:

- `SC TO-I`, `SC TO-I/A`, `SC TO-T`, and amendments for tenders;
- `PREM14A`, `DEF14A`, `DEFA14A`, `8-K`, `6-K`, `425`, `S-4`, and `F-4` for SPAC votes, extensions, deals, and amendments;
- `N-2`, `N-CSR`, tender filings, and proxy materials for US closed-end funds.

For UK investment trusts, official issuer RNS announcements and circulars are primary. The AIC supplies free daily prior-close data, alerts, and a long corporate-action history, but delayed announcements and licensing limits mean it is a discovery aid rather than the sole source.[^aicdata] The FCA National Storage Mechanism is free and official but explicitly not real-time.[^fcansm]

Every candidate becomes one immutable event record containing:

| Field group | Required fields |
| --- | --- |
| **Identity** | issuer, instrument, CIK/LEI, event type, accession/document URL |
| **Causality** | first-public timestamp, each amendment timestamp, observation timestamp |
| **Terms** | anchor value, formula, cap, proration, record date, eligibility, jurisdiction |
| **Execution** | market price and timestamp, settlement buffer, issuer deadline, broker cutoff, election route and confirmation |
| **Payoff** | conservative gross value, commission, spread, FX, tax/stamp, event costs, time buffer, net euro spread |
| **Risk** | failure value, loss if failed, uncertain inputs, asset/NAV liquidity, maximum capacity |
| **Outcome** | accepted quantity, settlement value/date, realized costs, residual position, postmortem |

Amendments append new state; they never overwrite what was knowable at entry. This ledger is the research asset. A backtest assembled from final offer terms would import hindsight into both eligibility and payoff.

## IBKR and €5,000 economics

IBKR supports voluntary corporate-action elections and Dutch auctions through Client Portal, but its deadline may precede the issuer's. Elected shares must be settled by the broker cutoff, and an election without confirmation is not processed.[^ibkrca][^ibkrcamanager] The fee page currently lists general mandatory and voluntary corporate-action processing as free, while separately listing a USD 100 DTC DWAC fee.[^ibkrfeesother] Because SPAC documents sometimes mention DTC/DWAC delivery, a live-paper exercise or broker confirmation must establish which path and fee actually apply before capital is used.

US stock commissions can be small—IBKR's tiered schedule lists USD 0.0035 per share with a USD 0.35 order minimum—but exchange, regulatory, spread, and FX costs remain.[^ibkruscommission] Automatic currency conversion adds about 0.03% to the exchange rate.[^ibkrfx]

UK trust economics are heavier. Tiered UK commission is 0.05% with a GBP 1 minimum, and electronic purchases of most UK shares generally incur 0.5% SDRT, subject to instrument-specific exemptions.[^ibkrukcommission][^sdrt] Four €1,250 trust positions would incur roughly €25 of SDRT alone, before eight minimum commissions, FX, spreads, and realization haircuts. A 0.5% quoted discount is therefore not an edge.

At this account size:

- a USD 0.05 spread on 500 SPAC shares is only USD 25 gross;
- odd-lot capacity is contractually small and may deploy only part of the account;
- trust-event diversification may mean only a few positions, each exposed to idiosyncratic NAV and timetable risk;
- fixed operational effort matters even when the broker fee is zero.

A candidate must clear **both** an all-in percentage hurdle and a minimum expected euro-profit hurdle. The exact thresholds should be preregistered from the prospective census, not chosen after seeing which historical trades survive.

## Risk and allocation architecture

Rolling volatility is the wrong primary sizing variable. Event payoffs are discontinuous: a quiet price series before a failed vote or missed election can report low volatility precisely when forward loss is large. Event-driven risk work instead emphasizes explicit scenario and event-failure analysis.[^eventrisk]

For each event, declare:

$$
L_{event}=position\ size\times(entry\ price-failure\ value)+failure\ costs
$$

and size from a whole-book event-loss budget. Correlated legal, liquidity, market, broker, and funding failures mean that three different event labels are not automatically three independent bets. During stress, event-strategy correlations can rise.[^corporatearb]

Common admission gates should be:

1. The primary filing and every amendment have been captured.
2. The exact account is eligible by residence, record date, beneficial ownership, and instrument class.
3. Shares can settle before an intentionally early IBKR cutoff, and the election route has been rehearsed.
4. Conservative value is independently reconstructible; unknown terms are haircuts, not optimistic estimates.
5. Net spread clears percentage and euro hurdles after commission, bid/ask, FX, tax/stamp, corporate-action, and time reserves.
6. Failure loss fits the event budget without relying on cross-sectional diversification.
7. The rule guarantees no accidental post-event exposure.
8. If no event qualifies, allocation is zero.

The allocator should compare eligible events by conservative expected net value per unit of event-loss budget, while respecting the odd-lot cap and liquidity. It should **not** manufacture constant exposure or allocate by trailing volatility merely to keep the sleeve full.

## Is this Atalanta's pair?

Mechanically, it is a better candidate than another momentum strategy. Atalanta responds to persistent directional movement in non-equity markets. This family seeks small, issuer-specific value transfers created by legal terms, deadlines, and approved realizations. Its signal, holding period, payer, and failure state are different.

But mechanism difference is only a hypothesis of diversification. Trust discounts and event spreads can widen during liquidity stress; several “independent” events can fail together when financing, markets, or broker operations seize up. Practitioner multi-strategy research argues that varying opportunity sets and low-but-nonzero correlations can justify tactical capital sharing, while also acknowledging that correlations rise under stress.[^corporatearb] That supports the shared family architecture, not a guaranteed hedge.

The roster decision should therefore be:

> [!success] Research classification
> **Incubating ordinary-market candidate; zero when empty.** It may eventually pair with Atalanta, but it does not yet deserve a Floor allocation, fixed Target weight, or an assumed “income” label.

Promotion requires an aligned whole-book test against Atalanta, including:

- point-in-time opportunity arrival and cash occupancy;
- net realized return after every explicit cost;
- maximum loss and event-failure scenarios;
- behavior during equity selloffs, liquidity shocks, and trend reversals;
- marginal Sharpe, drawdown, and crisis behavior of the complete book;
- evidence that returns do not come from accidental equity, duration, GBP/USD, or stale-NAV exposure.

At €5,000 the family cannot be justified by a promise of “a bunch of uncorrelated strategies.” There will be too few simultaneous events. Robustness comes first from refusing weak events, budgeting failure loss, and holding cash—not from counting sub-books.

## Build order and falsification gates

### Phase 1: prospective census, no capital

For at least six months, run the free discovery process and record every candidate before knowing its outcome. Include rejected events and the exact rejection reason. Manually verify every primary document.

Success requires:

- the scanner finds events before the broker cutoff;
- terms and amendments can be reconstructed without paid data;
- at least one sub-book supplies repeatable executable opportunities;
- conservative expected euros exceed the operational and market costs.

Kill or pause a sub-book if:

- most apparent edges disappear when price timestamps and eligibility are corrected;
- opportunities are EEA-ineligible, already beyond the record date, or below the euro hurdle;
- value depends on stale/private NAV or an unhedgeable stock delivery;
- broker processing cannot be confirmed safely;
- the only positive history comes from warrants, IPO allocations, pre-announcement ownership, or hindsight.

### Phase 2: live-paper election rehearsal

Use Client Portal up to—but not through—the final irreversible step to confirm visibility, ownership aggregation, cutoff, election fields, confirmation record, and stated fees. Ask IBKR support specifically whether ordinary SPAC redemptions use the free voluntary-action path or can incur a DWAC/pass-through charge.

### Phase 3: tiny capital tracer

Only a fixed-price odd-lot cash tender or a plainly documented SPAC cash redemption should be the first tracer. Use a size whose full event failure would not matter to the portfolio. An investment-trust realization should wait until the NAV haircut and jurisdiction workflow have been exercised prospectively.

### Phase 4: aligned research candidate

Build the complete event stream with cash on empty days and compare it with Atalanta on identical dates. Promotion is based on complete-book utility, not the apparent Sharpe of marked, illiquid event positions.

## Final answer

Shortlist items 3 and 4 combine coherently as **one public-filings special-situations family with three contract-specific engines**. The shared scanner and event ledger are worth building. The investable claim is much narrower than the labels:

- trusts: approved realization only;
- SPACs: secondary common below verified trust, redeemed before de-SPAC;
- tenders: explicit odd-lot priority, preferably fixed cash.

The family is a plausible economic complement to Atalanta, not yet its proven pair. The honest next allocation is zero; the next piece of work is a point-in-time prospective event ledger.

## Sources

[^discountdynamics]: Copeland, L., “Arbitrage Bounds and the Time Series Properties of the Discount on UK Closed-End Mutual Funds,” *Journal of Business Finance & Accounting* 34(1–2), 2007. The long-run discount need not be zero, and the discount process exhibits long memory and nonlinearity. [Journal article DOI](https://doi.org/10.1111/j.1468-5957.2006.00649.x).

[^activistcef]: Bradley, M. et al., “Activist Arbitrage: A Study of Open-Ending Attempts of Closed-End Funds,” covering US activist attempts from 1988–2003. The activist creates the catalyst, so this is not passive post-announcement alpha. [Columbia-hosted paper](https://business.columbia.edu/sites/default/files-efs/pubfiles/4118/activist_arb.pdf).

[^openending]: Research in the *Review of Quantitative Finance and Accounting* finds a large announcement-period response around open-ending, implying that much of the pre-event discount may be captured before a new investor can enter. [Article record](https://econpapers.repec.org/article/kaprqfnac/v_3a50_3ay_3a2018_3ai_3a2_3ad_3a10.1007_5fs11156-017-0634-0.htm).

[^tenderreexam]: Kadapakkam, P., Zhang, Y. & Yildirim, H., “A reexamination of the tendering profit anomaly,” *Review of Quantitative Finance and Accounting* 56, 2021. Older tender profits disappeared in 2000–2015; closed-end-fund tender profits were small and insignificant after costs. [Article record](https://ideas.repec.org/a/kap/rqfnac/v56y2021i4d10.1007_s11156-020-00935-4.html).

[^scgit]: AIC-hosted announcement history for Schroders Capital Global Innovation Trust's approved wind-down and successive tenders. This demonstrates mechanics and duration, not alpha. [AIC announcement](https://www.theaic.co.uk/companydata/schroders-capital-global-innovation-trust/announcements/9556103).

[^cqstender]: CQS Natural Resources Growth and Income 2025 tender circular, including EEA exclusions. [Offer circular](https://cynprotectyourinvestment.com/wp-content/uploads/2025/05/3845-Project-Coast-Circular_WEB.pdf).

[^esct]: European Smaller Companies Trust 2025 tender circular, including its record date and capped basic entitlement. [Issuer-hosted circular](https://cdn.janushenderson.com/webdocs/ESCT+Tender+offer+circular+2025.pdf).

[^secspacrule]: SEC, “Special Purpose Acquisition Companies, Shell Companies, and Projections,” final rule, 2024. The rule describes trust, redemption, conflicts, dilution, and disclosure mechanics. [Final rule PDF](https://www.sec.gov/files/rules/final/2024/33-11265.pdf) and [rule page](https://www.sec.gov/rules-regulations/2024/01/s7-13-22).

[^spacprospectus]: A 2026 SPAC prospectus states the redemption calculation, vote independence, beneficial-holder identification, and tender process; exact terms remain issuer-specific. [SEC filing](https://www.sec.gov/Archives/edgar/data/2096900/000121390026010180/R2.htm). A second filing illustrates the two-business-day delivery deadline. [SEC filing](https://www.sec.gov/Archives/edgar/data/2028935/000121390026058177/R19.htm).

[^spacsrfs]: Gahng, M., Ritter, J. & Zhang, D., “SPACs,” *Review of Financial Studies* 36(9), 2023. Its optimal-redemption return includes IPO/first-day units and attached warrants or rights. [Author-hosted paper](https://site.warrington.ufl.edu/ritter/files/SPACs.pdf).

[^soberspac]: Klausner, M., Ohlrogge, M. & Ruan, E., “A Sober Look at SPACs,” *Yale Journal on Regulation*. Redeeming IPO investors benefit materially from warrants/rights; post-merger investors face dilution and poor outcomes. [Stanford-hosted paper](https://law.stanford.edu/wp-content/uploads/2022/07/2022-01-24-A-Sober-Look-At-SPACs-Yale-Journal-on-Regulation.pdf).

[^aqrspac]: AQR, “Are SPACs Still Alive?” describes secondary-market below-trust redemptions inside a broader program that also has IPO and warrant exposure. Treat as conflicted practitioner implementation evidence. [AQR paper](https://www.aqr.com/-/media/AQR/Documents/Insights/White-Papers/Are-SPACs-Still-Alive.pdf?sc_lang=en).

[^anebulo]: Anebulo Pharmaceuticals, 2026 final Schedule TO amendment: odd-lot shares accepted in full while the general proration factor was 3.47392%. [SEC filing](https://www.sec.gov/Archives/edgar/data/1815974/000149315226004156/formsctoia.htm).

[^optimum]: Optimum Communications, 2026 tender results: odd lots accepted in full and other tenders prorated at approximately 48.6%. [SEC filing](https://www.sec.gov/Archives/edgar/data/1702780/000121390026075249/ea029202904ex99a5c.htm).

[^nooddlot]: A current issuer tender whose terms explicitly subject odd lots to proration, demonstrating that priority cannot be assumed. [SEC offer document](https://www.sec.gov/Archives/edgar/data/859796/000114036126023437/ny20074859x2_exa1i.htm).

[^edgaraccess]: SEC, “Accessing EDGAR Data,” describing free public access and daily/full indexes. [SEC documentation](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).

[^edgarapi]: SEC, “EDGAR Application Programming Interfaces,” describing unauthenticated submissions JSON and bulk archives. [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).

[^aicdata]: Association of Investment Companies, research-tool FAQ: prior-close update timing, announcement delay, alerts, history, and licensing constraints. [AIC FAQ](https://www.theaic.co.uk/research-tools/faq).

[^fcansm]: FCA, National Storage Mechanism investor guide. The NSM is free and official but not real-time. [FCA guide](https://www.fca.org.uk/publication/primary-market/nsm-investor-user-guide.pdf).

[^ibkrca]: Interactive Brokers Ireland, corporate-action instructions: voluntary-election workflow, region-specific earlier deadlines, settled-share requirement, and best-efforts handling. [IBKR instructions](https://www.interactivebrokers.ie/en/trading/corp-action-instructions.php).

[^ibkrcamanager]: Interactive Brokers, Corporate Action Manager guide, including Dutch-auction elections and confirmation requirements. [IBKR guide](https://www.ibkrguides.com/clientportal/support_corporateaction.htm).

[^ibkrfeesother]: Interactive Brokers Ireland, other fees: general corporate actions are listed as free; DTC DWAC deposits/withdrawals are listed separately at USD 100. [IBKR fee schedule](https://www.interactivebrokers.ie/en/pricing/other-fees.php).

[^ibkruscommission]: Interactive Brokers Ireland, US stock commissions: tiered and fixed schedules plus third-party fees. [IBKR commission schedule](https://www.interactivebrokers.ie/en/pricing/commissions-stocks.php?re=amer).

[^ibkrfx]: Interactive Brokers Ireland, spot-currency commissions and automatic-conversion spread. [IBKR FX pricing](https://www.interactivebrokers.ie/en/pricing/commissions-spot-currencies.php).

[^ibkrukcommission]: Interactive Brokers, European stock commissions, including UK tiered pricing. [IBKR commission schedule](https://www.interactivebrokers.co.uk/en/pricing/commissions-stocks-europe.php).

[^sdrt]: UK Government, “Tax when you buy shares,” including the general 0.5% SDRT on electronic share purchases and exceptions. [GOV.UK guidance](https://www.gov.uk/tax-buy-shares/buy-shares-electronically).

[^eventrisk]: Jorion, P., “Risk Management for Event-Driven Funds,” on discontinuous, skewed event payoffs and forward-looking failure analysis. [SSRN paper](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1018281).

[^corporatearb]: AQR, “Corporate Arbitrage—Overview and Benefits of a Dynamic Multi-Strategy Approach.” Useful for the capital-sharing architecture and time-varying opportunity sets; it is asset-manager research with a direct conflict of interest. [AQR paper](https://www.aqr.com/-/media/AQR/Documents/Whitepapers/AQR-Corporate-Arbitrage--Overview-and-Benefits-of-a-Dynamic-Multistrategy-Approach.pdf?sc_lang=en).
