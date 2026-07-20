---
title: Cash-Merger Deep Backtest Data Boundary
date: 2026-07-20
topic: demeter-cash-merger
status: decision
related:
  - "[[edgartools-listing-identity-resolution-2026-07-18]]"
  - "[[survivorship-free-delisted-market-data-2026-07-20]]"
tags:
  - note
  - demeter
  - merger-arbitrage
  - sec
  - market-data
  - survivorship-bias
---

# Cash-Merger Deep Backtest Data Boundary

> [!abstract] Decision
> A proper historical prototype is feasible, but **not with Edgartools plus IBKR alone**. Use free SEC/Edgartools data for event-first discovery and causal target identity, and add **EODHD EOD Historical Data** for delisted OHLCV and corporate actions. Make **2019-present** the primary research window. IBKR remains the executable-contract validator and live/current-bar source; it must not be the historical delisted-data authority.

## The three required layers

| Layer | Source | What it can establish | Current availability |
| --- | --- | --- | --- |
| Event-first cash-merger discovery | SEC EDGAR through Edgartools | Market-wide candidate filings, filing contents, exhibits, accession and causal acceptance time | Free and already installed. SEC APIs require no key, and Edgartools is MIT-licensed and supports all SEC forms and EDGAR history since 1994.[^sec-api][^edgartools] |
| Point-in-time target listing | Target-owned SEC filing evidence, normalized by Aegis | CIK, affected share class, observed ticker and SEC exchange at or before the decision time; then SEC-exchange-to-MIC normalization | Free, but it is an Aegis resolver rather than an Edgartools convenience lookup. See [[edgartools-listing-identity-resolution-2026-07-18]]. Today's SEC ticker map is only a cross-check, never historical proof.[^sec-access][^sec-xbrl] |
| Survivorship-free daily market data | EODHD delisted-symbol and EOD/action APIs | Raw daily OHLCV for active and delisted targets, delisted enumeration, symbol changes, dividends and splits | Requires a self-serve EODHD subscription for a deep run. The free tier exposes only the past year and 20 calls/day; paid EOD history is advertised from $19.99/month.[^eod-api][^eod-pricing] |

The lifecycle and terminal cash outcome continue to come from EDGAR. A successful deal closes at the contractually evidenced consideration only after completion is causally public; the final exchange print is not assumed to equal settlement.

## Why IBKR cannot close the historical gap

IBKR's own historical-data limitations explicitly list **“data for securities which are no longer trading”** as unavailable. They also warn that data before an exchange move will often be unavailable and recommend a specialized provider when a strategy exceeds IBKR's market-data service.[^ibkr-limitations] This is a product boundary, not a gateway bug and not something contract qualification can repair.

Therefore:

- IBKR can backfill and cache bars while a target is still trading.
- A prospectively accumulated Aegis catalog remains usable after that target disappears.
- IBKR cannot be relied upon to reconstruct an uncached completed target years later.
- An IBKR-only replay over current symbols is not survivorship-free, regardless of how many filings Edgartools finds.

## Why the primary window starts in 2019

EODHD documents that delisted companies after 2018 retain EOD, fundamentals, dividends and splits; pre-2018 delistings retain EOD only.[^eod-delisted] Its fundamentals include CIK for US companies, which gives a second identity join against the filing-derived CIK.[^eod-cik] Starting in 2019 therefore gives the prototype both the delisted price history and the action/identity fields needed to reconcile an event-derived target census. Earlier history can be an extension study only after its missing actions and weaker listing evidence are measured explicitly.

The initial deep run should consequently use:

```text
event discovery: 2018-01-01 onward (for lookback and deals entering 2019)
portfolio evaluation: 2019-01-01 through the latest complete trading day
event universe: all eligible US cash acquisitions found from historical filings
market universe: the event-derived target union, active and delisted
```

No unresolved event-to-security identity, missing price interval or missing corporate action may be silently dropped. Coverage must be reported against the complete event-derived target census before performance is interpreted.

## Alternatives and cost

- **EODHD** is the recommended personal-project source: documented delisted enumeration, ordinary EOD endpoints for delisted symbols, US symbol-change history and self-serve monthly access starting around $19.99.[^eod-delisted][^eod-pricing]
- **Norgate US Platinum** is a stronger long-history validation alternative: it explicitly includes delisted US securities back to 1990, but costs $346.50 for six months and requires a Windows 10/11 local proprietary database.[^norgate-package][^norgate-system]
- **CRSP** is the research benchmark, but CRSP explicitly says its databases target institutional, government and academic licensees and directs individual investors elsewhere.[^crsp-access]

No EODHD, Norgate or CRSP credential is currently configured in this workspace. What is available now—Edgartools, SEC and the running IBKR Gateway—can implement and validate the first two layers and prospective collection, but cannot honestly produce the requested deep survivorship-free P&L history.

## Go/no-go rule

Build the event-first ledger and listing resolver now. Before calling the result a deep alpha backtest, obtain one month of EODHD access and reconcile a fixed sample containing successful deals, failed deals, ticker changes and delisted targets. Proceed only if every event-derived target is either matched to documented history or retained as an explicit coverage failure. If that reconciliation fails, trial Norgate; do not substitute current-universe IBKR data.

[^sec-api]: U.S. SEC, [EDGAR Application Programming Interfaces](https://www.sec.gov/search-filings/edgar-application-programming-interfaces). The APIs require no authentication or API key and provide public submission histories.
[^edgartools]: Edgartools, [official source and documentation](https://github.com/dgunning/edgartools). The project documents its MIT license, all-form support and complete EDGAR history since 1994.
[^sec-access]: U.S. SEC, [Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data). The SEC characterizes its CIK/ticker/exchange association files as periodically updated and does not guarantee their accuracy or scope.
[^sec-xbrl]: U.S. SEC, [EDGAR XBRL Guide, June 2026](https://www.sec.gov/files/edgar/filer-information/specifications/xbrl-guide-2026-06-29.pdf), sections 3.2.4–3.2.4.4 on registered-security title, trading-symbol and exchange facts.
[^eod-api]: EODHD, [End-of-Day Historical Data API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes). It documents raw OHLCV, adjusted close, 30+ years for many instruments, and the free tier's one-year/20-call limits.
[^eod-pricing]: EODHD, [official product page](https://eodhd.com/). It advertises self-serve access from $19.99/month with no long-term commitment.
[^eod-delisted]: EODHD, [Delisted Stock Companies Data](https://eodhd.com/financial-apis/delisted-stock-companies-data-2). It documents delisted enumeration, continued use of the regular EOD/actions endpoints, the post-2018 coverage boundary and US symbol-change history.
[^eod-cik]: EODHD, [US Fundamentals CIK field announcement](https://eodhd.com/financial-apis-blog/new-fields-for-us-fundamentals-feed). EODHD documents CIK in its US fundamentals output.
[^ibkr-limitations]: Interactive Brokers, [Web API historical-data documentation](https://ibkrcampus.com/campus/ibkr-api-page/cpapi-v1/#market-data). The current IBKR Campus documentation explicitly lists data for securities no longer trading as unavailable.
[^norgate-package]: Norgate Data, [US stock-market packages](https://norgatedata.com/stockmarketpackages.php). Platinum includes delisted securities back to 1990 and is listed at $346.50 for six months.
[^norgate-system]: Norgate Data, [Updater installation requirements](https://norgatedata.com/ndu-installation.php). The local updater requires Windows 10 or 11.
[^crsp-access]: CRSP, [Subscription information](https://www.crsp.org/subscription-information/). CRSP explicitly directs individual-investor research to other services.
