---
title: Massive Data for Cash-Merger Convergence
date: 2026-07-15
topic: demeter-cash-merger
status: feasibility-decision
related:
  - "[[finding-a-buildable-convergent-engine]]"
  - "[[demeter-current-cash-merger-universe]]"
  - "[[the-tiered-strategy-roster]]"
tags:
  - note
  - demeter
  - merger-arbitrage
  - external-data
  - massive
---

# Massive Data for Cash-Merger Convergence

> [!abstract] Decision
> Massive materially changes the data-feasibility verdict for the archived fixed-cash merger prototype, but it does **not** supply a complete merger-arbitrage tape. It can replace brittle filing discovery and long-horizon IBKR price retrieval with structured REST data. It cannot currently replace deal-term extraction, lifecycle classification, or broker execution checks. Do not restore the strategy yet. First prove historical 8-K backfill, fixed-cash term recovery, delisted-target prices, and next-session causal timestamps on a small set of known completed and broken deals.

## What the July 2026 release actually adds

On 1 July 2026 Massive released two open-beta endpoints: `8-K Disclosures`, which classifies material events into a three-level taxonomy and returns a supporting filing excerpt, and `Disclosure Categories`, which exposes the controlled vocabulary. Massive explicitly names event detection, event-driven strategies and M&A tracking as use cases.[^changelog]

This is structured API consumption over HTTPS, not web-page scraping. The intended seam is REST JSON from Massive, with direct SEC filing text used only when the normalized response lacks the contractual terms. The strategy should never parse Massive's website HTML.

The release solves **discovery**, not the complete merger state. An `8-K Disclosures` record contains accession number, CIK, filing date, filing URL, three category levels, supporting text and currently mapped tickers. It has no structured offer price, consideration type, buyer, agreement date, expected close, outside date, regulatory conditions, completion status, termination status or break value.[^disclosures] The taxonomy endpoint describes categories; it does not add transaction economics.[^taxonomy]

## Coverage against the archived prototype

| Required input | Massive coverage | Decision |
| --- | --- | --- |
| Filing discovery | **Strong.** The SEC EDGAR Index is a filterable master index with form, date, CIK, issuer, ticker, accession and direct SEC URL. The disclosure endpoint adds categorized 8-K events.[^index][^disclosures] | Replace quarterly `master.idx` crawling and broad archive discovery. |
| Announcement detection | **Promising, not proven.** Acquisition/material-agreement categories and supporting excerpts should identify candidates. Exact M&A taxonomy values and recall must be measured from the live taxonomy and known deals. | Use as a candidate generator, never as proof that a deal is eligible. |
| Filing text | **Partial.** `8-K Text` returns parsed text from the core Items sections plus CIK, accession, filing date and SEC URL.[^8ktext] | Parse the normalized text first; fetch the direct SEC submission only when terms or status are absent. No HTML-page scraping. |
| Structured fixed-cash terms | **No.** Neither disclosures nor 8-K text has normalized merger consideration or closing-condition fields.[^disclosures][^8ktext] | A narrow, validated term parser remains necessary. Reject ambiguous, stock, mixed, CVR, earnout and ticking-fee deals. |
| Lifecycle updates | **Partial.** Later 8-K disclosures/text can expose amendments, votes, completions and terminations, but the API does not deliver a normalized deal-status state machine. | Reconstruct lifecycle by accession and CIK; preserve every observed transition and its source. |
| Daily OHLCV | **Yes.** Custom Bars supplies ticker/date-range OHLCV; it is included in every Stocks plan and has an explicit history entitlement by tier.[^bars] | Replace IBKR HMDS for research bars. |
| Price adjustment | **Split-only.** The `adjusted` option adjusts aggregates for splits, not dividends.[^bars] | Model dividends separately if they occur while a target is held. |
| Delisted targets | **Promising.** All Tickers accepts a point-in-time `date`, `active=false`, CIK and FIGI filters and returns delisting date plus stable identifiers.[^tickers] Massive also says its price data remains point-in-time and does not concatenate ticker histories.[^pointintime] | Use CIK as event identity and the dated ticker table to map to price symbols. Validate several completed/delisted targets before trusting a backtest. |
| Ticker-change continuity | **Narrower than the knowledge base implies.** Ticker Events is experimental and its current documentation says `ticker_change` is the only supported event type.[^tickerevents] | Do not rely on it for merger, acquisition or delisting events; use dated All Tickers plus filings. |
| Executability | **No.** Massive describes market data and filings, not the connected account's contract permissions or order behavior. | IBKR remains the authority for qualification, eligibility, order preview, live quotes and execution. |

## Two unresolved historical-data risks

### 1. Filing backfill is unspecified

The 8-K Disclosures, 8-K Text and SEC EDGAR Index pages all state that they are included in every Stocks plan and updated daily, but list plan history as **“not applicable.”**[^disclosures][^8ktext][^index] That phrase does not establish either full EDGAR backfill or a particular start date. The documentation permits filing-date range filters, but range filters alone do not prove historical completeness.

This is the principal go/no-go question for a 2020–2026 test. An authenticated probe must recover known announcements, amendments, completions and terminations from multiple years, including delisted issuers. If it cannot, Massive is only a prospective live source and does not rescue the historical evaluation.

### 2. Filing timestamps are date-only

The documented filing records expose `filing_date`, not SEC acceptance time.[^disclosures][^8ktext][^index] A causal daily backtest must therefore make a new event tradable no earlier than the next market session. Trading on the same date would assume the filing was available before the chosen mark. Raw SEC text or another timestamped primary record may refine this later, but a date-only API must default conservatively.

## Point-in-time identity: useful, with one documentation conflict

The disclosure response says `tickers` are currently mapped to the filer and may be empty.[^disclosures] Current ticker strings must therefore not be the event primary key. Store CIK and accession as event identity, then resolve the tradable symbol as of the observation date through All Tickers, which explicitly supports point-in-time date queries and delisted securities.[^tickers]

Massive's knowledge base says Ticker Events covers full histories including delistings, mergers and acquisitions.[^pointintime] The current endpoint specification contradicts that broad statement: it calls the endpoint experimental and says only `ticker_change` is supported.[^tickerevents] The endpoint specification is the operative contract. Until the schema actually exposes other event types, completion and termination must come from filings rather than Ticker Events.

## Cost and the plan that would be needed

The filing endpoints are currently included in all Stocks plans during open beta. The free Stocks Basic plan is sufficient for a feasibility probe: `$0`, five calls per minute, two years of stock-price history and end-of-day data.[^pricing]

For the intended `2020-08-10` through 2026 evaluation:

- Stocks Starter is `$29/month` but supplies only five years of aggregate history, so in July 2026 it cannot cover the full requested window.
- Stocks Developer is `$79/month` and supplies ten years of aggregate history, which covers the window.
- Stocks Advanced is `$199/month` with real-time data and 20+ years; real time is unnecessary for a daily research reconstruction.[^pricing][^bars]

Do not buy the `$99/month` TMX Corporate Events add-on for this purpose. Its documented event types cover earnings, meetings, dividends, splits, conferences and similar calendar events, but not mergers or acquisitions.[^tmx][^pricing]

Pricing and beta access are current as of 15 July 2026, not durable contracts. The 8-K endpoints use a `vX` path and are explicitly open beta; Ticker Events is experimental.[^changelog][^tickerevents] The changelog also records a different experimental financials endpoint being deprecated and then sunset, demonstrating that experimental interfaces can be replaced.[^changelog] The production design must isolate Massive behind one adapter, preserve immutable raw responses and normalized event snapshots, and fail clearly when the API contract changes.

## What IBKR still owns

Massive should become a research and event-data provider, not a broker substitute. IBKR remains authoritative for:

- exact contract qualification and exchange mapping;
- account eligibility and trading permissions;
- live bid/ask, marketability and order-size granularity;
- commissions and non-transmitting order previews;
- actual order submission, fills, positions, cash and account state.

IBKR need not remain the long-horizon research-history provider. That separation directly removes the archived prototype's HMDS timeout failure: Massive supplies reproducible historical bars; IBKR answers whether the current account can trade the resulting position.

## Required feasibility probe before any rebuild

Use the free plan first and keep the archived strategy untouched.

1. Pull the disclosure taxonomy and identify the exact acquisition, merger-agreement, amendment, completion and termination categories.
2. Select a deliberately mixed validation set: pending fixed-cash deals, completed deals, broken deals, amended prices, tender offers and excluded complex-consideration deals.
3. Verify that the EDGAR Index finds every primary form and that 8-K Disclosures finds the announcement/status events without relying on today's ticker map.
4. Measure whether `supporting_text` or `items_text` recovers fixed offer price and excludes non-cash terms. Follow `filing_url` only when the normalized text is insufficient.
5. Resolve each target by CIK to its ticker on the filing date, then fetch bars through completion or delisting. Check several known ticker changes and delisted targets.
6. Cache raw API responses immutably and replay the lifecycle using next-session availability. Compare the reconstructed states with the primary SEC filings.

> [!success] Promotion criterion
> Reopen the prototype only if Massive recovers the validation set without survivorship omissions and reconstructs fixed-cash terms and lifecycle states deterministically. If disclosures are only prospective or term extraction remains unreliable, keep the merger engine archived rather than dressing a current-universe screen as a historical strategy.

## Sources

[^changelog]: [Massive, “Changelog”](https://massive.com/changelog), 1 July 2026 entry for the open-beta 8-K Disclosures and Disclosure Categories endpoints; also 22 June 2026 experimental Financials sunset entry. Accessed 15 July 2026.

[^disclosures]: [Massive, “8-K Disclosures” REST API](https://massive.com/docs/rest/stocks/filings/8-k-disclosures). Response schema, filters, daily update cadence, plan access and unspecified plan history. Accessed 15 July 2026.

[^taxonomy]: [Massive, “Disclosure Categories” REST API](https://massive.com/docs/rest/stocks/filings/disclosure-categories). Three-level versioned taxonomy schema. Accessed 15 July 2026.

[^8ktext]: [Massive, “8-K Text” REST API](https://massive.com/docs/rest/stocks/filings/8-k-text). Parsed core-Items text schema, filing-date filters, daily cadence and unspecified plan history. Accessed 15 July 2026.

[^index]: [Massive, “SEC EDGAR Index” REST API](https://massive.com/docs/rest/stocks/filings/index). Master filing-index schema, filters, daily cadence and unspecified plan history. Accessed 15 July 2026.

[^bars]: [Massive, “Custom Bars (OHLC)” REST API](https://massive.com/docs/rest/stocks/aggregates/custom-bars). OHLCV contract, split adjustment, recency and plan-specific history. Accessed 15 July 2026.

[^tickers]: [Massive, “All Tickers” REST API](https://massive.com/docs/rest/stocks/tickers/all-tickers). Point-in-time date, active/delisted status, CIK/FIGI identifiers and plan-specific history. Accessed 15 July 2026.

[^pointintime]: [Massive, “How does Massive handle ticker changes and acquisitions?”](https://massive.com/knowledge-base/article/how-does-massive-handle-ticker-changes-and-acquisitions). Point-in-time market-data policy and non-concatenated ticker series. Accessed 15 July 2026.

[^tickerevents]: [Massive, “Ticker Events” REST API](https://massive.com/docs/rest/stocks/corporate-actions/ticker-events). Experimental status and current `ticker_change`-only event contract. Accessed 15 July 2026.

[^pricing]: [Massive, “Pricing”](https://massive.com/pricing). Individual Stocks plan prices, call limits, historical depth and data recency; TMX partner-data price. Accessed 15 July 2026.

[^tmx]: [Massive, “TMX Corporate Events” REST API](https://massive.com/docs/rest/partners/tmx/corporate-events). Supported normalized event types, update cadence and history. Accessed 15 July 2026.
