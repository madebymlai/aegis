---
title: DEI Trading-Symbol and Exchange Coverage
date: 2026-07-18
topic: demeter-cash-merger
status: research-note
related:
  - "[[current-fixed-cash-universe-2026-07-17]]"
  - "[[edgartools-listing-identity-resolution-2026-07-18]]"
tags:
  - note
  - demeter
  - merger-arbitrage
  - sec
  - edgartools
---

# DEI Trading-Symbol and Exchange Coverage

> [!abstract] Result
> In the causal periodic-filing sample for all 20 current U.S. fixed-cash targets, Edgartools parsed **28 exact `dei:TradingSymbol` facts and zero lacked `dei:SecurityExchangeName` in the same XBRL `context_ref`**. Missing exchange facts are therefore not an observed blocker for the currently supported XNAS/XNYS universe. The resolver must still represent `Unresolved` because EDGAR does not guarantee this relationship across every filer, form, security type or historical period.

## Method

- Universe: the 20 targets and announcement dates recorded in [[current-fixed-cash-universe-2026-07-17]].
- Library: Edgartools 5.42.0 with SEC identity `m@laimk.dev`.
- For each ticker, select the latest target-owned `10-K` or `10-Q` whose filing date is no later than the recorded announcement date.
- Parse the selected filing with `filing.xbrl()`.
- Select facts by exact concept equality, not Edgartools' partial concept search.
- For every exact `dei:TradingSymbol` fact, require an exact `dei:SecurityExchangeName` fact with the same `context_ref`.

All 20 selected filings parsed successfully. Eighteen filings had one trading-symbol context, DBRG had four, and BHF had six, for 28 contexts total. Every context was paired with an exchange fact.

| Measure | Result |
| --- | ---: |
| Targets | 20 |
| Target-owned periodic filings parsed | 20 |
| Exact `dei:TradingSymbol` facts | 28 |
| Missing same-context `dei:SecurityExchangeName` | **0** |
| Observed missing rate | **0 / 28 = 0%** |

## Regulatory interpretation

The result is consistent with the SEC cover-page model for exchange-listed Section 12(b) securities. The EDGAR XBRL Guide expects `dei:SecurityExchangeName` in the same security context as `dei:Security12bTitle`, and defines the exchange value as an EDGAR national-exchange code such as `NASDAQ`, `NYSE` or `NYSEAMER`.[^sec-guide]

This is not a universal `TradingSymbol -> SecurityExchangeName` guarantee. Valid exceptions include securities registered under Section 12(g), OTC or non-national-exchange securities, ADR-specific contexts, foreign/private targets, unsupported forms and filings without usable Inline XBRL. The correct denominator for Demeter is therefore supported public U.S. Section 12(b) target-security contexts, not every `TradingSymbol` fact in EDGAR.

## Design consequence

Keep the proposed Edgartools-native resolver:

1. Prefer target-owned filing facts available by the decision time.
2. Join security title, trading symbol and exchange by XBRL context and class dimensions.
3. Convert the evidenced SEC exchange code through the Aegis-owned MIC crosswalk.
4. Return `Resolved`, `Ambiguous`, `Unresolved` or `NonPublic`; never guess an exchange.

For the initial XNAS/XNYS strategy scope, the measured coverage supports promotion of this path. A current SEC ticker/exchange map remains only corroborating evidence, not the historical authority.

## Limitations

- This is a directly relevant strategy sample, not an EDGAR-wide census.
- It covers current targets with 2025-2026 causal periodic filings, not older pre-Inline-XBRL history.
- Selection used filing-date cutoffs. Production replay must use the exact SEC acceptance timestamp for intraday causality.
- Coverage does not prove that the transaction affects the first listed class; class matching remains necessary.

[^sec-guide]: U.S. SEC, [EDGAR XBRL Guide, June 2026](https://www.sec.gov/files/edgar/filer-information/specifications/xbrl-guide-2026-06-29.pdf), sections 3.2.4.1-3.2.4.4.
