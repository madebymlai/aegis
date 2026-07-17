---
title: Cat-Bond Return Proxies for Carry Validation
date: 2026-07-12
topic: carry
tags:
  - note
  - carry
  - data
  - validation
---

# Cat-Bond Return Proxies for Carry Validation

> [!abstract] Decision
> Validate the Artemis signal first against a **total-return** series, never raw SHRIX NAV. The preferred market target is the weekly Swiss Re Global Cat Bond Total Return Index (`SRGLTRR`), but no first-party free machine-readable history was found. The practical public fallback is SHRIX total return from February 2013, reconstructed from NAV plus distributions or obtained from a data vendor whose adjusted series explicitly reinvests distributions. Treat SHRIX as an independent active-fund proxy, not as CATB history.

## Recommended validation hierarchy

1. **Swiss Re Global Cat Bond Total Return Index (`SRGLTRR`)** is the cleanest target for the market-level Artemis signal. Swiss Re describes it as the main broad cat-bond total-return index. It is market-value weighted, calculated weekly, based on indicative prices, and represents natural-catastrophe, interest-bearing bonds; zero-coupon and non-natural-cat bonds are excluded.[^swissre2024][^swissre2021]
2. **SHRIX total return** is the best long public realized-fund cross-check. The Stone Ridge High Yield Reinsurance Risk Premium Fund commenced operations on 1 February 2013. Its official performance presentation reinvests dividends, and the current issuer describes the open-end fund as seeking the reinsurance risk premium primarily through catastrophe bonds.[^shrixannual][^shrixissuer]
3. **CATB NAV or executable quote history** remains the implementation check only. HANetf reports a 2 December 2025 inception, active management, USD base currency, accumulating treatment, and a 1.28% TER.[^catb]

Run the same predeclared Artemis rule on both `SRGLTRR` and SHRIX if index access can be obtained. Agreement across the broad index and an independently managed fund is materially stronger evidence than either alone. CATB must not be backfilled with either series.

## SHRIX must be measured as total return

SHRIX distributes substantially all net investment income and realized capital gains at least annually; recent issuer distribution documents show actual cash distributions. A raw NAV-price series therefore contains mechanical ex-distribution drops and materially understates investor return.[^shrixprospectus][^shrixdistributions]

Use one of these constructions, in order:

1. An official or licensed **total-return** series whose methodology explicitly reinvests distributions.
2. Official daily NAV plus official per-share distributions, reconstructed as:

   $$
   r_t = \frac{NAV_t + D_t}{NAV_{t-1}} - 1
   $$

   where $D_t$ is the distribution with ex-date $t$.
3. A vendor-adjusted price series only after verifying that its adjustment includes every income and capital-gain distribution. Preserve the raw NAV and distribution tables beside the adjusted result.

Do not mix issuer-reported calendar returns with a daily or weekly timing test. They are useful for checksum validation but too coarse for 1-, 3-, 6-, and 12-month forward-return analysis.

## What SHRIX can validate

SHRIX is an economically relevant realized proxy: its objective is total return from income and capital preservation, and under normal conditions it invests at least 80% of net assets plus investment borrowings in reinsurance-related securities and at least 80% in high-yield/high-risk debt. Stone Ridge says its construction focuses systematically on expected-return sources rather than security selection or market timing.[^shrixprospectus]

That makes SHRIX useful for testing whether a lagged broad-market richness measure is followed by better realized outcomes in a professionally managed reinsurance portfolio. It is also a meaningful check against an accidental relationship unique to Artemis or Swiss Re indicative marks.

## What SHRIX cannot validate

SHRIX is not a clean CATB substitute:

- **Mandate breadth:** SHRIX may use catastrophe bonds, quota-share notes, industry-loss-warranty notes, derivatives, borrowing, and other reinsurance-related securities. CATB is an actively managed UCITS ETF presented as a diversified cat-bond portfolio.[^shrixprospectus][^catb]
- **Manager and selection basis:** Stone Ridge and King Ridge are different active managers. Any timing result includes their portfolio construction, cash, valuation, and trading decisions.
- **Cost basis:** SHRIX Class I's March 2026 prospectus reports 1.73% total annual operating expenses, including 0.09% borrowing interest, versus CATB's 1.28% TER.[^shrixprospectus][^catb]
- **Liquidity and valuation:** SHRIX is an open-end mutual fund valued at NAV; CATB is an exchange-traded ETF with bid/ask spread, premium/discount, and brokerage costs. Swiss Re's index itself uses indicative prices.[^shrixprospectus][^swissre2024]
- **Distribution policy:** SHRIX distributes income and gains; CATB accumulates them. This is an accounting difference when total return is measured correctly, but a severe error if raw prices are compared.[^shrixprospectus][^catb]
- **Currency and vehicle:** both report USD as the relevant base/share currency, but Demeter executes CATB inside an EUR book and therefore adds EUR/USD translation and exchange execution that SHRIX does not reproduce.

Consequently, SHRIX can validate the **market mechanism and sizing rule**, not CATB tracking quality, attainable execution, or manager-specific expected carry.

## Swiss Re access finding

Swiss Re publishes the index methodology and periodic reports with index descriptions and selected performance values. The methodology identifies `SRGLTRR`, and the reports show that the index is weekly and based on indicative dealer marks.[^swissremethod][^swissre2021] The 2024 report cites Bloomberg ticker `SRGLTRR` alongside other Bloomberg indices.[^swissre2024]

No official Swiss Re CSV, API, or freely downloadable complete observation history was located. Public Swiss Re material is therefore sufficient to establish index validity and methodology, but not to power the backtest reproducibly. Do not digitize chart pixels as the primary dataset. The options are:

1. Retrieve `SRGLTRR` through an already licensed Bloomberg/data entitlement.
2. Request the weekly series from Swiss Re Capital Markets for personal research.
3. Proceed with SHRIX total return as the executable analysis fallback and label the missing independent index replication as a limitation.

## Interpretation boundary

The validation question is narrow:

> Does an Artemis observation available at the decision date predict subsequent **total return** in an independent cat-bond portfolio or index?

It does not ask whether Artemis and the return proxy share the same expected-loss model, whether CATB is presently cheap, or whether the historical best threshold should be deployed. Test fixed positive-net-carry and predeclared richness-sizing rules against always-invested exposure at 1-, 3-, 6-, and 12-month horizons. Apply publication lag, overlapping-return inference, and multiple-horizon correction. Use CATB only for forward tracking and implementation costs.

[^swissre2024]: [Swiss Re, *Insurance-Linked Securities Market Insights, August 2024*, pp. 12–13](https://www.swissre.com/dam/jcr%3A8f99a7ea-1da2-42ca-923f-5063941b0ed2/ils-market-insights-august-2024.pdf)
[^swissre2021]: [Swiss Re, *Insurance-Linked Securities Market Insights, March 2021*, pp. 22–23](https://www.swissre.com/dam/jcr%3Ad731c398-36d8-4663-9ccb-7f11ec7b3985/ils-market-insights-march-2021.pdf)
[^swissremethod]: [Swiss Re, *Cat Bond Indices Methodology*](https://www.swissre.com/dam/jcr%3A307452ca-9664-4772-96f9-7c11f80109b2/2014_08_ils_cat_bond_indices_methodology.pdf)
[^shrixannual]: [SEC, Stone Ridge Trust annual report: SHRIX commencement and reinvested-return convention](https://www.sec.gov/Archives/edgar/data/1559992/000119312520004704/d821117dncsr.htm)
[^shrixissuer]: [Stone Ridge, SHRIX/SHRMX fund page](https://www.stoneridgefunds.com/fund/shrix-shrmx)
[^shrixprospectus]: [Stone Ridge, SHRIX/SHRMX prospectus](https://www.stoneridgefunds.com/documents/shrix-shrmx-prospectus)
[^shrixdistributions]: [Stone Ridge, SHRIX/SHRMX distribution documents](https://www.stoneridgefunds.com/fund/shrix-shrmx)
[^catb]: [HANetf, KRC Cat Bond UCITS ETF](https://hanetf.com/fund/catb-krc-cat-bond-ucits-etf/)
