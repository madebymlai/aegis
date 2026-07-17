---
title: Demeter Current Cash-Merger Universe
date: 2026-07-15
topic: demeter-cash-merger
status: implementation-note
related:
  - "[[finding-a-buildable-convergent-engine]]"
  - "[[the-tiered-strategy-roster]]"
tags:
  - note
  - demeter
  - merger-arbitrage
  - instruments
  - ibkr
---

# Demeter Current Cash-Merger Universe

> [!abstract] Decision
> Use the 14 exact InstrumentIds below as Demeter's **verified prospective current fixed-cash core**. Each contract qualified through the local IBKR paper Gateway as a USD common stock with a one-share size increment and no instrument-definition ineligibility reason. A one-share buy limit `whatIf` at the cash offer also returned `PreSubmitted` without an order error for every core name. Add `TXNM.XNYS` and `BHF.XNAS` conditionally after the same broker checks: their `$61.25` and `$70.00` shares remain whole-share feasible and their wider spreads can improve breadth. This establishes instrument eligibility, not strategy validity: the current SEC event source discovers deals too late to estimate an honest pre-announcement break value.

## Recommended complete universe

Primary filings establish fixed cash consideration and a still-pending process as of 2026-07-15. The IBKR identifiers and `conId`s were qualified locally on that date.

| InstrumentId | IBKR `conId` | Fixed cash/share | Primary point-in-time evidence and current milestone |
| --- | ---: | ---: | --- |
| `CCO.XNYS` | `362175385` | `$2.43` | The definitive proxy states `$2.43` cash per share.[^cco] |
| `LPRO.XNAS` | `426545710` | `$3.15` | The target's tender recommendation states `$3.15` cash; the related 8-K gives an October 15 outside date with a regulatory extension to December 15.[^lpro14d9][^lpro8k] |
| `PAYO.XNAS` | `499621117` | `$7.40` | The June 15 announcement 8-K states `$7.40` cash per share; solicitation filings remained active in July.[^payo] |
| `KORE.XNYS` | `712118325` | `$9.25` | The definitive proxy states `$9.25` cash per share; a July 9 filing kept the transaction process active.[^kore][^kore8k] |
| `GBTG.XNYS` | `564354641` | `$9.50` | The definitive proxy states `$9.50` cash and schedules the special meeting for August 3.[^gbtg] |
| `CCRN.XNAS` | `13608169` | `$13.25` | The definitive proxy states `$13.25` cash; the HSR waiting period expired on June 22.[^ccrn][^ccrnhsr] |
| `OGN.XNYS` | `490414355` | `$14.00` | The definitive proxy states `$14.00` cash per share.[^ogn] |
| `AES.XNYS` | `2560358` | `$15.00` | The definitive proxy states `$15.00` cash; shareholders approved the merger and the HSR waiting period expired in June.[^aes][^aesvote] |
| `DBRG.XNYS` | `578327143` | `$16.00` | The definitive proxy states `$16.00` cash; shareholders approved the merger in April.[^dbrg][^dbrgvote] |
| `IMXI.XNAS` | `327709672` | `$16.00` | The definitive proxy states `$16.00` cash. Shareholders approved in December 2025, but the long regulatory path makes stale-deal and break-risk control especially important.[^imxi][^imxivote] |
| `SLP.XNAS` | `28174576` | `$18.50` | The July 9 preliminary proxy states `$18.50` cash; this is an early-stage candidate until the definitive proxy appears.[^slp] |
| `AVNS.XNYS` | `321325546` | `$25.00` | The definitive proxy states `$25.00` cash; a July 15 supplemental filing shows that the vote process remained active.[^avns][^avnssupp] |
| `ALOT.XNAS` | `266058` | `$29.00` | The announcement 8-K states `$29.00` cash; this is an early-stage candidate until a definitive proxy appears.[^alot] |
| `RAMP.XNYS` | `335460283` | `$38.50` | The definitive proxy states `$38.50` cash and schedules the special meeting for August 17.[^ramp] |

The complete config should contain all 14 names. A tight current spread is a signal outcome, not a reason to erase a valid pending deal from the opportunity set: the indicator should leave it at zero weight when expected net value is insufficient. Remove a name only when primary evidence says the deal closed, terminated, changed to complex consideration, or otherwise became ineligible.

### Conditional breadth tier: `TXNM` and `BHF`

The initial 14-name cutoff was a conservative sub-`$40` granularity preference, not a mechanism-based rejection of the two higher-priced targets.

| Prospective InstrumentId | Fixed cash/share | Why it can help | What remains before config admission |
| --- | ---: | --- | --- |
| `TXNM.XNYS` | `$61.25` | Roughly `7.2%` gross spread in the 2026-07-15 discovery snapshot; utility-regulatory risk differs from the other core deals. | Qualify the exact IBKR contract and run the one-share `whatIf`. Parse the stated dividend adjustment rather than treating `$61.25` as an unconditional terminal value, and model the pending NRC/New Mexico regulatory path.[^txnm] |
| `BHF.XNAS` | `$70.00` | Roughly `7.2%` gross spread in the snapshot; shareholders have approved and the remaining insurance approvals add a distinct timing premium. | Qualify the exact IBKR contract and run the one-share `whatIf`. The long, multi-state insurance review requires explicit stale-deal/timeline handling rather than a constant completion probability.[^bhf] |

One share of either name is still affordable in an integer-share sleeve; excluding them merely to keep every stock below `$40` would sacrifice breadth unnecessarily. The correct design is therefore **14 broker-verified core names plus two conditional names**, promoted after contract/order validation and exact payoff parsing. Their current spreads are discovery context, not independently verified executable quotes.

## What the IBKR check did and did not prove

Two local paper-Gateway checks succeeded on 2026-07-15:

1. Contract qualification resolved every identifier to `COMMON`, `USD`, size increment `1`, with no `ineligibilityReasonList` entry.
2. A one-share SMART buy limit `whatIf`, priced at the contractual cash offer, returned `PreSubmitted` with no order error for every identifier. `whatIf` previews do not transmit orders.

This does **not** prove that a future live order will fill, that market data is subscribed, that the spread exceeds costs, that a borrow is available, or that the instrument remains eligible after a corporate-action update. It also does not validate historical data. Daily-history requests currently time out even for an `AAPL` control as well as `SLP` and `ZIM`, so the Gateway's current HMDS problem cannot be interpreted as an asset-specific rejection. Price-history coverage remains unverified.

## The source must be corrected before this becomes a valid strategy

The current SEC adapter discovers only `DEFM14A`, `SC 14D9` and `SC 14D9/A`. Its `first_effective` date is therefore generally the definitive-proxy or tender-recommendation date. Demeter then estimates `break_value` from the preceding 20 trading days. Those observations can already contain the announced offer and may sit close to the offer price; they are not the unaffected pre-announcement value.

That is load-bearing. A broad universe cannot rescue a payoff model whose downside anchor is measured after the catalyst. Before using this universe, discovery must start from the definitive merger-announcement 8-K (or another source field that records the true public announcement timestamp), preserve that causal timestamp, and estimate break value strictly from data available before it. This is also why `PAYO`, `SLP` and `ALOT` can qualify economically now but will not necessarily activate under the current discovery-form set.

## Honest YAML semantics

Do not put this current list into a `2020-08-10` to `2026-07-01` backtest. That would give the past advance knowledge of companies selected because they are pending targets today, omit completed and delisted historical targets, and create both look-ahead and survivorship bias.

The honest uses are:

- **Current-state allocation:** start no earlier than the latest causal event-source rebuild and interpret only the latest allocation, not historical performance.
- **Forward paper test:** freeze the 14-name universe as known on `2026-07-15`, begin on `2026-07-16` or the first subsequent trading session, and dynamically admit/deactivate only from later timestamped primary filings.
- **Historical validation:** build a separate point-in-time event inventory of all contemporaneous fixed-cash targets, including completed, terminated and delisted names, and obtain survivorship-safe price history. Only that inventory can support a 2020–2026 conclusion.

## Deliberate exclusions

| Name | Reason not to put in the clean fixed-cash config |
| --- | --- |
| `TALK.XNAS` | A June 22 `25-NSE` indicates exchange removal; the tracker entry was stale.[^talk] |
| `CPRX.XNAS` | IBKR returned `No Opening Trades: DTC Chilled or Ineligible` during instrument qualification. |
| `TBPH`, `ESPR`, `XOMA` | Contingent value rights make consideration and payoff non-fixed. |
| `AFBI`, `NSTS` | Consideration is adjustable or approximate rather than a definitive fixed amount per share. |
| `WBD`, `CZR` | Ticking-fee/consideration mechanics exceed the clean initial parser contract. |
| `ZIM.XNYS` | Fixed cash is not enough: the Israeli golden-share/government-veto state is too material for the current constant completion-probability ranker. |
| `EEX.XNYS`, `SILA.XNYS` | Local contract qualification timed out; do not guess their identifiers or eligibility. |

[^cco]: [Clear Channel Outdoor definitive proxy, filed 2026-04-13](https://www.sec.gov/Archives/edgar/data/1334978/000121390026042721/ea0283916-02.htm)
[^lpro14d9]: [Open Lending Schedule 14D-9, filed 2026-06-29](https://www.sec.gov/Archives/edgar/data/1806201/000119312526286952/d140679dsc14d9.htm)
[^lpro8k]: [Open Lending transaction 8-K, filed 2026-06-16](https://www.sec.gov/Archives/edgar/data/1806201/000119312526271902/d147981d8k.htm)
[^payo]: [Payoneer transaction 8-K, filed 2026-06-15](https://www.sec.gov/Archives/edgar/data/1845815/000095010326008945/dp248400_8k.htm)
[^kore]: [KORE definitive proxy, filed 2026-06-12](https://www.sec.gov/Archives/edgar/data/1855457/000114036126025086/ny20068726x6_defm14a.htm)
[^kore8k]: [KORE 8-K, filed 2026-07-09](https://www.sec.gov/Archives/edgar/data/1855457/000114036126028120/ef20077619_8k.htm)
[^gbtg]: [Global Business Travel definitive proxy, filed 2026-07-06](https://www.sec.gov/Archives/edgar/data/1820872/000114036126027649/ny20072693x2_defm14a.htm)
[^ccrn]: [Cross Country Healthcare definitive proxy, filed 2026-06-15](https://www.sec.gov/Archives/edgar/data/1141103/000114036126025249/ny20073866x2_defm14a.htm)
[^ccrnhsr]: [Cross Country Healthcare HSR 8-K, filed 2026-06-23](https://www.sec.gov/Archives/edgar/data/1141103/000095010326009315/dp248764_8k.htm)
[^ogn]: [Organon definitive proxy, filed 2026-06-25](https://www.sec.gov/Archives/edgar/data/1821825/000119312526273323/d15298ddefm14a.htm)
[^aes]: [AES definitive proxy, filed 2026-05-19](https://www.sec.gov/Archives/edgar/data/874761/000114036126021662/ny20067536x2_defm14a.htm)
[^aesvote]: [AES approval and HSR 8-K, filed 2026-06-26](https://www.sec.gov/Archives/edgar/data/874761/000114036126026562/ef20076870_8k.htm)
[^dbrg]: [DigitalBridge definitive proxy, filed 2026-03-30](https://www.sec.gov/Archives/edgar/data/1679688/000110465926033634/tm267669-2_defm14a.htm)
[^dbrgvote]: [DigitalBridge shareholder-approval 8-K, filed 2026-04-23](https://www.sec.gov/Archives/edgar/data/1679688/000110465926047803/tm2612488d1_8k.htm)
[^imxi]: [International Money Express definitive proxy, filed 2025-10-17](https://www.sec.gov/Archives/edgar/data/1683695/000114036125040538/ny20053648x2_defm14a.htm)
[^imxivote]: [International Money Express shareholder-approval 8-K, filed 2025-12-09](https://www.sec.gov/Archives/edgar/data/1683695/000114036125044991/ef20060920_8k.htm)
[^slp]: [Simulations Plus preliminary proxy, filed 2026-07-09](https://www.sec.gov/Archives/edgar/data/1023459/000102345926000036/prem14a.htm)
[^avns]: [Avanos Medical definitive proxy, filed 2026-06-29](https://www.sec.gov/Archives/edgar/data/1606498/000110465926072432/tm2614353-2_defm14a.htm)
[^avnssupp]: [Avanos Medical supplemental 8-K, filed 2026-07-15](https://www.sec.gov/Archives/edgar/data/1606498/000160649826000093/avns-20260714.htm)
[^alot]: [AstroNova transaction 8-K, filed 2026-06-17](https://www.sec.gov/Archives/edgar/data/8146/000119312526273447/d100857d8k.htm)
[^ramp]: [LiveRamp definitive proxy, filed 2026-07-06](https://www.sec.gov/Archives/edgar/data/733269/000110465926080505/tm264528-7_defm14aseq1.htm)
[^talk]: [Talkspace exchange-removal filing, filed 2026-06-22](https://www.sec.gov/Archives/edgar/data/1803901/000135445726000617/8A_CERT_TALK.pdf)
[^txnm]: [TXNM Energy definitive-proxy filings, SEC company search](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001108426&type=DEFM14A&dateb=&owner=include&count=10)
[^bhf]: [Brighthouse Financial definitive-proxy filings, SEC company search](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001685040&type=DEFM14A&dateb=&owner=include&count=10)
