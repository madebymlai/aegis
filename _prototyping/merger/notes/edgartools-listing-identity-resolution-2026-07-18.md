---
title: Edgartools for Point-in-Time Listing Identity Resolution
date: 2026-07-18
topic: demeter-cash-merger
status: research-note
related:
  - "[[prospective-200-name-universe-rule]]"
  - "[[current-fixed-cash-universe-2026-07-17]]"
tags:
  - note
  - demeter
  - merger-arbitrage
  - sec
  - instruments
  - edgartools
---

# Edgartools for Point-in-Time Listing Identity Resolution

> [!abstract] Decision
> Use **Edgartools as the EDGAR retrieval and Inline XBRL parsing layer**, but keep listing resolution as an Aegis-owned domain module. Resolve a target security from target-owned, time-causal filing facts and preserve every candidate plus its context and accession. Never construct an `InstrumentId` from `Company.get_ticker()`, `find_ticker(cik)`, or today's SEC ticker map alone.

## What Edgartools provides

Edgartools materially reduces the mechanical work:

| Need | Edgartools support | Boundary |
| --- | --- | --- |
| Resolve a known ticker or CIK to an SEC filer | `Company`/`Entity`, backed by bundled reference data and a live-SEC fallback | Ticker lookup is current reference data, not event-time identity. |
| Obtain the target's filings | `Company.get_filings(...)`, including form, accession, filing date and acceptance timestamp | A merger filing submitted by the acquirer does not identify the target's CIK automatically; event-to-target entity linking remains custom. |
| Read SEC submissions metadata | `Company.data` exposes CIK, current `tickers`, current `exchanges`, and `former_names` | `former_names` is issuer-name history, not ticker, venue, or share-class history. |
| Parse filing-level cover-page facts | `filing.xbrl()` and `xbrl.facts.query()` expose facts, `context_ref`, entity identifier, and dimension members | The resolver must pair facts by context and choose the relevant registered security. |
| Represent multiple ticker rows | `Company.tickers` returns all current ticker strings; the SEC exchange reference table has one row per CIK/ticker/exchange | Edgartools does not expose a typed `ObservedListing`, nor decide which class a merger concerns. |

These capabilities follow the SEC's own APIs. The submissions endpoint contains current name, former names, ticker symbols and exchanges plus filing history; its data update throughout the day.[^sec-api] Edgartools parses those fields directly into `CompanyData`.[^edgar-submissions] Its reference module can also load a current `[cik, ticker, company, exchange]` table and directly fetch the SEC's `company_tickers_exchange.json`.[^edgar-reference]

## The important sharp edges

### Current mappings are not point-in-time mappings

The SEC describes `company_tickers_exchange.json` as a periodically updated association file and explicitly does **not** guarantee its accuracy or scope.[^sec-access] Neither that file nor the `tickers`/`exchanges` arrays in today's submissions response carries effective-from/effective-to dates. Freezing a downloaded copy makes a prospective observation reproducible; it does not reconstruct a historical listing.

Edgartools' bundled ticker parquet is updated with library releases and is tried before local or live SEC data.[^edgar-reference] That is useful for discovery and current cross-checking, but especially dangerous if silently used in a historical run.

### CIK identifies the filer, not a security

A CIK can have several registered securities and several ticker symbols. `Company.tickers` preserves the list, but `Company.get_ticker()` simply returns its first element.[^edgar-company] The lower-level `find_ticker(cik)` is more hazardous for this use: for multi-ticker CIKs it prefers a non-hyphenated ticker and then the shortest ticker, with hard-coded overrides.[^edgar-primary-ticker] That is a display convenience, not merger-security resolution.

Therefore, no API that returns one ticker for a CIK may sit on the event-to-`InstrumentId` path.

### Multi-class cover facts must be joined by XBRL context

The SEC's current XBRL guide models registered securities with `dei:Security12bTitle`, `dei:SecurityExchangeName`, and `dei:TradingSymbol`. Multiple classes use `StatementClassOfStockAxis` or `ClassesOfShareCapitalAxis`; a security traded on multiple exchanges can additionally use `EntityListingsExchangeAxis`. The title and exchange are paired in the same context.[^sec-xbrl]

Edgartools' full facts view retains `context_ref`, the filing entity identifier, and every dimension/member column, which is enough to implement that join.[^edgar-facts] However, the convenience `xbrl.entity_info['ticker']` must not be used: its parser collapses DEI facts into a dictionary keyed only by concept, so repeated `TradingSymbol` facts overwrite one another.[^edgar-entity-info]

The safe extraction unit is therefore:

```text
(accession, acceptance_timestamp, context_ref,
 security_title, trading_symbol, sec_exchange_code,
 class_axis_member, listings_exchange_member, target_cik)
```

The SEC also states that no instance type requires `Security12bTitle`; absence is legitimate.[^sec-xbrl] An event 8-K, proxy, tender filing, or foreign-filer document may therefore lack a complete cover-page tuple even when the transaction is valid. The resolver should search the target's latest eligible target-owned filing available at or before the decision timestamp, then return `Unresolved` or `Ambiguous` if the evidence remains insufficient.

## Exchange to MIC is still a custom crosswalk

SEC cover facts use EDGAR-defined exchange acronyms such as `NYSE`, `NASDAQ`, `NYSEAMER`, and `Phlx`; they are not ISO MICs.[^sec-xbrl] The ISO 10383 Registration Authority publishes the current MIC registry, including operating/segment MIC metadata.[^iso-mic]

Aegis must therefore own and test the narrow semantic mapping used by its supported universe, for example `NYSE -> XNYS`, `NASDAQ -> XNAS`, and `NYSEAMER -> XASE`. Neither Edgartools nor the ISO file can infer that policy automatically from a raw exchange name. Preserve the original SEC value beside the normalized MIC and version the crosswalk.

## Other open-source tools

| Tool | Material use here | Recommendation |
| --- | --- | --- |
| [Arelle](https://arelle.readthedocs.io/en/latest/) | Mature XBRL/Inline XBRL processor with XBRL Dimensions and SEC EDGAR validation support.[^arelle] | Use as a conformance oracle for difficult filings or parser regression fixtures; it still does not choose the target share class or create an Aegis instrument. |
| [sec-cik-mapper](https://sec-cik-mapper.readthedocs.io/) | Convenient daily-generated CIK/ticker/exchange mappings derived from SEC files, including one-to-many ticker mappings.[^cik-mapper] | Optional batch convenience only. It duplicates current SEC reference data and supplies no authoritative event-time security history. |
| [sec-edgar-downloader](https://github.com/jadchaar/sec-edgar-downloader) | Downloads filings by CIK/ticker and form.[^sec-downloader] | Not needed if Edgartools already owns retrieval; it does not add XBRL-context listing resolution. |

No reviewed open-source tool supplies the missing end-to-end object: a causally dated target CIK plus the exact security title, share class, ticker, primary listing MIC, ambiguity state, and provenance. That result must be constructed and persisted by Aegis.

## Recommended resolver contract

1. Extract the transaction target and target security language from the event and its exhibits; resolve the **target CIK**, preserving evidence and ambiguity.
2. Query only target-owned filings accepted no later than the decision timestamp.
3. With Edgartools, query the raw DEI facts for `Security12bTitle`, `TradingSymbol`, and `SecurityExchangeName`; group by `context_ref` and retain class/listing dimensions.
4. Match the transaction's affected security description to those candidates. Never select the first or shortest ticker.
5. Use a frozen SEC ticker/exchange snapshot only to cross-check a filing-derived candidate or to produce explicitly lower-confidence candidates. It cannot prove past identity.
6. Normalize the evidenced SEC exchange code through an Aegis-owned SEC-to-MIC table.
7. Return a typed result: `Resolved(ObservedListing)`, `Ambiguous(candidates, evidence)`, `Unresolved(reason, evidence)`, or `NonPublic(evidence)`.
8. Only `Resolved` proceeds to `InstrumentId` construction and IBKR qualification. Broker qualification validates executability; it must not invent the listing identity.

## Historical active-deal reconstruction

Edgartools can support a historical active-deal ledger without starting from a present-day ticker universe. Its market-wide `get_filings(...)` API reads SEC quarterly indexes and filters by calendar year, quarter, filing-date range and one or more form types.[^edgar-market-filings] Each resulting filing exposes the accession and filing content; parsed index headers expose the SEC acceptance timestamp and 8-K items, while `attachments` and `full_text_submission()` expose agreements, proxies, tender materials and amendments.[^edgar-headers]

Edgartools does **not** supply a merger lifecycle or an `active_at` series. Aegis must construct one causally:

1. Enumerate candidate forms market-wide by historical filing interval rather than by today's companies or tickers.
2. Parse announcements and terms from target/acquirer `8-K` and `6-K`, merger proxies and registrations, tender forms and exhibits.
3. Record every observation at its SEC acceptance timestamp.
4. Fold amendments, approvals, revised terms, outside dates, completions and withdrawals into a deterministic deal state.
5. A deal is active at decision time only after its qualifying announcement is available and before a causally observed completion or termination.
6. Persist both normalized events and verified-empty checked intervals in the Aegis custom-data catalog.

Use quarterly/daily SEC indexes for exhaustive discovery; full-text search is a candidate accelerator, not proof of complete coverage. The SEC publishes public filing indexes from 1994Q3 onward, but a clean strategy history will be shorter: older filings have weaker structure, historical listing facts may lack usable Inline XBRL, foreign/private/OTC cases need additional resolution, and post-completion delisted targets still require survivorship-free market prices.[^sec-indexes]

Therefore EDGAR plus Edgartools can reconstruct historical **event membership and lifecycle**, but cannot alone produce an executable backtest. The separate market-data source must retain OHLCV for completed, terminated and delisted targets.

> [!warning] Historical boundary
> A reliable historical backtest needs either a prospectively accumulated listing ledger or a genuine point-in-time security master. Re-querying Edgartools or SEC reference JSON today cannot establish what ticker, class, or exchange was knowable on an earlier event date.

[^sec-api]: U.S. SEC, [EDGAR Application Programming Interfaces](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).
[^sec-access]: U.S. SEC, [Accessing EDGAR Data — CIK, ticker, and exchange associations](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).
[^sec-xbrl]: U.S. SEC, [EDGAR XBRL Guide, June 2026](https://www.sec.gov/files/edgar/filer-information/specifications/xbrl-guide-2026-06-29.pdf), sections 3.2.4–3.2.4.4.
[^edgar-submissions]: Edgartools source at commit `0043ee9`, [`parse_entity_submissions`](https://github.com/dgunning/edgartools/blob/0043ee94ec661ed1118fd6cff7fc79d1b067704f/edgar/entity/data.py#L140-L198).
[^edgar-reference]: Edgartools source at commit `0043ee9`, [ticker reference loading](https://github.com/dgunning/edgartools/blob/0043ee94ec661ed1118fd6cff7fc79d1b067704f/edgar/reference/tickers.py#L57-L202) and [live exchange table](https://github.com/dgunning/edgartools/blob/0043ee94ec661ed1118fd6cff7fc79d1b067704f/edgar/reference/tickers.py#L371-L390).
[^edgar-company]: Edgartools source at commit `0043ee9`, [`Company.tickers`, `get_ticker`, and `get_exchanges`](https://github.com/dgunning/edgartools/blob/0043ee94ec661ed1118fd6cff7fc79d1b067704f/edgar/entity/core.py#L570-L607).
[^edgar-primary-ticker]: Edgartools source at commit `0043ee9`, [`get_cik_ticker_lookup` and `find_ticker`](https://github.com/dgunning/edgartools/blob/0043ee94ec661ed1118fd6cff7fc79d1b067704f/edgar/reference/tickers.py#L284-L332).
[^edgar-facts]: Edgartools source at commit `0043ee9`, [`FactsView.get_facts`](https://github.com/dgunning/edgartools/blob/0043ee94ec661ed1118fd6cff7fc79d1b067704f/edgar/xbrl/facts.py#L1035-L1118).
[^edgar-entity-info]: Edgartools source at commit `0043ee9`, [DEI convenience extraction](https://github.com/dgunning/edgartools/blob/0043ee94ec661ed1118fd6cff7fc79d1b067704f/edgar/xbrl/parsers/instance.py#L582-L628).
[^iso-mic]: ISO 10383 Registration Authority, [Market Identifier Codes](https://www.iso20022.org/market-identifier-codes).
[^arelle]: Arelle, [official documentation and supported standards](https://arelle.readthedocs.io/en/latest/).
[^cik-mapper]: `sec-cik-mapper`, [official documentation](https://sec-cik-mapper.readthedocs.io/).
[^sec-downloader]: `sec-edgar-downloader`, [official source repository](https://github.com/jadchaar/sec-edgar-downloader).
[^edgar-market-filings]: Edgartools, [`get_filings` market-wide historical filing API](https://github.com/dgunning/edgartools/blob/main/edgar/docs/Filings.md).
[^edgar-headers]: Edgartools source, [`IndexHeaders.acceptance_datetime` and filing metadata](https://github.com/dgunning/edgartools/blob/main/edgar/headers.py) and [`Filing.full_text_submission`/`attachments`](https://github.com/dgunning/edgartools/blob/main/edgar/_filings.py).
[^sec-indexes]: U.S. SEC, [Accessing EDGAR Data — daily, full and quarterly indexes](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).
