---
title: Free CATB carry data sources
date: 2026-07-12
status: researched
tags: [cat-bonds, carry, demeter, data]
---

# Free CATB carry data sources

## Decision

Use the **Artemis/Plenum outstanding-market yield series as Demeter's sole external carry
source**. CATB is the executable UCITS vehicle for the broad catastrophe-insurance premium;
the strategy does not claim to estimate King Ridge's exact portfolio carry. HANetf data has
no production dependency.

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

### 1. CATB manager reports — rejected production dependency

The quarterly report is the only free source found that directly publishes CATB's
portfolio expected loss and current spread/yield. Its sparse cadence and lack of historical
observations make it unsuitable as Demeter's production signal.

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

### 4. Artemis market yield — production asset-class signal

The free [cat-bond market-yield
series](https://www.artemis.bm/catastrophe-bond-market-yield/) decomposes outstanding-market
yield into collateral yield, insurance spread and expected loss. Demeter deliberately uses
this as an asset-class signal and implements the resulting exposure through CATB; it does
not label the observation CATB-specific.

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

## Historical observations found

CATB itself has no earlier full-quarter history to recover: HANetf gives an inception date
of 2 December 2025, and its report as of 31 March 2026 is therefore the fund's first full
calendar quarter. HANetf retains monthly CATB factsheets from November/December 2025 onward,
but those PDFs publish holdings, NAV and descriptive fund data rather than portfolio spread
and modelled expected loss. They cannot extend the CATB-specific richness signal.

The clean free historical calibration source is the **Twelve Cat Bond Fund monthly report
archive** on Swiss Fund Data. Its reports expose discount margin or spread, modelled
expected loss, excess spread, average coupon, maturity, loss bands, peril contributions and
stress tests. Examples found include:

- 30 June 2022: spread at issuance 5.69%, expected loss 2.16%, excess spread 3.53%,
  implying a 2.63x spread/EL multiple.
- 28 February 2025: discount margin 4.51%, expected loss 1.72%, excess spread 2.79%,
  implying a 2.62x multiple.
- 31 May 2025: discount margin 5.50%, expected loss 1.67%, excess spread 3.83%,
  implying a 3.29x multiple.

This archive is suitable for setting defensible prior ranges and testing whether a
spread/EL sizing curve is sensible across market regimes. It is not CATB's portfolio and
must not be spliced into CATB's live signal or presented as CATB backtest history.

## Recommended Demeter data contract

1. Refresh the public Artemis outstanding-market series on each Run.
2. Store validated observations as immutable content-addressed runtime-cache entries; reuse
   the newest valid entry during a temporary outage and fail a cacheless offline cold start.
3. Compute total net carry as collateral yield plus insurance spread minus expected loss and
   CATB's fund fee.
4. Compute catastrophe-risk compensation as insurance spread divided by expected loss.
5. Apply a conservative publication lag and reject stale observations.
6. Emit a fully invested one-name CATB sleeve only when market carry qualifies.
7. Leave all commingled-book sizing to Aegis Trader's Allocator.

## Consequence for the current implementation

The HANetf holdings fetch, manager-report parser, tranche matching and coverage reporting are
removed. Demeter now claims broad cat-bond market carry implemented through CATB, not exact
CATB portfolio richness.
