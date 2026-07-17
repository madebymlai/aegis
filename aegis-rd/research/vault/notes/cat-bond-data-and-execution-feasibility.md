---
title: Cat-Bond Data and Execution Feasibility
date: 2026-07-12
topic: carry
tags:
  - note
  - carry
  - data
---

# Cat-Bond Data and Execution Feasibility

> [!abstract] Decision
> The cat-bond redesign is testable now as a research proxy but not yet as one continuous executable instrument. Use a Plenum weekly NAV stream for historical mechanism research and `C47B` as the only eligible small-account execution vehicle. Do not splice the ETF backward or present Plenum performance as the ETF's track record.

## Question and pre-search prior

The search had to settle three implementation questions: whether a point-in-time 2020-2026 UCITS cat-bond return series exists, whether an established fund can be bought at the book's size and cadence, and whether a listed vehicle is already executable through IBKR. The prior was that established funds would supply the history but fail the retail ticket-size constraint, while the new ETF would solve execution but lack history. Evidence against that prior would have been an established, retail-sized share class with downloadable NAV history or a listed vehicle spanning the full window.

The searches used the available web search because Exa was not exposed in either session. The final vehicle comparison was repeated on 12 July against current issuer, regulator, exchange, prospectus, KID, and fund-report sources.

## Historical series found

Plenum publishes a family of weekly total-return indices intended to represent all UCITS funds that invest directly and fully in catastrophe bonds. The indices use accumulating and generally currency-hedged share classes, with fund prices taken from share-class NAVs. Master indices are available in USD, EUR, and CHF in equal- and capital-weighted forms; low- and high-risk sub-indices are also published.[^plenum]

The official Plenum page offers pre-2022 history and live data from 2022 as downloadable files, but access is gated by a contact form requiring a name, corporate email, telephone number, and company. No request was submitted because that would contact an external party on the user's behalf.[^plenumform]

Artemis mirrors the Plenum series openly. Its page embeds dated master average and capital-weighted USD observations from January 2011 through 26 June 2026. The 2020-2021 segment is monthly and the segment from 31 December 2021 is weekly. This is enough for a weekly or monthly research test covering the required window, but the embedded dates contain at least two obvious transcription errors (`12/01/20204`, `19/01/20204`) and one likely date error (`16/09/2025` between 9 May and 23 May 2025). Any ingestion must correct only mechanically identifiable date typos, preserve raw values, and record the transformations.[^artemis]

The preferred series for the EUR book is Plenum Master EUR Average, ISIN `CH1208860473`, Bloomberg `PLCBFEA`; the capital-weighted counterpart is `CH1208860440` / `PLCBFEC`. Artemis exposes only the USD versions, so obtaining the official EUR file is preferable to converting the USD index after the fact.[^plenum][^artemis]

## Established funds are not small-ticket execution vehicles

Schroder GAIA Cat Bond is the cleanest fully documented established fund. Its USD A accumulation class, ISIN `LU2049314961`, launched 27 September 2019 and has a USD 100,000 minimum initial subscription, 1.77% ongoing charge, and dealing on the second and fourth Friday plus the final business day of each month. Subscriptions require three days' notice and redemptions seven days. Its factsheet reports net calendar returns of 4.8% in 2020, 2.8% in 2021, -3.3% in 2022, 16.0% in 2023, 12.9% in 2024, and 9.1% in 2025.[^schroder]

Twelve Cat Bond Fund is an established weekly-dealing UCITS fund, but the available institutional share classes do not solve the small-account problem. Its official supplement confirms the UCITS structure and weekly dealing convention, while the public identifiers include USD accumulation class `IE00BD2B9264`. The fund is useful as an index constituent and institutional reference, not as the current EUR 5,000 execution line.[^twelve]

The related Securis Catastrophe Bond Fund makes the ticket-size constraint explicit. New receiving classes begin at USD 25,000 for P/P2 and rise to USD 100,000, USD 500,000, or USD 1 million for other classes; older A-H classes are closed to new investment. Its history can inform the index but it is not a practical Demeter holding.[^securis]

## Listed execution exists, but history does not

KRC Cat Bond UCITS ETF, ISIN `IE000UWJUW87`, is the one listed UCITS implementation. HANetf reports inception on 2 December 2025, TER 1.28%, accumulating treatment, daily liquidity, and listings in EUR on Xetra (`C47B`) and Borsa Italiana (`CATB`), USD on LSE (`CATB`), and GBP on LSE (`ILS`). Fund assets were about USD 14.0 million on 9 July 2026.[^hanetf]

The Gateway resolves the EUR listing as conId `836127700`, local symbol `C47B`, primary exchange `IBIS2`, SMART-routable across Xetra, Frankfurt, Borsa Italiana, Gettex, and Tradeweb. A non-transmitting one-share What-If market order returned `PreSubmitted` with no warning and an estimated EUR 4 commission. The LSE USD line is conId `845305944`, but its history begins on the LSE listing date, 13 January 2026. This establishes an executable vehicle, not a usable 2020-2026 backtest.[[2026-07-04#P3 - cat-bond concave pole: data-blocked on IBKR (deferred)]]

`C47B` is USD-base and the EUR exchange quote does not hedge EUR/USD. It is also a small new fund. A policy change effective in May 2026 removed the former 10% limit on catastrophe bonds tied to non-natural events, so cyber, aviation, and other event risks may enter without a dedicated cap. Historical Plenum natural-cat performance therefore has both manager basis and peril-universe basis against the executable ETF.[^hanetfpolicy]

## Why the established Plenum fund is not the live asset

Plenum Cat Bond Defensive Fund R EUR, ISIN `LI0115208543`, is the strongest historical single-fund candidate. Its current prospectus specifies one share or EUR 100 minimum, Friday valuation, weekly issue and redemption at NAV, accumulating income, and a maximum 1.75% management fee. The EUR class can be fully or partially currency-hedged, but full hedging is not guaranteed by the contract.[^plenumfund]

IBKR resolves it as conId `841522557`, symbol `PCAE`, primary exchange `EBS`. A frozen broker quote was EUR 133.10 bid and EUR 134.16 ask, roughly 80 basis points full spread. More importantly, a non-transmitting one-share What-If order was rejected with `No Trading Permission, Customer Ineligible: No Opening Trades: Open-End Fund on European Exchange`. It is therefore a research stream, not an executable Demeter asset on the connected account.

## Current retail-access universe

The July 12 sweep found only one European exchange-traded cat-bond vehicle: `C47B`. HANetf calls it Europe's first cat-bond UCITS ETF and lists the same share class on Xetra, Borsa Italiana, and the LSE.[^hanetflaunch] No current European closed-end cat-bond fund, investment trust, or separate cat-bond ETP survived the search. The present LSE cat-bond fund listing is the HANetf ETF.[^lse]

The remaining candidates are conventional open-end UCITS funds. A fund can appear on an exchange or broker quote page without becoming an ETF. Plenum's legal prospectus says `Listing: no`, even though Plenum offers secondary daily trading through the SIX Sponsored Funds segment.[^plenumfund][^plenumsix] IBKR consequently classifies `PCAE` as an open-end European fund and rejects opening trades with i146. Every conventional fund below should be assumed susceptible to the same restriction until a non-transmitting Gateway What-If order proves otherwise.

### Exchange-traded instruments

| Instrument | Identifiers and venue | Structure | Retail ticket | Costs and size | History and decision |
|---|---|---|---|---|---|
| KRC Cat Bond UCITS ETF | `IE000UWJUW87`; Xetra `C47B` EUR, Borsa Italiana `CATB` EUR, LSE `CATB` USD / `ILS` GBP | Irish open-end UCITS ETF, accumulating, USD base, not EUR-hedged | One share; Gateway What-If accepted | TER 1.28%; USD 14.0m NAV on 9 July 2026 | Inception 2 December 2025. Only executable European small-account candidate; no defensible 2020-2026 self-history.[^hanetf] |
| Brookmont Catastrophic Bond ETF | US ticker `ILS`, NYSE Arca; CUSIP `26923N470` | US 1940 Act ETF, primarily natural-cat bonds | Exchange unit if permitted | Issuer presents daily trading; current fee and AUM require US prospectus verification | Not a European UCITS/PRIIPs product. Plausible IBKR contract lookup, but an EU retail opening trade is expected to be blocked for missing PRIIPs KID.[^brookmont] |

### Conventional open-end funds

| Fund or retail-facing class | Identifier | Verified shape | Small-book assessment |
|---|---|---|---|
| Plenum Cat Bond Defensive R EUR | `LI0115208543`, broker symbol `PCAE`, SIX Sponsored Funds / `EBS` | Liechtenstein UCITS; inception 6 September 2010; one share or EUR 100; weekly Friday NAV; R EUR TER 1.72% at 30 June 2025; total fund assets USD 532.4m; EUR currency risk may be fully or partially hedged | Fits EUR 5,000 economically, but Gateway What-If already failed i146. Historical research stream only.[^plenumreport] |
| GAM Swiss Re Cat Bond Ordinary Acc EUR | `IE00B6S4V579`; an income EUR class also appears as `IE00B52P3X14` | Irish UCITS, launched as GAM Star Cat Bond in 2011; co-managed with Swiss Re from May 2025 and renamed GAM Swiss Re Cat Bond in June 2026 | Retail distribution evidence exists, but it remains an open-end fund. Exact minimum, charge, and IBKR eligibility require KID plus What-If verification.[^gam] |
| Franklin Cat Bond UCITS W Acc USD | `LU3047210656` | Luxembourg UCITS; EUR 1,000 minimum; USD accumulating; 1.09% ongoing charge; USD 271.9m at 31 May 2026; legal vehicle and class inception 1 August 2025 with predecessor W history from 21 July 2023 | Nominally small-ticket and the strongest overlooked mutual-fund contract candidate. It adds EUR/USD risk and is likely i146-blocked. No retail EUR-hedged class found.[^franklin] |
| Twelve Cat Bond B Acc EUR | `IE00BD2B9603` | Irish UCITS; weekly NAV; EUR accumulating; EUR 10,000 minimum; share-class inception 5 June 2020; temporary capacity soft-close announced April 2025 | Above the EUR 5,000 book before broker eligibility. Research comparator, not a live candidate.[^twelveretail] |
| AXA IM WAVe Cat Bonds | A-class examples include `IE00BF0MWX70`; I USD `IE00BZCPNB98` | Irish UCITS; issuer pages show A, I, and J share families; the verified I class minimum is USD 1m | No primary-source-verified class at or below EUR 5,000 emerged. Open-end and likely i146 even where a distributor waives minimums.[^axa] |
| Other direct cat-bond UCITS peers | Multiple share classes | GAM, LGT, Schroder, Tenax, Leadenhall, Securis, Solidum, Icosa, Maneki, Euler, and Fermat. Verified examples include LGT B2 EUR `LU0816333396` at EUR 500,000, Schroder A USD `LU2049314961` at USD 100,000, and Securis receiving classes from USD 25,000 | Institutional or distributor-dependent. Keep as benchmark constituents, not Demeter contracts.[^lgt][^schroder][^securis] |

The peer screen was anchored on the Plenum UCITS Cat Bond Fund Index constituents, which cover direct and substantially full cat-bond UCITS portfolios.[^plenum] Product renames and manager transitions mean names are not stable identifiers. Exact ISINs, legal structure, and current KIDs matter more than brand labels.

## IBKR live-verification shortlist

Run contract-details lookup and a one-share or minimum-unit non-transmitting What-If in this order:

1. `IE000UWJUW87`, `C47B`, primary `IBIS2`, conId `836127700`. Already eligible. Recheck live bid, ask, depth, and commission after resolving the competing-session market-data problem.
2. `LU3047210656`, Franklin W Acc USD. This is the only newly found conventional class with a verified EUR 1,000 minimum. Expect an open-end-fund or PRIIPs eligibility rejection, but verify rather than infer.
3. `IE00B6S4V579`, GAM Swiss Re Cat Bond Ordinary Acc EUR, then `IE00B52P3X14` for the income EUR class. Retrieve contract structure and minimum before What-If. Expect i146 if IBKR models them as European open-end funds.
4. `IE00BD2B9603`, Twelve B Acc EUR. Verify contract metadata only; the EUR 10,000 product minimum already disqualifies it for this book.
5. US `ILS`, NYSE Arca, CUSIP `26923N470`. Verify only to document the expected EU-retail PRIIPs block. It is not a UCITS fallback.

Do not spend further Gateway cycles on `PCAE` unless account permissions change. ConId `841522557` has already reproduced i146.

## Recommended research contract

Use the historical fund index and executable ETF as two explicitly different objects:

1. Research return stream: official Plenum Master EUR Average weekly total return, preferably the manager file rather than the Artemis mirror.
2. Execution candidate: `C47B` in EUR. Eligibility is confirmed; live spread and depth remain a promotion prerequisite because the current account lacks the Xetra top-of-book subscription and a competing session prevented a clean snapshot.
3. Frequency: evaluate and rebalance monthly; never fabricate daily observations from weekly NAVs.
4. Costs: the historical index is net of constituent fund fees but does not contain the ETF's 1.28% TER, exchange spread, or execution costs. Apply an explicit ETF implementation-drag sensitivity rather than claiming identity.
5. Promotion boundary: the proxy can establish whether the cat-bond mechanism improves the floor. It cannot establish that the new ETF captures the same portfolio, marks, capacity, peril universe, currency exposure, or manager skill. `C47B` begins as a small live pilot or challenger, never as a proxy-backfilled champion.

> [!warning] Remaining authorization boundary
> The strongest next step is to request the official EUR index history from Plenum. The form requires personal and company contact details, so it must be submitted by the user or with explicit authorization and supplied details.

## Sources

[^plenum]: Plenum Investments, "Plenum CAT Bond UCITS Fund Indices," official index description and identifiers, accessed 11 July 2026. Weekly total-return indices from accumulating, generally hedged UCITS fund NAVs; includes master EUR Average `CH1208860473` / `PLCBFEA` and EUR Capital `CH1208860440` / `PLCBFEC`. Plenum also manages cat-bond funds, so it has a product conflict of interest. https://www.plenum.ch/index/

[^plenumform]: Plenum Investments, "Download Formular," accessed 11 July 2026. Offers index history through 31 December 2021 and live Excel data from 1 January 2022, conditional on corporate contact details. https://www.plenum.ch/index/download-formular/

[^artemis]: Artemis, "Catastrophe Bond Fund Indices - UCITS," accessed 11 July 2026. Open mirror of Plenum master USD indices from January 2011 through June 2026, with weekly live observations from end-2021; page source exposes dates and values. Specialist industry publisher, not the index owner. https://www.artemis.bm/catastrophe-bond-fund-indices/

[^schroder]: Schroders, "Schroder GAIA Cat Bond A Accumulation USD," factsheet dated May 2026. ISIN `LU2049314961`; USD 100,000 minimum, 1.77% ongoing charge, fortnightly-plus-month-end dealing, T-3 subscription and T-7 redemption notice. Issuer source with direct product conflict. https://api.schroders.com/document-store/GAIACAT-Schroder-GAIA-Cat-Bond-A-Acc-FMR-IEEN.pdf

[^twelve]: Twelve Capital UCITS ICAV, "Twelve Cat Bond Fund Supplement," 9 October 2025. Official legal supplement confirming UCITS structure, USD base currency, and weekly dealing convention. Issuer source with direct product conflict. https://securisinvestments.com/download/6086/

[^securis]: Twelve Securis, "Securis Catastrophe Bond Fund," March 2026 factsheet and share-class pages. New receiving-class minimums start at USD 25,000; older receiving classes are closed. Issuer source with direct product conflict. https://securisinvestments.com/ucits/

[^hanetf]: HANetf, "KRC Cat Bond UCITS ETF," accessed 11 July 2026. ISIN `IE000UWJUW87`; inception 2 December 2025; TER 1.28%; accumulating; Xetra, Borsa Italiana, and LSE listings; about USD 14.0 million NAV on 9 July 2026. Issuer source with direct product conflict. https://hanetf.com/fund/catb-cat-bond-etf/

[^hanetfpolicy]: HANetf II ICAV, "Change of the Investment Policy - KRC Cat Bond UCITS ETF," shareholder notice dated 16 April 2026. Removes the 10% cap on non-natural-event catastrophe bonds; issuer legal notice. https://storage.pardot.com/882763/1776338703Ajp3jHw3/KRC_Cat_Bond_UCITS_ETF___Shareholder_Notice___dated_16_April_2026.docx.pdf

[^plenumfund]: CAIAC Fund Management, "Plenum CAT Bond Defensive Fund Prospectus and Trust Agreement," 20 March 2025. R EUR `LI0115208543`; one share or EUR 100 minimum, weekly Friday NAV dealing, accumulating, maximum 1.75% portfolio-management fee; currency classes may be fully or partially hedged. Official legal document. https://www.swissfunddata.ch/sfdpub/docs/fpd-2176-20250320-en.pdf

[^hanetflaunch]: HANetf, "HANetf and King Ridge Capital launch Europe's first catastrophe bond ETF on London Stock Exchange," January 2026. Confirms the ETF structure and LSE, Xetra, and Borsa Italiana listings. Issuer source with direct product conflict. https://hanetf.com/press-releases/53038/

[^lse]: Artemis, "King Ridge brings ILS funds back to London Stock Exchange as Cat Bond UCITS ETF lists," 14 January 2026. Specialist secondary source used only to check the current listed-fund landscape. https://www.artemis.bm/news/king-ridge-brings-ils-funds-back-to-london-stock-exchange-as-cat-bond-ucits-etf-lists/

[^plenumsix]: Plenum Investments, "Company," accessed 12 July 2026. States that its cat-bond funds have daily liquidity through the SIX Sponsored Fund Segment. Issuer source; this secondary facility does not override the prospectus classification or IBKR i146 result. https://www.plenum.ch/en/firm/

[^plenumreport]: CAIAC Fund Management, "Plenum CAT Bond Defensive Fund Semi-Annual Report," 30 June 2025. Reports USD 532.4 million total net assets, 1.72% R-class TER, class assets, and EUR/USD forward positions. Official fund report. https://www.swissfunddata.ch/sfdpub/docs/sar-2176-20250630-en.pdf

[^brookmont]: Brookmont Capital Management, "Brookmont Catastrophic Bond ETF," accessed 12 July 2026. NYSE Arca ticker `ILS`, CUSIP `26923N470`, daily-traded US ETF focused primarily on natural-disaster cat bonds. Issuer source with direct product conflict. https://ilsetf.com/

[^gam]: GAM Investments, "GAM Swiss Re Cat Bond," accessed 12 July 2026; and GAM, "GAM adds to its UCITS offering with cat bond fund launch," 7 November 2011. Confirms current UCITS status, the Swiss Re partnership, and original fund launch. Issuer sources with direct product conflict. https://www.gam.com/en/funds/featured-funds/gam-swiss-re-cat-bond and https://www.gam.com/en/news-articles/press-releases/corporate/gam-adds-to-its-ucits-offering-with-cat-bond-fund-launch-november-2011

[^franklin]: Franklin Templeton, "Franklin Cat Bond UCITS Fund W (acc) USD," accessed 12 July 2026. `LU3047210656`; EUR 1,000 minimum, 1.09% ongoing charge, USD 271.9 million total fund assets at 31 May 2026, and predecessor-history disclosure. Issuer source with direct product conflict. https://www.franklintempleton.lu/our-funds/price-and-performance/products/42012/BC/

[^twelveretail]: Fundsquare, "Twelve Capital Cat Bond Fund B ACC EUR," and Twelve Capital UCITS ICAV fund documents. `IE00BD2B9603`, weekly accumulating EUR class; public fund data identifies 5 June 2020 inception and EUR 10,000 minimum. Fundsquare is market infrastructure but not the issuer. https://www.fundsquare.net/security/summary?idInstr=367465

[^axa]: AXA Investment Managers, "AXA IM WAVe Cat Bonds Fund," current share-class pages; and Raiffeisen fund distribution data for I USD `IE00BZCPNB98`, which reports a USD 1 million minimum. Issuer source establishes the current product; distributor source supplies the class minimum. https://funds.axa-im.com/en/fund/axa-im-wave-cat-bonds-fund-j-h-accumulation-eur/ and https://investice.rb.cz/en/produkt/fund/?ID_NOTATION=392175387&ISIN=IE00BZCPNB98

[^lgt]: LGT, "LGT (Lux) I Prospectus," 21 May 2026, and current B2 EUR product data. The prospectus establishes institutional minimums; B2 EUR `LU0816333396` is reported at EUR 500,000. Official prospectus: https://dl.avl-investmentfonds.de/fds/LU2168313570-VERKPROSP-EN-20260521.pdf
