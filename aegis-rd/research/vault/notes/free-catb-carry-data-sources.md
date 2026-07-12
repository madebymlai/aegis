---
title: Free CATB carry data sources
date: 2026-07-12
status: researched
tags: [cat-bonds, carry, demeter, data]
---

# Free CATB carry data sources

## Decision

Use **HANetf/King Ridge's CATB manager reports as the authoritative portfolio-level
carry source**. Use HANetf's daily holdings for concentration and implementation
monitoring. Keep Artemis market data as market context and the Artemis Deal Directory as
an audit/enrichment source, not as the primary estimator of CATB expected loss.

This removes the need to reach 80% bond-by-bond expected-loss coverage before CATB carry
can be measured. A manager-published portfolio statistic covers the managed portfolio as
a whole.

## The source we missed

HANetf's free [Cat Bond Quarterly Report | April
2026](https://hanetf.com/monthly-reports/cat-bond-quarterly-report-april-2026/) reports,
as of 31 March 2026:

- Weighted average coupon: **13.0%**
- Weighted average yield to maturity: **9.3%**
- Net spread over risk-free collateral: **6.0%**
- Modelled weighted average expected loss: **2.8%**
- Weighted average maturity: **1.74 years**
- Expected-loss-band weights and historical-event stress impacts

The report says coupon and expected-loss figures come from the underlying 144A documents
for every constituent. Yield and spread use blended Bloomberg, Swiss Re and broker
pricing; stress tests use Verisk. This is the exact CATB portfolio, not a proxy fund or a
market average.

At that observation:

\[
\text{spread/EL multiple} = 6.0 / 2.8 = 2.14
\]

\[
\text{insurance premium after modelled loss} = 6.0 - 2.8 = 3.2\%
\]

A rough fee-adjusted expected total carry is `9.3 - 2.8 - 1.28 = 5.22%`, but this must be
labelled an estimate: the report warns that yield is a portfolio characteristic rather
than realised performance, and its phrase "shown on a net basis" needs clarification
before assuming whether the 1.28% TER is already reflected.

## Source hierarchy

### 1. CATB manager reports — primary signal

The quarterly report is the only free source found that directly publishes CATB's
portfolio expected loss and current spread/yield. Cache each report by publication time
and use the statistics only from the following decision date.

Limitation: only one CATB quarterly report was discoverable so far. This provides a real
31 March observation, not a continuous history or a time-series timing model.

### 2. HANetf daily holdings — exposure monitoring

The [CATB fund page](https://hanetf.com/fund/catb-cat-bond-etf/) and downloadable XLSX
provide daily identities, quantities, weights, ISINs, displayed rates, market values and
maturities. The prospectus supplement says holdings are disclosed each business day using
prior-close positions and completed trades.

Use these for:

- Cash, sponsor and position concentration
- Weighted maturity
- Portfolio turnover and holdings changes
- Identifying triggered or extended bonds
- Auditing whether the quarterly aggregate remains representative

Do not infer a current modelled expected loss solely from these fields.

### 3. Artemis Deal Directory — free tranche audit/enrichment

The [Artemis Deal Directory](https://www.artemis.bm/deal-directory/) contains more than
1,000 transactions and exposes issuer, sponsor, peril, trigger and date. Individual deal
pages commonly provide class-level initial expected loss, attachment probability and
final spread. Its sitemap makes transactions discoverable.

Use it to explain CATB risk and cross-check manager statistics. No documented official
bulk API or complete CSV export was found, so it should not be the load-bearing live feed.
Expected loss is also usually the issuance estimate rather than a current manager model.

### 4. Artemis market yield — regime context only

The free [cat-bond market-yield
series](https://www.artemis.bm/catastrophe-bond-market-yield/) decomposes market yield
into collateral yield, insurance spread and expected loss. It is useful for whether the
overall market is rich or cheap, but it is not CATB-specific.

### 5. Free research and comparator data — validation only

- The OpenICPSR [Economic Catastrophe Bonds replication
  dataset](https://doi.org/10.3886/E113301V1) includes a downloadable `masterDATA.csv`.
  It is useful for historical cross-sectional calibration but predates CATB and cannot
  describe its current portfolio.
- Plenum publishes free [CAT Bond UCITS Fund index data and
  methodology](https://www.plenum.ch/index/), including risk grouping by expected loss
  and VaR. It is a fund-family benchmark, not CATB look-through data.
- Franklin Templeton's free cat-bond fund factsheet publishes portfolio spread, expected
  loss, yield, maturity, VaR and expected-loss contribution by peril. It demonstrates the
  correct reporting shape and supplies a comparator, but its portfolio is not CATB.
- World Bank cat-bond prospectuses and case studies publish excellent first-party risk
  statistics for IBRD tranches. They cover only the sovereign/IBRD subset.

## What is not freely available

No clean free source was found for daily CATB portfolio expected loss, current
bond-by-bond discount margins, or CATB's live Verisk loss model. HANetf's report explicitly
uses Bloomberg, Swiss Re, brokers and Verisk for those calculations.

OpenFIGI can freely map CATB ISINs to FIGIs, and FINRA TRACE may provide some reported
transactions, but identifiers and trades do not supply modelled expected loss. Cat bonds
are also OTC and TRACE coverage is not a complete portfolio valuation source.

## Recommended Demeter data contract

1. Dynamically cache HANetf daily holdings.
2. Dynamically discover and cache each CATB manager report.
3. Treat manager-report `yield`, `spread`, `expected_loss`, `maturity`, and EL-band weights
   as authoritative report observations with 100% portfolio coverage.
4. Compute `spread / expected_loss` and `spread - expected_loss` without reconstructing
   bond-level EL.
5. Use Artemis aggregate richness only as a separate market-regime observation.
6. Between manager reports, carry forward the latest report with explicit age; do not
   pretend the portfolio EL updates daily.
7. Ask HANetf whether future quarterly reports will retain the same fields and whether TER
   is already embedded in the reported 9.3% yield before defining net expected carry.

## Consequence for the current implementation

The 80% tranche-match gate and its bond-match report solve the wrong problem and are
removed. The primary portfolio signal begins from the report published 1 May 2026, using
its 31 March data without look-ahead.
