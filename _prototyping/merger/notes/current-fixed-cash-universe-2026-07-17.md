---
title: Current Fixed-Cash Merger Universe — 2026-07-17
date: 2026-07-17
topic: demeter-cash-merger
status: research-note
related:
  - "[[demeter-current-cash-merger-universe]]"
  - "[[finding-a-buildable-convergent-engine]]"
  - "[[the-tiered-strategy-roster]]"
tags:
  - note
  - demeter
  - merger-arbitrage
  - instruments
  - sec
---

# Current Fixed-Cash Merger Universe — 2026-07-17

> [!abstract] Decision
> Use the 20 exact InstrumentIds below as the **current fixed-cash research universe**. The prior 14 names remain pending. Add the six IBKR-validated names `DSGR.XNAS`, `CRNX.XNAS`, `APGE.XNAS`, `TECH.XNAS`, `BHF.XNAS`, and `EA.XNAS`. Demote `TXNM.XNYS` from the conditional tier because its New Mexico regulatory state has materially worsened.

This is a current prospective universe, not a historical backtest universe. Primary SEC or issuer evidence was checked after a broad-to-narrow Exa search on 2026-07-17. A deal's presence here establishes a fixed-cash endpoint and a pending process; it does not establish positive expected net payoff. The indicator must still reject unattractive spreads.

## Discovery method and coverage boundary

Broad discovery used three Exa query families: current or pending U.S.-listed cash mergers, 2026 acquisition announcements and merger-arbitrage trackers, and current-status or completion checks for tracker-seeded tickers. Narrow verification then searched each company and ticker for its cash offer and latest lifecycle state, and admitted a name only from SEC or issuer evidence. Forms reviewed included `8-K`, `DEFM14A`/`PREM14A`, `DEFA14A`, `SC 14D-9/A`, and `6-K` where relevant.

The named audit set contained 50 tickers. Exa and tracker results were discovery seeds only, and a secondary status was never allowed to override a current primary filing.

| Screening result | Count | Tickers |
| --- | ---: | --- |
| Accepted pending fixed-cash endpoint | 20 | `CCO`, `LPRO`, `PAYO`, `KORE`, `GBTG`, `CCRN`, `OGN`, `AES`, `DBRG`, `IMXI`, `SLP`, `AVNS`, `ALOT`, `RAMP`, `DSGR`, `CRNX`, `APGE`, `TECH`, `BHF`, `EA` |
| Excluded or watchlisted for payoff, status, or source complexity | 12 | `TXNM`, `PERF`, `WBD`, `CZR`, `TBPH`, `ATAI`, `ESPR`, `UNF`, `AFBI`, `GNK`, `TWO`, `ZIM` |
| Stale or unsupported old-note candidate | 3 | `TALK`, `NSTS`, `SILA` |
| Completed tracker seed | 15 | `NUVL`, `WSR`, `EEX`, `TBRG`, `CPRX`, `KALV`, `CSGS`, `EHAB`, `RAPT`, `DVAX`, `TPH`, `EWCZ`, `TERN`, `CNTA`, `XOMA` |

This is a researched current candidate set, not an exhaustive U.S. merger-market census. The exact raw Exa result pages were not retained, so `20/50` is the coverage of the named audit set—not a market-wide recall estimate. Historical or exhaustive coverage requires a persisted discovery ledger with timestamped queries, every screened candidate, and deterministic deduplication rules.

## Exact recommended InstrumentIds

```yaml
instruments:
  - CCO.XNYS
  - LPRO.XNAS
  - PAYO.XNAS
  - KORE.XNYS
  - GBTG.XNYS
  - CCRN.XNAS
  - OGN.XNYS
  - AES.XNYS
  - DBRG.XNYS
  - IMXI.XNAS
  - SLP.XNAS
  - AVNS.XNYS
  - ALOT.XNAS
  - RAMP.XNYS
  - DSGR.XNAS
  - CRNX.XNAS
  - APGE.XNAS
  - TECH.XNAS
  - BHF.XNAS
  - EA.XNAS
```

All 20 names were qualified through the local IBKR paper Gateway on 2026-07-17. Each resolved as a USD U.S.-listed common stock, and a one-share buy-limit `whatIf` at the cash offer returned `PreSubmitted` without an order error. Their prices do not justify an arbitrary exclusion: even one `$210` EA share is only about `4.2%` of a €5,000 book before FX conversion, while the other additions require less capital per share.

| InstrumentId | IBKR `conId` | One-share `whatIf` |
| --- | ---: | --- |
| `CCO.XNYS` | `362175385` | `PreSubmitted` |
| `LPRO.XNAS` | `426545710` | `PreSubmitted` |
| `PAYO.XNAS` | `499621117` | `PreSubmitted` |
| `KORE.XNYS` | `712118325` | `PreSubmitted` |
| `GBTG.XNYS` | `564354641` | `PreSubmitted` |
| `CCRN.XNAS` | `13608169` | `PreSubmitted` |
| `OGN.XNYS` | `490414355` | `PreSubmitted` |
| `AES.XNYS` | `2560358` | `PreSubmitted` |
| `DBRG.XNYS` | `578327143` | `PreSubmitted` |
| `IMXI.XNAS` | `327709672` | `PreSubmitted` |
| `SLP.XNAS` | `28174576` | `PreSubmitted` |
| `AVNS.XNYS` | `321325546` | `PreSubmitted` |
| `ALOT.XNAS` | `266058` | `PreSubmitted` |
| `RAMP.XNYS` | `335460283` | `PreSubmitted` |
| `DSGR.XNAS` | `271109` | `PreSubmitted` |
| `CRNX.XNAS` | `326089330` | `PreSubmitted` |
| `APGE.XNAS` | `641851449` | `PreSubmitted` |
| `TECH.XNAS` | `172729810` | `PreSubmitted` |
| `BHF.XNAS` | `282563276` | `PreSubmitted` |
| `EA.XNAS` | `268995` | `PreSubmitted` |

## Primary-source evidence

### Reconfirmed prior core

| InstrumentId | Cash/share | Announced | Latest verified lifecycle state as of 2026-07-17 | Primary evidence |
| --- | ---: | --- | --- | --- |
| `CCO.XNYS` | `$2.43` | 2026-02-09 | Shareholder-approved; regulatory review remains and Q3 close was guided. | [Shareholder-vote 8-K, accession `0001213900-26-055090`](https://www.sec.gov/Archives/edgar/data/1334978/0001213900-26-055090-index.html); [definitive proxy](https://www.sec.gov/Archives/edgar/data/1334978/000121390026042721/ea0283916-02.htm) |
| `LPRO.XNAS` | `$3.15` | 2026-06-15 | Tender pending; scheduled to expire 2026-07-27. The agreement has an October 15 outside date and a possible regulatory extension to December 15. | [Schedule 14D-9, accession `0001193125-26-286952`](https://www.sec.gov/Archives/edgar/data/1806201/000119312526286952/d140679dsc14d9.htm); [announcement 8-K](https://www.sec.gov/Archives/edgar/data/1806201/000119312526271902/d147981d8k.htm) |
| `PAYO.XNAS` | `$7.40` | 2026-06-15 | Solicitation remains active; closing is guided for mid-2027. | [Latest July solicitation filing, accession `0000950103-26-010366`](https://www.sec.gov/Archives/edgar/data/1845815/0000950103-26-010366-index.html); [announcement 8-K](https://www.sec.gov/Archives/edgar/data/1845815/000095010326008945/dp248400_8k.htm) |
| `KORE.XNYS` | `$9.25` | 2026-02-26 | The special meeting was scheduled for 2026-07-16, but no primary vote-results filing was available at the evidence cutoff; retain the deal as pending rather than inferring approval. | [Latest available transaction 8-K, accession `0001140361-26-028120`](https://www.sec.gov/Archives/edgar/data/1855457/000114036126028120/ef20077619_8k.htm); [definitive proxy](https://www.sec.gov/Archives/edgar/data/1855457/000114036126025086/ny20068726x6_defm14a.htm) |
| `GBTG.XNYS` | `$9.50` | 2026-05-02 | Vote scheduled for 2026-08-03; transaction remains pending. | [Definitive proxy, accession `0001140361-26-027649`](https://www.sec.gov/Archives/edgar/data/1820872/000114036126027649/ny20072693x2_defm14a.htm) |
| `CCRN.XNAS` | `$13.25` | 2026-05-07 | HSR waiting period expired; shareholders approved on 2026-07-16. | [Vote-results 8-K, accession `0000950103-26-010760`](https://www.sec.gov/Archives/edgar/data/1141103/0000950103-26-010760-index.html); [HSR 8-K](https://www.sec.gov/Archives/edgar/data/1141103/000095010326009315/dp248764_8k.htm) |
| `OGN.XNYS` | `$14.00` | 2026-04-26 | Vote scheduled for 2026-07-23; transaction remains pending. | [Definitive proxy, accession `0001193125-26-273323`](https://www.sec.gov/Archives/edgar/data/1821825/000119312526273323/d15298ddefm14a.htm) |
| `AES.XNYS` | `$15.00` | 2026-03-02 | Shareholder-approved and HSR waiting period expired; other closing conditions remain. | [Approval and HSR 8-K, accession `0001140361-26-026562`](https://www.sec.gov/Archives/edgar/data/874761/000114036126026562/ef20076870_8k.htm) |
| `DBRG.XNYS` | `$16.00` | 2025-12-29 | Shareholder-approved; H2 2026 close remains guided. | [Shareholder-approval 8-K, accession `0001104659-26-047803`](https://www.sec.gov/Archives/edgar/data/1679688/000110465926047803/tm2612488d1_8k.htm) |
| `IMXI.XNAS` | `$16.00` | 2025-08-10 | All international and 51 U.S. state/territory approvals were reported obtained; one U.S. state approval remained. | [Latest SEC 10-Q, accession `0001628280-26-033174`](https://www.sec.gov/Archives/edgar/data/1683695/000162828026033174/imxi-20260331.htm); [issuer press-release index containing the 2026-06-24 update](https://investors.intermexonline.com/news-events/press-releases) |
| `SLP.XNAS` | `$18.50` | 2026-06-15 | Preliminary-proxy stage; Q4 2026 close guided. | [Preliminary proxy, accession `0001023459-26-000036`](https://www.sec.gov/Archives/edgar/data/1023459/000102345926000036/prem14a.htm) |
| `AVNS.XNYS` | `$25.00` | 2026-04-13 | Vote scheduled for 2026-07-22; solicitation remains active. | [Supplemental 8-K, accession `0001606498-26-000093`](https://www.sec.gov/Archives/edgar/data/1606498/0001606498-26-000093-index.html); [definitive proxy](https://www.sec.gov/Archives/edgar/data/1606498/000110465926072432/tm2614353-2_defm14a.htm) |
| `ALOT.XNAS` | `$29.00` | 2026-06-17 | Preliminary-proxy stage; Q3 2026 close guided. | [Latest preliminary-proxy filing, accession `0001193125-26-306199`](https://www.sec.gov/Archives/edgar/data/8146/0001193125-26-306199-index.html); [announcement 8-K](https://www.sec.gov/Archives/edgar/data/8146/000119312526273447/d100857d8k.htm) |
| `RAMP.XNYS` | `$38.50` | 2026-05-17 | Vote scheduled for 2026-08-17; transaction remains pending. | [Definitive proxy, accession `0001104659-26-080505`](https://www.sec.gov/Archives/edgar/data/733269/000110465926080505/tm264528-7_defm14aseq1.htm) |

### Six additions

| InstrumentId | Cash/share | Announced | Latest verified lifecycle state as of 2026-07-17 | Primary evidence and eligibility caveat |
| --- | ---: | --- | --- | --- |
| `DSGR.XNAS` | `$35.00` | 2026-07-16 | Definitive agreement signed; majority-of-minority vote and HSR clearance remain. The agreement is not subject to a financing condition. | [Announcement 8-K, accession `0001193125-26-306263`](https://www.sec.gov/Archives/edgar/data/703604/000119312526306263/d131211d8k.htm); [issuer release](https://www.sec.gov/Archives/edgar/data/703604/000119312526306263/d131211dex991.htm). Very early-stage. |
| `CRNX.XNAS` | `$85.00` | 2026-07-06 | Q3 2026 close guided; shareholder, HSR and foreign clearances remain. Buyer disclosed committed bridge financing and no financing condition. | [Announcement 8-K, accession `0001140361-26-027642`](https://www.sec.gov/Archives/edgar/data/1658247/000114036126027642/ef20077399_form8k.htm); [latest deal solicitation, accession `0001140361-26-028209`](https://www.sec.gov/Archives/edgar/data/1658247/0001140361-26-028209-index.html). |
| `APGE.XNAS` | `$135.11` | 2026-06-22 | Vote scheduled for 2026-08-11; Q3 2026 close guided. Consideration is fixed cash. | [Definitive proxy, accession `0001140361-26-028341`](https://www.sec.gov/Archives/edgar/data/1974640/000114036126028341/ny20076262x2_defm14a.htm). |
| `TECH.XNAS` | `$73.00` | 2026-06-25 | Shareholder and global regulatory approvals remain; close guided for late 2026 or early 2027. | [Announcement 8-K, accession `0001999371-26-013527`](https://www.sec.gov/Archives/edgar/data/842023/000199937126013527/tech-8k_062326.htm); [latest solicitation, accession `0001999371-26-014655`](https://www.sec.gov/Archives/edgar/data/842023/000199937126014655/tech-defa14a_070926.htm). |
| `BHF.XNAS` | `$70.00` | 2025-11-06 | Shareholder-approved; HSR was cleared, while FINRA and Delaware, Massachusetts and New York insurance approvals remained. Close is still guided for 2026. | [Definitive proxy, accession `0001140361-26-000522`](https://www.sec.gov/Archives/edgar/data/1685040/000114036126000522/ny20060599x2_defm14a.htm); [shareholder-approval 8-K, accession `0001685040-26-000005`](https://www.sec.gov/Archives/edgar/data/1685040/000168504026000005/exhibit991-brighthouseshar.htm). Promoted from the old conditional tier. |
| `EA.XNAS` | `$210.00` | 2025-09-29 | Shareholder approval and HSR clearance are complete; limited regulatory reviews remain. Buyer debt tenders were extended to 2026-07-30, with settlement expected 2026-08-04, while the merger remained pending. | [Latest issuer 8-K, accession `0000712515-26-000053`](https://www.sec.gov/Archives/edgar/data/712515/000071251526000053/earningspressrelease2026_0.htm); [HSR 8-K, accession `0001140361-26-004514`](https://www.sec.gov/Archives/edgar/data/712515/000114036126004514/ef20065192_8k.htm); [buyer debt-tender update](https://www.prnewswire.com/news-releases/oak-eagle-acquireco-inc-announces-extension-of-the-expiration-time-and-settlement-date-for-the-previously-announced-tender-offers-and-consent-solicitations-for-any-and-all-of-electronic-arts-incs-1-850-senior-notes-due-2031-a-302826961.html). |

## Changes from the 2026-07-15 note

- Keep all 14 prior core names; none had completed or terminated by the evidence cutoff.
- Add the six names above. The old sub-`$40` preference was an execution heuristic, not an economic or broker constraint, and discarded useful breadth.
- Promote `BHF.XNAS` from conditional to the recommended research universe, still subject to the same broker validation as every new addition.
- Remove `TXNM.XNYS` from conditional admission. Its 2026-07-06 8-K reports that the New Mexico Public Regulation Commission voided the `$400 million` PIPE, ordered unwind/compliance, imposed fines, and stayed the merger-application schedule.[^txnm]

## Explicit exclusions and watchlist

| Candidate | Decision | Reason |
| --- | --- | --- |
| `TXNM.XNYS` | Exclude pending resolution | Current New Mexico regulatory action is adverse and the transaction schedule is stayed; treating a stale tracker status as a normal pending deal would be misleading.[^txnm] |
| `PERF.XNYS` | Watchlist | The `$2.00` fixed-cash transaction is binding and guided for Q4, but Perfect Corp. is a foreign private issuer reporting on `6-K`. The current Edgar event source described for the prototype only consumes U.S. `8-K` deal events; admit it only after causal `6-K` support is explicit.[^perf] |
| `WBD.XNAS`, `CZR.XNAS` | Exclude from clean fixed-cash parser | Consideration includes a ticking component, so the terminal value is date-dependent rather than a single fixed number.[^wbd][^czr] |
| `TBPH`, `ATAI`, `ESPR` | Exclude | Contingent value rights make the payoff path-dependent and non-fixed. |
| `UNF` | Exclude | Mixed `$155` cash plus `0.772` Cintas shares; not a cash-only convergence endpoint. |
| `AFBI` | Exclude | `$23` headline consideration is subject to a closing-equity adjustment. |
| `GNK` | Exclude | Nonbinding/contested proposal rather than a signed fixed-cash transaction. |
| `TWO` | Exclude for now | Competing-bid/tender state is unstable and requires explicit bid-state logic. |
| `ZIM` and other foreign-private-issuer deals | Watchlist | Their filings and jurisdictional state require a supported `6-K`/foreign lifecycle path; do not silently treat missing `8-K` events as no news. |
| `TALK`, `NSTS`, `SILA` | Do not admit | Old-note candidates whose current primary evidence or supported fixed-cash endpoint was not retained in this audit. |

The 15 completed seeds must not enter a 2026-07-17 prospective universe. Examples include [CPRX's completion 8-K](https://www.sec.gov/Archives/edgar/data/1369568/000119312526304984/d159184d8k.htm), [WSR's completion 8-K](https://www.sec.gov/Archives/edgar/data/1175535/000119312526303327/d116879d8k.htm), [TBRG's completion 8-K](https://www.sec.gov/Archives/edgar/data/1169445/000119312526299668/d153395d8k.htm), and [XOMA's completion 8-K](https://www.sec.gov/Archives/edgar/data/791908/000119312526302648/d165297d8k.htm).

## Use boundary

> [!warning] Prospective only
> Do not backfill these 20 current targets into an earlier backtest. That would leak knowledge of future targets and omit completed, terminated, and delisted historical deals. Use this list for a current-state run or freeze it for a forward paper test beginning after 2026-07-17. Historical validation requires a point-in-time event inventory.

The recommendation also does not turn every deal on. The strategy should separately require positive expected net event payoff after completion upside, break downside, time, commission, spread, and concentration constraints. Universe breadth preserves opportunity; it is not an allocation signal.

## Bootstrap result

The prospective bootstrap through 2026-07-16 ingested one announcement for each of the 20 names and obtained complete IBKR market marks, but the frozen `q70` benchmark allocated nothing. This is a policy result, not a universe-data failure: ten names fell below its beta-adjusted fallback, eight had no positive spread after its fixed 175-day cash-rate discount, and four failed its `q_market >= 70%` threshold (the categories overlap). Two also failed the liquidity floor.

Do not enlarge the universe with weaker or non-fixed deals merely to force ten eligible positions. The next research question is whether the fixed 175-day horizon and beta-adjusted fallback are defensible risk controls for seasoned deals; it is separate from establishing the current event inventory.

[^txnm]: [TXNM 2026-07-06 regulatory-update 8-K, accession `0001108426-26-000040`](https://www.sec.gov/Archives/edgar/data/81023/000110842626000040/pnm-20260706.htm)
[^perf]: [Perfect Corp. transaction 6-K, accession `0001104659-26-082398`](https://www.sec.gov/Archives/edgar/data/1899830/000110465926082398/tm2619936d1_6k.htm); [issuer announcement](https://ir.perfectcorp.com/news-and-events/news-releases/news-details/2026/Perfect-Corp--Enters-into-a-Definitive-Agreement-for-a-Going-Private-Transaction/default.aspx)
[^wbd]: [Warner Bros. Discovery preliminary merger proxy](https://www.sec.gov/Archives/edgar/data/1437107/000119312526108369/d115093dprem14a.htm)
[^czr]: [Caesars transaction 8-K](https://www.sec.gov/Archives/edgar/data/1590895/000119312526242995/d143382d8k.htm)
