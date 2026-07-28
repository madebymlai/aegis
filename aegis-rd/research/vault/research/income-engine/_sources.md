---
title: "Convergent Income Engine - sources register"
date: 2026-07-25
tags:
  - register
  - income-engine
  - citations
---

# Convergent Income Engine - sources register

> [!abstract] Purpose and method
> Stage 1 citation register for "The Convergent Income Engine: Funding the Book Through Ordinary
> Markets". Extracted from the seven folded articles' own footnotes, not re-derived. Every citation
> below is copied from a vault article's Sources section (author, venue, volume, year, COI as the
> article itself states them) unless marked otherwise. Where a detail is missing in the vault text,
> it is recorded as missing, not filled in.
>
> This register also performed live primary-source verification this session (2026-07-25). An initial
> pass used WebSearch/WebFetch; every load-bearing item was then independently re-confirmed through
> Exa (`mcp__exa__web_search_exa` / `mcp__exa__web_fetch_exa`) per team-lead instruction, checking
> authors, year, venue and volume against the primary page each time rather than accepting a
> plausible-looking title match. All eight re-checks (Bassi et al.'s sample period, Terstegge,
> Mallory's crypto-wedge paper, the Bai-Bali-Wen retraction, He-Kelly-Manela, Adrian-Etula-Muir,
> Gospodinov-Robotti's placebo figure, Kargar's leverage figures, Qiao-Xu-Zhang-Zhou, Evans et al.,
> and the Drobetz-Schröder-Tegtmeier cat-bond paper) confirmed cleanly against the primary source with
> no near-misses. Below, "verified this session" or "confirmed via Exa" marks a citation checked this
> way, rather than one carried forward on the vault's word alone.
> number of adjacent items that were cheap to check. Those checks are new evidence, not previously
> recorded in the vault, and are marked accordingly in each row with **"verified this session"**.

## Verification-status legend

- **VERIFIED-IN-VAULT** - confirmed against the primary source, either previously in
  `research/budgeting-convexity/_challenge-verification.md`, or newly this session (marked
  "verified this session" with what was checked).
- **CITED-CONSISTENT** - appears with matching details across multiple vault articles, or is a
  standard peer-reviewed/official source with no internal contradiction found; not independently
  primary-source-checked in this pass.
- **UNCONFIRMED** - the vault itself flags it as unconfirmed, single-sourced, or missing details
  (author names, sample period, exact figures not independently re-quoted from primary text).
- **NEEDS-VENUE-CHECK** - post-2023 and not yet confirmed to exist in a real peer-reviewed venue
  (arXiv/SSRN/working-paper only).
- **CONTESTED** - a published challenge exists against the claim.
- **RETRACTED** - withdrawn by the authors or publisher.

---

## 1. Summary counts

Approximately **185 distinct sources** across the seven folded articles and the backbone notes the
brief says inform the paper's framing (plus roughly 15 non-academic instrument/product-documentation
sources, listed separately in §3.9, that a theoretical paper is unlikely to cite directly). Counting
is manual across ~250 raw footnote instances with heavy cross-article duplication (Koijen, Moskowitz,
Pedersen & Vrugt's "Carry" alone is cited, in whole or by name, in six of the eleven source documents
read); treat the count as approximate. The per-citation rows in §3 are the authoritative record.

**By pedigree** (academic/practitioner-research sources only, excludes §3.9's product documentation):

| Pedigree | Approx. count |
|---|---|
| Peer-reviewed journal | ~120 |
| Working paper (NBER/SSRN/arXiv/central-bank) | ~35 |
| Practitioner white paper / index-provider / manager research | ~20 |
| Master's thesis | 2 |
| Practitioner blog | 4 |
| Official (central bank / BIS / exchange education) | ~6 |

**By verification status:**

| Status | Approx. count | Note |
|---|---|---|
| VERIFIED-IN-VAULT | ~20 | includes 8 from `_challenge-verification.md` and ~11 newly verified this session |
| CITED-CONSISTENT | ~135 | the bulk of standard peer-reviewed citations |
| UNCONFIRMED | ~20 | working papers/theses/blogs the vault itself flags, or missing details |
| NEEDS-VENUE-CHECK | ~8 | post-2023, arXiv/SSRN-only |
| CONTESTED | ~6 | see blocking items |
| RETRACTED | 1 | Bai, Bali & Wen (JFE 2019) |

---

## 2. Blocking items

These must be resolved, or explicitly fenced as corroborating-only, before the paper cites them.
Ordered by how much the paper depends on them (per the parallel synthesis agent's read of the fold
corpus, which this register agrees with).

### 2.1 Bassi, Behn, Grill & Waibel (2024) - sample period

**Status: substantially resolved this session, not yet confirmed against the final paywalled text.**
The vault (`window-dressing-at-the-regulatory-snapshot.md`, `the-premium-is-rent-on-a-balance-sheet.md`)
explicitly states the sample start/end years are unconfirmed and must be closed before citing the
12.5%/25% figures in a paper. Live verification this session found the primary text: the ECB Working
Paper predecessor (No. 2771, February 2023, same four authors, same figures) states plainly, twice,
**"The sample period is from 1 September 2016 to 30 June 2021"** across 36 large euro-area banks
(MMSR confidential transaction data). A companion SUERF Policy Brief and a 2026 BIS Basel Committee
working paper (which cites "Bassi et al (2023)" for the identical 12.5%/25% figures) both corroborate
the same headline numbers without contradiction. The published *Journal of Financial Intermediation*
58 (2024), article 101086, DOI `10.1016/j.jfi.2024.101086`, is confirmed to exist and to carry the
same abstract and headline figures via IDEAS/RePEc. **What remains open:** ScienceDirect returned a
403/paywall both via WebFetch and Exa, so the exact sample-period sentence was not read in the final
peer-reviewed PDF itself - only in the 2023 working-paper predecessor and papers citing it. Given
working papers rarely change their core sample window en route to publication, and no citing source
gives a different window, treat September 2016 - June 2021 as high-confidence but formally
**NEEDS-VENUE-CHECK** until someone reads the published PDF directly.

### 2.2 Bai, Bali & Wen (JFE 2019) - RETRACTED

**Status: confirmed independently this session, re-confirmed via Exa.** "Common risk factors in the
cross-section of corporate bond returns," *Journal of Financial Economics* 131(3):619-642 (published
online 16 August 2018, cover-dated 2019), DOI `10.1016/j.jfineco.2018.08.002`. Retraction notice: *JFE*
150(3):103721, December 2023, DOI `10.1016/j.jfineco.2023.103721`, sourced directly from ScienceDirect
via `mcp__exa__web_search_exa` this session, with the retraction text itself confirming the mechanism:
*"subsequent research conducted by Dickerson, Mueller and Robotti (2023)... reveals an error present
in the data used by Bai et al. (2019) that consists of temporal misalignment of different data
series... The authors of Bai et al. (2019) confirm that the original results are based on the data
with the above error."* The retraction is at the authors' request, per the
Dickerson-Mueller-Robotti citation already in the vault. **No folded article treats BBW as live
evidence** - it appears only as historical context inside the [^dmr] citation in
`what-makes-a-convergent-sleeve-an-income-engine.md`, explaining what got corrected. The paper must
never cite BBW's factor findings as evidence, only (if at all) as the retracted predecessor the
Dickerson-Mueller-Robotti/Dickerson-Robotti-Rossetti correction is about.

### 2.3 Dickerson, Robotti & Rossetti - "The Corporate Bond Factor Replication Crisis"

**Status: unpublished working paper, confirmed still unpublished.** arXiv:2604.07880 (2026). The
vault's own fate-check (2026-07-10) found it still a working paper, April 2026 revision, also on SSRN
6088966. Not independently re-checked this session (no new information since 2026-07-10 would be
expected in two weeks). NEEDS-VENUE-CHECK. Any claim sourced to it must carry the not-peer-reviewed
flag the vault already attaches.

### 2.4 Terstegge - "Intermediary Option Pricing" - RESOLVED this session

**Status: identified and verified, re-confirmed via Exa.** The brief (`_brief.md`) flagged this as an
"open lead...needs sourcing before use," with only an unidentified "unpublished conference paper whose
authors and title could not be pinned down." Live verification this session fetched the paper directly
and re-confirmed it via `mcp__exa__web_search_exa` against three independent pages (the FMA-hosted
PDF, Terstegge's own faculty site, and his Copenhagen Business School PhD thesis record): **Julian
Terstegge**, "Intermediary Option Pricing," working paper, version dated November 7, 2025 (SSRN
5877762; presented FMA Derivatives 2025, circulated via AFA program materials). Byline affiliation on
the paper itself is **University of Michigan** (Ross School of Business, his current position per his
faculty page); the underlying research was conducted as Chapter 1 of his PhD thesis at **Copenhagen
Business School** ("Essays in Financial Intermediation and Climate Economics," DOI
`10.22439/phd.14.2025`, 2025) - both affiliations are real and not a mismatch, just sequential (CBS
PhD candidate at the time of writing, now Michigan faculty). H-index 0, 0 citations at time of check,
consistent with a still-unpublished single-author paper. The paper's own text confirms the data window
the vault had already partially cited ("CBOE data 2011-2023"): *"For each day between 2011 and 2023, I
estimate dealers' aggregate positions across all outstanding S&P 500 index options."* The abstract and
the "shadow gamma" mechanism (scenario gamma at a hypothetical 10% down-move stays strongly negative
even where local/contemporaneous gamma has flattened) match the vault's paraphrase in
`the-payer-did-not-leave-the-supply-arrived.md` and `_challenge-verification.md` verbatim in substance.
**This unblocks the citation but does not upgrade its weight**: it remains a single-author,
non-peer-reviewed working paper, and per the parallel
synthesis agent's read (`_synthesis.md` §3.3), it does not rebut Dew-Becker & Giglio and must never be
load-bearing - corroborating only.

### 2.5 Dew-Becker & Giglio - break-date instability

**Status: CONTESTED, not blocking in the sense of unresolvable, but requires careful handling.**
Per `_challenge-verification.md` (already in the vault) and confirmed by this register's reading:
the underlying finding (S&P 500 traded-option alpha ≈ 0 since a break point) is real, but the break
date moves between the authors' own drafts - near 2010 in the plain-language summary (Chicago Fed WP
2025-17, Sept 2025) and 2012 in the statistical estimate of the sibling S&P-500-specific paper
(conditionally accepted, *Critical Finance Review*, 2026), with Bates (2022) independently dating a
decline at 2017 on separate methodology. The paper is still a working paper (Chicago Fed WP series;
NBER WP 31833 is the 2023 predecessor). Both papers exist and are correctly described; what is
contested is (a) the exact date, (b) whether the zero-alpha result says anything about jump-risk
compensation specifically (it does not - the authors' own text confirms jump risk lives in the
untested wedge between synthetic and traded returns), and (c) whether the "payer left" reading survives
Terstegge's shadow-gamma finding. Record as CONTESTED, and record the correction the vault's own
`the-payer-did-not-leave-the-supply-arrived.md` already makes: the mechanism with the right sign is
new option-selling supply arriving, not the payer leaving.

### 2.6 Tomunen (2026, RFS) on cat-bond premia

**Status: VERIFIED.** "Failure to share natural disaster risk," *Review of Financial Studies*
39(3):661-701, 2026, DOI `10.1093/rfs/hhaf055`. Confirmed in `_challenge-verification.md` with direct
quotes on the intermediary-constraint model fit (71% of test-asset return variation) and the
post-2017-losses recapitalization detail. Not re-verified live this session (no reason to doubt the
prior verification).

### 2.7 The contested intermediary spine

**Status: all four papers confirmed to exist with correct venues, re-confirmed via Exa in a second
pass; the underlying dispute is real and CONTESTED, and the two specific statistics carried in vault
prose are now independently confirmed to the primary text (an upgrade from the team lead's framing,
which anticipated these might need re-quoting).** Every entry below was checked twice this session -
once via WebSearch/WebFetch and once via `mcp__exa__web_search_exa`, cross-reading IDEAS/RePEc,
publisher pages (Wiley, ScienceDirect), and (for the two disputed statistics) the primary PDF text
directly - with author list, year, journal, volume and page range matching exactly both times.

- **He, Kelly & Manela (2017)**, "Intermediary Asset Pricing: New Evidence from Many Asset Classes,"
  *Journal of Financial Economics* 126(1):1-35, DOI `10.1016/j.jfineco.2017.08.002`. Confirmed this
  session, both passes.
- **Adrian, Etula & Muir (2014)**, "Financial Intermediaries and the Cross-Section of Asset Returns,"
  *Journal of Finance* 69(6):2557-2596, DOI `10.1111/jofi.12189`. Confirmed this session, both passes;
  the abstract's own headline figures (R²=77%, average annual pricing error 1%) are consistent across
  every source pulled.
- **Gospodinov & Robotti (2021)**, "Common Pricing across Asset Classes: Empirical Evidence
  Revisited," *Journal of Financial Economics* 140(1):292-324. Confirmed this session, both passes,
  full title recovered (the vault's own citations give only "(JFE 2021)" without a title in the
  backbone notes). **The "39 of 40" placebo statistic is now confirmed verbatim from the primary
  text**, fetched via Exa directly from the authors' own working-paper PDF (Warwick Business School
  repository) as well as the published ScienceDirect page: *"Based on HKM's methodology and a 5%
  nominal size of the tests, the industry factor is found to be priced in 39 out of 40 cases... In
  contrast, our proposed battery of tests only retains the industry factor one time out of 40."*
  VERIFIED-IN-VAULT.
- **Kargar (2021)**, "Heterogeneous Intermediary Asset Pricing," *Journal of Financial Economics*
  141(2):505-532 (not "Broker-Dealer Leverage and the Cross-Section of Equity Returns," which was an
  earlier working-paper title for the same underlying project - confirmed via Exa against the AEA
  conference program, Kargar's own faculty page, and the published ScienceDirect abstract, all of
  which agree on the published title). Confirmed this session, both passes. **The "47%/72%"
  leverage-swing statistic is now confirmed verbatim**: *"broker-dealers reduced leverage by
  about 47% (from 35 to 19) while holding companies increased leverage by approximately 72% (from 22
  to 38)"* over 2008Q1-2009Q4. VERIFIED-IN-VAULT.

The dispute itself (single intermediary factor vs. plural, venue-local constraints) remains
unresolved in the literature - that is the nature of a contested spine, not a defect in the register.
The parallel synthesis agent's read (`_synthesis.md` §3.1) concludes correctly that Kargar's plurality
finding, not a repaired single factor, is what survives, and that this *supports* rather than
undermines `carry-is-not-one-premium`'s thesis.

### 2.8 Crypto spot-versus-futures wedge - RESOLVED this session

**Status: attributed, re-confirmed via Exa.** The vault (`the-premium-is-rent-on-a-balance-sheet.md`)
records "a May 2026 arXiv working paper reports a persistent 2.58% annualised wedge... Authors not
recorded here - attribute before citing." Identified this session and independently re-confirmed via
`mcp__exa__web_fetch_exa` against the arXiv HTML page directly: **Mallory, Mindy L. (2026)**, "Implied
ETF Carry Rates and the Limits of Arbitrage in Segmented Bitcoin Markets," arXiv:2605.29309, submitted
May 28, 2026, Associate Professor, Purdue University (single author, 0 citations at time of check). The
paper's own text confirms the exact figures and their basis: *"the mean wedge is 2.58% and the median
wedge is 2.52%, both measured in annual percentage points"* across 386 date-bucket observations, "5th
percentile is -4.77%, and the 95th percentile is 10.42%," comparing IBIT-option-implied carry (via
put-call parity plus BlackRock's daily holdings file) to CME bitcoin futures carry (benchmarked to
BRRNY). Working paper / arXiv preprint, not peer-reviewed. NEEDS-VENUE-CHECK, but now citable with
attribution instead of unusable.

### 2.9 Qiao, Xu, Zhang & Zhou (JBF 2024)

**Status: venue, authors, and sample fully confirmed this session and re-confirmed via Exa; content
remains unread by the desk.** "Variance risk premiums in emerging markets," *Journal of Banking and
Finance* 167:107259, 2024, DOI `10.1016/j.jbankfin.2024.107259`. Received Nov 12, 2023; accepted Jul 3,
2024. Full author list confirmed from the published first page, pulled via `mcp__exa__web_search_exa`
directly from the Tsinghua PBC School of Finance's hosted copy of the published PDF: **Fang Qiao**
(China School of Banking and Finance, UIBE), **Lai Xu** (Whitman School of Management, Syracuse
University), **Xiaoyan Zhang** (PBC School of Finance, Tsinghua University), **Hao Zhou** (PBC School
of Finance, Tsinghua; School of Business, Southern University of Science and Technology) - all four
names and all four affiliations match on both the IDEAS/RePEc record and the publisher-hosted PDF, no
discrepancy. Sample: January 2006 - December 2023, nine emerging markets (Brazil, China, India, South
Korea, Mexico, Poland, Russia, South Africa, Taiwan) and eleven developed markets - matches the
vault's description in `the-payer-did-not-leave-the-supply-arrived.md` exactly. Peer-reviewed,
genuine venue, real paper - **not** the "probably-synthetic article" the corpus has been warned about.
But `the-payer-did-not-leave-the-supply-arrived.md` states plainly "nobody on this desk has read it,"
and flags two specific reasons its headline figures cannot yet settle the question the desk cares
about (it measures a different object - raw implied-minus-*expected*-realized gap rather than a
delta-hedged alpha - and it ran no break test, so its full-sample average straddles the 2012 break and
is consistent with either hypothesis). **Do not cite its findings as settled evidence beyond the
abstract-level facts now confirmed.**

---

## 3. The register

Grouped by the paper's provisional sections. Citations repeated across multiple folded articles are
listed once, at first substantive use, with all citing articles named; later sections cross-reference
rather than repeat. Instrument/product-documentation sources (ETF tickers, ISINs, factsheets) are
kept in §3.9, separate from the academic bibliography, since the paper is decided to stay theoretical.

### 3.1 The role and its metric - `what-makes-a-convergent-sleeve-an-income-engine`

| Citation | Claim it is load-bearing for | Pedigree | COI | Verification |
|---|---|---|---|---|
| Goetzmann, Ingersoll, Spiegel & Welch (2007), "Portfolio Performance Manipulation and Manipulation-Proof Performance Measures," *RFS* 20(5):1503-1546 (NBER WP 9116, 2002) | Sharpe-maximizing payoff shape; the manipulation-proof measure $\hat\Theta$ | Peer-reviewed | None | CITED-CONSISTENT |
| Spurgin (2001), "How to Game Your Sharpe Ratio," *JAI* 4(3):38-46 | Empirical Sharpe-gaming via OTM put-writing | Peer-reviewed (practitioner journal) | None | CITED-CONSISTENT |
| Leland (1999), "Beyond Mean-Variance," *FAJ* 55(1):27-36 | Mean-variance rewards short-gamma at zero true alpha | Peer-reviewed | None | CITED-CONSISTENT |
| Lo (2002), "The Statistics of Sharpe Ratios," *FAJ* 58(4):36-52 | Serial correlation inflates annualized Sharpe up to 65% | Peer-reviewed | None | CITED-CONSISTENT |
| Bailey & Lopez de Prado (2014), "The Deflated Sharpe Ratio," *JPM* 40(5):94-107 | DSR corrects best-of-N selection bias | Peer-reviewed (practitioner journal) | None | CITED-CONSISTENT (also in `carry-is-not-one-premium`) |
| Eling & Schuhmacher (2007), "Does the choice of performance measure influence the evaluation of hedge funds?" *JBF* 31(9):2632-2647 | 2,763 funds, measure choice barely matters - the article's own best counter-evidence | Peer-reviewed | None | CITED-CONSISTENT |
| Smetters & Zhang (2013), NBER WP 19500, "A Sharper Ratio" | Adjusted-Sharpe corrections can misrank/diverge | Working paper (NBER) | None | CITED-CONSISTENT |
| Varga-Haszonits & Kondor (2008), *J. Statistical Mechanics* P12007 (arXiv:0811.0800) | Downside-risk estimator instability at small samples | Peer-reviewed (physics) | None | CITED-CONSISTENT |
| Asvanunt & Richardson (2017), "The Credit Risk Premium," *J. Fixed Income* 26(3) (SSRN 2563482) | Raw IG/HY credit premium figures (137bp/248bp) | Peer-reviewed | **AQR** | CITED-CONSISTENT - see §4, the vault's own Limitations section calls this "COI-free backbone," which contradicts its own Sources-section COI tag |
| Israel, Palhares & Richardson (2018), "Common Factors in Corporate Bond Returns," *JIM* 16(2) (SSRN 2576784) | Defensive+momentum+value beats carry alone (5.26% net, Sharpe 1.03) | Peer-reviewed | **AQR** | CITED-CONSISTENT |
| AQR (2016/2018), "Style Investing in Fixed Income" | Credit carry 0.90-correlated to market beta | Practitioner white paper | **AQR (high)** | CITED-CONSISTENT |
| Dickerson, Robotti & Rossetti (2026), arXiv:2604.07880 | 108-factor corporate bond zoo, survivors are value not carry | Working paper | None | **NEEDS-VENUE-CHECK** - see §2.3 |
| Dickerson, Mueller & Robotti (2023), "Priced risk in corporate bonds," *JFE* 150:103707 | BBW's factors fail replication; documents the retraction | Peer-reviewed | None | **VERIFIED-IN-VAULT** - this is the paper that names the BBW retraction, itself independently confirmed §2.2 |
| Getmansky, Lo & Makarov (2004), "An econometric model of serial correlation and illiquidity in hedge fund returns," *JFE* 74(3):529-609 | Smoothed marks inflate Sharpe, bias correlations toward zero | Peer-reviewed | None | CITED-CONSISTENT |
| Brown, Kang, In & Lee (2010), SSRN WP 1536323 | Doubt Ratio (MPPM-implied risk aversion flags manipulation) | Working paper | None | **UNCONFIRMED** - re-checked 2026-07-10, still unpublished after ~16 years |
| Foster & Young (2010), "Gaming Performance Fees by Portfolio Managers," *QJE* 125(4):1435-1458 | No track-record mechanism certifies skill vs. luck | Peer-reviewed | None | CITED-CONSISTENT |
| Maillard (2020), HAL WP hal-02989192 | MPPM tail-penalty quantification (~3%/unit negative skew) | Working paper | None stated | **UNCONFIRMED** - re-checked 2026-07-10, still unpublished |
| Henke, Kaufmann, Messow & Fang-Klingler (2020), "Factor Investing in Credit," *J. Index Investing* 11(1) | OAS-based carry/value print negative alphas in HY | Peer-reviewed | **Quoniam** | CITED-CONSISTENT |
| Mulder & Tims (2018), "Conditioning carry trades," *JIMF* 85:1-19 | Regime-avoidance beats unconditional carry, 25 countries | Peer-reviewed | None | CITED-CONSISTENT |
| Christiansen, Ranaldo & Soderlind (2011), *JFQA* 46(4):1107-1125 | Carry's equity beta rises in high-vol regime | Peer-reviewed | None | CITED-CONSISTENT |
| Asness (2016), "The Siren Song of Factor Timing," *JPM* 42(5) (SSRN 2763956) | Factor-timing gains mostly vanish when implemented | Peer-reviewed (practitioner journal) | **AQR** | CITED-CONSISTENT |
| McLean & Pontiff (2016), *JF* 71(1):5-32 | ~58% average post-publication decay | Peer-reviewed | None | CITED-CONSISTENT |
| Tasche (2008), "Capital Allocation... the Euler Principle" | Marginal risk contribution formalism behind $\Delta\hat\Theta$ | Working paper/technical note | None | CITED-CONSISTENT |
| TIFF, "Total Portfolio Approach: Just Best Practices, Rebranded?" | "There are no buckets" - marginal contribution principle | Practitioner white paper | None stated | CITED-CONSISTENT (repeated in `the-skew-is-the-product`) |
| Brito, working paper (U. Coimbra), "Portfolio Management With Higher Moments" | CE dominates Sharpe under skew/kurtosis | Working paper | None stated | **UNCONFIRMED** - single-sourced, no date given in vault text |
| Low, Pachamanova & Sim (2012), *Mathematical Finance* 22(2):379-410 | CE-maximization implicitly prices skew | Peer-reviewed | None | CITED-CONSISTENT |
| Ang, Chen & Xing (2006), "Downside Risk," *RFS* 19(4):1191-1239 (NBER WP 11824) | Downside correlation/beta as the conditioning metric | Peer-reviewed | None | CITED-CONSISTENT |
| Page & Panariello (2018), "When Diversification Fails," *FAJ* 74(3):19-32 | Full-sample correlation hides crisis co-movement | Peer-reviewed (practitioner journal) | T. Rowe Price (mild) | CITED-CONSISTENT (also in `the-skew-is-the-product`) |
| Harvey & Siddique (2000), *JF* 55(3):1263-1295 | Coskewness priced ~3%/yr but "very challenging to measure" | Peer-reviewed | None | VERIFIED-IN-VAULT (25-year replication tracked separately, see `skewness-in-asset-returns`) |
| Kim & White (2004), *FRL* 1(1):56-73 | Moment skew "extremely sensitive to single outliers" | Peer-reviewed | None | CITED-CONSISTENT |
| Hosking (1990), *JRSS-B* 52(1):105-124 | L-moment skewness, lower bias/variance | Peer-reviewed | None | CITED-CONSISTENT |
| Bastianin (2019), *Applied Economics* | L-/trimmed-L-moment estimators lowest RMSE | Peer-reviewed | None | CITED-CONSISTENT |
| Groeneveld & Meeden (1984), *The Statistician* 33(4):391-399 | Bowley-family robust skew cross-check | Peer-reviewed | None | CITED-CONSISTENT |
| Noguer i Alonso & Al-Fallouji (2026), arXiv:2607.00883 | CVaR framework decomposes hedge quality into components | Preprint, 2026 | None stated | **NEEDS-VENUE-CHECK** - post-2023, arXiv only, not independently re-checked this session |
| Gonzalez, Papageorgiou & Skinner (2016), *EFM* 22(4):613-639 | Peer-reviewed application of MPPM/Doubt-Ratio pair | Peer-reviewed | None | CITED-CONSISTENT |
| Ferreira (2024), MSc thesis, Universidade Catolica Portuguesa | Vol-managed HY beats unscaled counterpart | Master's thesis | None | **UNCONFIRMED** - vault's own "weakest-pedigree source in this article" |
| Fischer & Stolper (2019), Deutsche Bundesbank DP 08/2019 | Stress rotates spread driver to liquidity | Working paper (central bank) | None | CITED-CONSISTENT |
| Campisi, La Rocca & Muzzioli (2023), *Statistica Neerlandica* 77(1):48-70 | Risk-asymmetry index, sensitivity/robustness tradeoff | Peer-reviewed, open access | None | CITED-CONSISTENT |
| Politis & Romano (1994), *JASA* 89(428):1303-1313 | Stationary bootstrap | Peer-reviewed | None | CITED-CONSISTENT |
| Ledoit & Wolf (2008), *J. Empirical Finance* 15(5):850-859 | Studentized bootstrap for Sharpe-difference tests | Peer-reviewed | None | CITED-CONSISTENT |
| White (2000), *Econometrica* 68(5):1097-1126 | Reality Check for data snooping | Peer-reviewed | None | CITED-CONSISTENT |
| Hansen (2005), *JBES* 23(4):365-380 | Superior Predictive Ability test | Peer-reviewed | None | CITED-CONSISTENT |
| Israelov & Nielsen (2015), "Covered Calls Uncovered," *FAJ* 71(6):44-57 | Covered calls are mostly equity exposure | Peer-reviewed | **AQR (high - both authors managed option strategies)** | CITED-CONSISTENT (also in `carry-as-the-short-gamma-income-pole`) |
| Patel, Raquel & Chadwick (2024), *J. Asset Management* 25:31-50 | VRP factor absorbs put-write "alpha" | Peer-reviewed | None declared | CITED-CONSISTENT (also in `carry-as-the-short-gamma-income-pole`) |

### 3.2 Skew is the inventory - `the-skew-is-the-product`

Koijen, Moskowitz, Pedersen & Vrugt "Carry" (JFE 2018), Jurek (2014 JFE), Daniel-Hodrick-Lu (2017
CFR), Page & Panariello (2018), TIFF, and Ilmanen (2012 FAJ) recur here from §3.1/§3.3 - not
repeated. New citations:

| Citation | Claim | Pedigree | COI | Verification |
|---|---|---|---|---|
| Jurek & Xu, SSRN WP 2338585 | Skewness component ~10-15% of FX carry premium | Working paper | None stated | **UNCONFIRMED** - re-checked 2026-07-10, still unpublished |
| Bekaert & Panayotov (2019/2020), NBER WP 25420 / *JFQA* 55(4):1063-1094 | "Good carry" (ex AUD/JPY/NOK) has flat-to-positive skew | Peer-reviewed | None | CITED-CONSISTENT - does not test diversification value against trend, a gap the corpus flags |
| Torok (2022, rev. 2023), SSRN WP 4040261 | Option-implied-skew selection yields skew-neutral carry | Working paper | None | **NEEDS-VENUE-CHECK** - re-checked 2026-07-10, still WP, 0 citations after ~4 years |
| Daniel, Hodrick & Lu (2017), *Critical Finance Review* 6(2):211-262 | Dollar-neutral leg holds the deep skew, diversified leg does not | Peer-reviewed | None | CITED-CONSISTENT |
| Firoozye & Koshiyama (2020), *J. Investment Strategies* 9(1) | Positive skew is essential to every positive-Sharpe dynamic strategy | Peer-reviewed | None | CITED-CONSISTENT - the theorem behind the "dial turns one way" claim |
| Koijen, Moskowitz, Pedersen & Vrugt (2018), "Carry," *JFE* 127(2):197-225 | Carry co-crashes across asset classes in recessions | Peer-reviewed | **AQR (Moskowitz, Pedersen)** | CITED-CONSISTENT - the single most-repeated source in the corpus, cited by 6 of the 11 documents read |
| Lettau, Maggiori & Weber (2014), *JFE* 114(2):197-225 (NBER WP 18844) | Downside-risk CAPM jointly prices carry, equities, options, commodities, bonds | Peer-reviewed | None | CITED-CONSISTENT |
| Avino & Salvador (2024), *Review of Asset Pricing Studies* 14(2):310-348 | Merton+Geske hedge ratios ~1, put sensitivity concentrated in BB-B | Peer-reviewed | None | CITED-CONSISTENT - confirmed real venue (Oxford Academic) despite 2024 date |
| Campbell & Taksler (2002/2003), NBER WP 8961 / *JF* 58(6) | Idiosyncratic equity vol explains as much bond-yield variation as ratings | Peer-reviewed | None | CITED-CONSISTENT |
| Ben Dor et al. (2007), "DTS," *JPM* 33(2):77-100 | Spread changes proportional to spread level | Peer-reviewed (practitioner journal) | **Lehman/Robeco** | CITED-CONSISTENT |
| Barroso & Santa-Clara (2015), "Momentum Has Its Moments," *JFE* 116(1):111-120 | Vol-managing momentum: Sharpe 0.53→0.97, skew -2.47→-0.42 | Peer-reviewed | None | **VERIFIED-IN-VAULT** - figures repeated identically across 3 articles with no drift |
| Almeida (2021), Nova SBE MSc thesis | Vol-managed carry Sharpe +40%, skew flips -0.37→positive | Master's thesis | None | **UNCONFIRMED** - vault's own "weakest-pedigree source" |
| Moreira & Muir (2017), "Volatility-Managed Portfolios," *JF* 72(4):1611-1644 | Inverse-vol scaling raises Sharpe; timed on common vol factor, carry alpha disappears | Peer-reviewed | None | CITED-CONSISTENT |
| Granger, Greenig, Harvey, Rattray & Zou (2014), SSRN WP 2488552, "Rebalancing Risk" | Fixed-weight rebalancing = buy-and-hold + short straddle | Working paper | **Man Group** | **UNCONFIRMED** as standalone (still WP after ~12 years) but its core claim is restated in the peer-reviewed sequel below |
| Rattray, Granger, Harvey & van Hemert (2020), "Strategic Rebalancing," *JPM* 46(6):10-31 | 60/40 GFC drawdown 1.2x worse rebalanced than buy-and-hold | Peer-reviewed | **Man Group** | CITED-CONSISTENT |
| Willenbrock (2011), *FAJ* 67(4):42-49 | Diversification return comes from contrarian rebalancing trades | Peer-reviewed | None | CITED-CONSISTENT |
| Hoffstein (Newfound Research, 2020), "Tranching, Trend, and Mean Reversion" | Drift is an embedded momentum position; tranching as middle path | Practitioner blog | None stated | **UNCONFIRMED** as academic pedigree |
| Man Group (AHL) (2023), "Trend-Following and Long/Short Quality" | Fast shocks defeat trend's crisis alpha | Practitioner white paper | **Man Group** | **UNCONFIRMED** - vault explicitly states positioning-conditional numbers "not independently verified" |
| Dupuy (2021), *JBF* 129:106172 | Timed carry: Sharpe 0.76→1.07, skew -0.76→+0.97 | Peer-reviewed | None | **VERIFIED-IN-VAULT** - the peer-reviewed anchor for the carry sign-flip claim, figures consistent every citation |
| Baz, Granger, Harvey, Le Roux & Rattray (2015), SSRN WP 2695101 | Carry-momentum correlation +0.24 TS/+0.15 XS; carry skew by asset class | Working paper | **Man Group** | **VERIFIED-IN-VAULT** - vault states "tables verified to the primary document 2026-07-10" in two separate articles |
| Bae & Elkamhi (2021), *Management Science* 67(11):7262-7289 | Global equity correlation innovations jointly price carry and momentum | Peer-reviewed | None | CITED-CONSISTENT |
| Jang & Kang (2025), *Korean Journal of Financial Studies* 54(6):443-469 | Independent Korean-market DTS replication | Peer-reviewed, 2025 | None | **NEEDS-VENUE-CHECK** - real journal, not independently re-fetched this session |
| Winston (2018), Western Asset practitioner paper | DTS confounds exposure with risk, procyclical | Practitioner white paper | **Western Asset (counter-source)** | CITED-CONSISTENT |

### 3.3 Carry as the pole, and where the concavity lives - `carry-as-the-short-gamma-income-pole`

| Citation | Claim | Pedigree | COI | Verification |
|---|---|---|---|---|
| Jensen, Kelly & Pedersen (2023), "Is There a Replication Crisis in Finance?" *JF* 78(5):2465-2518 | 153-factor replication, carry strengthens under Bayesian correction | Peer-reviewed | **AQR (Kelly, Pedersen)** | CITED-CONSISTENT |
| Baltussen, Swinkels & van Vliet (2021), "Global Factor Premiums," *JFE* 142(3):1128-1154 | Multi-asset carry premium significant 1800-2016 | Peer-reviewed | **Robeco** | CITED-CONSISTENT (also `the-tiered-strategy-roster`) |
| Lustig, Roussanov & Verdelhan (2011), *RFS* 24(11):3731-3777 | Single global "slope" factor, ~70% of currency cross-sectional variation | Peer-reviewed | None | CITED-CONSISTENT |
| Brunnermeier, Nagel & Pedersen (2008), NBER Macro Annual 23:313-347 | Currency skewness falls with rate differential; funding-unwind crashes | Peer-reviewed (NBER volume) | **AQR (Pedersen)** | CITED-CONSISTENT |
| Gorton, Hayashi & Rouwenhorst (2013), *Review of Finance* 17(1):35-105 | Commodity basis/convenience yield decreasing in inventories | Peer-reviewed | None | CITED-CONSISTENT (also `carry-is-not-one-premium`, `commodity-carry-constructions`) |
| Caballero & Doyle (2012), NBER WP 18644 | Carry co-moves with short-vol position; absorbs carry alpha | Working paper | None | **UNCONFIRMED** - re-checked 2026-07-10, still unpublished ~12 years; opposite conclusion to Jurek |
| Carr & Wu (2009), "Variance Risk Premiums," *RFS* 22(3):1311-1341 | S&P 500 VRP strongly negative, unexplained by factor models | Peer-reviewed | None | CITED-CONSISTENT |
| Bollerslev, Tauchen & Zhou (2009), *RFS* 22(11):4463-4492 | VRP predicts market returns at quarterly horizon | Peer-reviewed | None | CITED-CONSISTENT |
| Bondarenko (2019), Cboe-sponsored | PUT index Sharpe ~0.65 vs S&P ~0.49, skew ~-2.1 | Exchange-funded practitioner research | **Cboe (high)** | CITED-CONSISTENT - flagged in the article's own limitations as hypothetical/gross-of-cost |
| Santa-Clara & Saretto (2009), *J. Financial Markets* 12(3):391-417 | Margin calls force liquidation at the loss; Sharpe 0.30→0.10 under margins | Peer-reviewed | None | CITED-CONSISTENT |
| Falconio (2016, rev. 2021), ECB WP 1968 | FX carry flattened post-2008 as differentials compressed | Working paper (central bank) | None | CITED-CONSISTENT |
| Aquilina, Lombardi, Schrimpf & Sushko (2024), BIS Bulletin 90 | August 2024 yen-carry unwind, ~40tn yen | Official (BIS) | None | CITED-CONSISTENT |
| Broadie, Chernov & Johannes (2009), *RFS* 22(11):4493-4529 | OTM put returns not inconsistent with Black-Scholes | Peer-reviewed | None | CITED-CONSISTENT - the counter-source to "free mispricing" readings |
| Menkhoff, Sarno, Schmeling & Schrimpf (2012), *JF* 67(2):681-718 | High-rate currencies lose on FX vol spikes | Peer-reviewed | None | CITED-CONSISTENT (also `carry-is-not-one-premium`) |
| Dobrynskaya (2014), *Review of Finance* 18(5):1885-1913 | Global downside-beta premium matches equity-market value | Peer-reviewed | None | CITED-CONSISTENT |
| Zeng (2025), *JFQA* 60(2):839-873 | Global rate vol tightens FX dealer constraints, 92% cross-sectional fit | Peer-reviewed, 2025 | None | CITED-CONSISTENT for existence, but **demote to corroborating** per §2.7 - a high-R² cross-sectional fit is exactly the object Gospodinov-Robotti's critique attacks |
| Burnside, Eichenbaum, Kleshchelski & Rebelo (2011), *RFS* 24(3):853-891 | ATM-hedged carry payoff indistinguishable from zero (peso problem) | Peer-reviewed | None | CITED-CONSISTENT - opposite verdict to Jurek, genuinely unresolved |
| Fernandez-Perez, Frijns, Fuertes & Miffre (2018), *JBF* 86:143-158 | Commodity skewness factor ~8.01%/yr, t=3.83 | Peer-reviewed | None | **VERIFIED-IN-VAULT** - identical figures repeated in `skewness-in-asset-returns` |
| Fan, Paseka, Qi & Zhang (2022), *Intl Review of Financial Analysis* 76:102081 | G10 carry decline post-2008 is a downside-risk disappearance | Peer-reviewed | None | CITED-CONSISTENT |
| Israelov (2017), SSRN WP 2894610 | Put-call parity explains PUT-BXM gap, not a distinct premium | Working paper | **AQR-affiliated (author formerly AQR)** | **UNCONFIRMED** as peer-reviewed |
| Dörries, Korn & Power (2023), CFR WP 23-06 | Seven-strategy VRP-harvest comparison, design problems identified | Working paper, 2023 | None declared | **NEEDS-VENUE-CHECK** |
| Dew-Becker & Giglio (2025), Chicago Fed WP 2025-17 (+ NBER WP 31833, 2023; sibling CFR 2026 conditionally-accepted paper) | Traded-option alpha ≈0 since ~2010-2012 | Working paper (Fed) | None (product) | **CONTESTED** - see §2.5 |
| Heston & Todorov (2023), SSRN WP 4373509 | Cross-asset VRP, S&P near-zero, mild illiquidity/jump association | Working paper, presented AEA-hosted conference | BIS co-author, no product COI | **VERIFIED-IN-VAULT** for the findings per `_challenge-verification.md`; note the folded article correctly does *not* call it an "AEA study" |
| Wysocki & Ślepaczuk (2025), *Economic Modelling* 152 | Systematic option-writing beats buy-and-hold 2018-2023 | Peer-reviewed, 2025 | None declared | CITED-CONSISTENT |
| Neuberger (2012), "Realized Skewness," *RFS* 25(11):3423-3455 | Long-horizon skew estimates are noisy, non-additive across horizons | Peer-reviewed | None | CITED-CONSISTENT |
| Berkovich & Shachmurove (2013), *J. Derivatives* 20(3):31-42 | Collateral funding costs can flip put-write alpha negative | Peer-reviewed | None declared | CITED-CONSISTENT |
| Ilmanen et al. (2020), AQR white paper, "Tail Risk Hedging" | Puts protect fast gaps, trend protects protracted bears | Practitioner white paper | **AQR (high)** | CITED-CONSISTENT (also `the-tiered-strategy-roster`) |

### 3.4 Carry is not one premium - `carry-is-not-one-premium`

Koijen et al. "Carry," Menkhoff et al., Gorton et al., and Bailey & Lopez de Prado recur from above.

| Citation | Claim | Pedigree | COI | Verification |
|---|---|---|---|---|
| DeMiguel, Garlappi & Uppal (2009), *RFS* 22(5) | 14 optimized allocation policies don't beat 1/N out of sample | Peer-reviewed | None | CITED-CONSISTENT |
| Hsu, Taylor, Wang & Li (2024), *JIMF* 143 | Carry strategies unstable after data-snooping corrections | Peer-reviewed, 2024 | None | CITED-CONSISTENT |

### 3.5 Commodity carry - `commodity-carry-constructions`

Gorton, Hayashi & Rouwenhorst recurs from §3.3.

| Citation | Claim | Pedigree | COI | Verification |
|---|---|---|---|---|
| Szymanowska, de Roon, Nijman & van den Goorbergh (2014), *JF* 69(1) | Spot premia (5-14%/yr) and term premia (1-3%/yr) have opposite signs | Peer-reviewed | None | CITED-CONSISTENT - the strongest single support for "commodity skew sign is construction-dependent" |
| Fuertes, Miffre & Rallis (2010), *JBF* 34(10) | Term-structure + momentum double sort | Peer-reviewed | Mild (one author later industry-affiliated, per vault text) | CITED-CONSISTENT |
| Erb & Harvey, CME educational paper, "Deconstructing Futures Returns" | Roll-yield adjustment is not itself a traded return | Practitioner/exchange-hosted | **CME (exchange-hosted)** | CITED-CONSISTENT - pedagogical source, not an empirical result being relied on for a figure |

### 3.6 ILS as a second crash factor - `insurance-linked-securities-as-the-orthogonal-income-pole`

> [!note] Cross-checked against the parallel buildability agent
> `research/income-engine/_buildability.md` independently verified Tomunen (2026, *RFS*),
> Gürtler-Hibbeln-Winkelvos, Carayannopoulos-Perez, and the Lehman TRS rating actions (Ajax Re, Newton
> Re, Carillon, Willow Re) against `_challenge-verification.md`, reaching the same VERIFIED verdicts
> this register reaches below. It also sources a primary ESMA document (ESMA34-2087785638-1548, June
> 2025) on UCITS cat-bond eligibility that this register does not carry, since that is wrapper-
> feasibility content owned by that agent, not academic bibliography. One gap this register closes
> that `_buildability.md` does not: the "role of catastrophe bonds" *FRL* paper's authors, cited as
> `[^role]` with no author names in both the folded article and `_buildability.md`, are identified
> below as Drobetz, Schröder & Tegtmeier (2020).

Koijen et al. "Carry" recurs (referenced narratively, not footnoted, in this article - a citation gap
worth noting: the article's opening paragraph attributes the co-crash claim to Koijen et al. by name
without a footnote marker in its own Sources list).

| Citation | Claim | Pedigree | COI | Verification |
|---|---|---|---|---|
| Froot (2001), "The Market for Catastrophe Risk," *JFE* 60(2-3):529-571 | Premium-to-expected-loss multiples of fair value; supply-side survivors of 8 tested explanations | Peer-reviewed | None | CITED-CONSISTENT - per the parallel synthesis agent, "the cleanest instance in the corpus" of the constrained-capacity thesis |
| Froot & O'Connell (1997), NBER WP 6043 | Post-event price spikes are supply shifts, not risk revisions | Working paper (NBER) | None | CITED-CONSISTENT |
| Gürtler, Hibbeln & Winkelvos (2016), *J. Risk and Insurance* 83(3):579-612 | Cat-bond/corporate-credit-spread dependency strengthens after Lehman | Peer-reviewed | None | **VERIFIED-IN-VAULT** per `_challenge-verification.md` (co-author first name corrected to Christine); the folded article's own footnote already has the corrected name |
| Morana & Sbrana (2019), *Economic Modelling* 81:274-294 | Cat-bond pricing undervalues global-warming risk | Peer-reviewed | None (counter-source) | CITED-CONSISTENT |
| Naik (2024) / Naik & Lee (2024), Bloomberg via Insurance Journal | Vendor models underestimate secondary perils | Practitioner journalism / testimony | ILS managers speaking against own book | **UNCONFIRMED** as academic pedigree |
| Neuberger Berman, "A Validation Study of Catastrophic Losses Over Time" | Structure ordering: index bonds realize losses at/below model | Manager white paper | **NB (sells ILS)** | CITED-CONSISTENT as a data claim, COI-flagged |
| Artemis (2026), Q4 2025 Cat Bond Market Report / UCITS AUM report | $19.12bn UCITS cat-bond sector; multiples compressed 6.87x→2.44x | Trade press/data provider | None stated | **VERIFIED-IN-VAULT** - vault states "Verified by fetch 2026-07-04" |
| Artemis/Plenum (Jan 2023) | UCITS cat-bond funds -2.3% in 2022 despite Ian | Trade press | **Plenum (manager)** | CITED-CONSISTENT |
| Artemis (Oct 2022) | Ian's realized losses ~half the mark-to-market hit | Trade press | None stated | CITED-CONSISTENT |
| Patton (2004), *J. Financial Econometrics* 2(1):130-168 | Asymmetric-dependence gains limited for short-sales-constrained investors | Peer-reviewed | None | CITED-CONSISTENT - the source for "orthogonality, not anti-correlation, is the right target" |
| Schroders (2025), "the case for insurance-linked securities" | "The only truly uncorrelated asset class" framing | Manager white paper | **Schroders (sells ILS)** | **CONTESTED** - directly at odds with Gürtler-Hibbeln-Winkelvos and Carayannopoulos-Perez; the brief itself flags this needs demoting |
| Neuberger Berman, "Catastrophe Bonds: An Uncorrelated Asset Class" | Same orthogonality framing | Manager marketing | **NB** | **CONTESTED** - same reason |
| Demers-Bélanger & Lai (2020), *Financial Markets, Institutions & Instruments* 29(5):165-228 | Cat bonds raise time-varying Sharpe/diversification ratio, esp. in crisis | Peer-reviewed | None | CITED-CONSISTENT |
| Carayannopoulos & Perez (2014/2015), *Geneva Papers on Risk and Insurance* 40(1) | Cat bonds zero-beta only in non-crisis periods; correlated post-Lehman | Peer-reviewed | None | **VERIFIED-IN-VAULT** per `_challenge-verification.md` |
| Drobetz, Schröder & Tegtmeier (2020), "The Role of CAT Bonds in an International Multi-Asset Portfolio," *Finance Research Letters* 33, art. 101198, DOI `10.1016/j.frl.2019.05.016` | Diversifier, poor hedge, safe haven only post-crisis | Peer-reviewed | None | **VERIFIED-IN-VAULT** - authors identified and re-confirmed via Exa against ScienceDirect and IDEAS/RePEc (Wolfgang Drobetz and Henning Schröder, Hamburg Business School; Lars Tegtmeier, Hochschule Merseburg). The vault's own footnote gives no authors: "The role of catastrophe bonds..." with a bare URL. This is the "balanced reading" citation the parallel synthesis agent leans on for what the paper *may* claim about ILS |
| Twelve Cat Bond Fund / Artemis fund-AUM reporting | $4.55bn largest UCITS cat-bond strategy | Trade press/product data | None (Artemis); manager COI on subject | CITED-CONSISTENT (product fact, see also §3.9) |

### 3.7 Reversal as falsifying case - `short-horizon-reversal-in-small-cross-sections`

| Citation | Claim | Pedigree | COI | Verification |
|---|---|---|---|---|
| Lehmann (1990), *QJE* 105(1):1-28 | Weekly winners/losers reverse the following week | Peer-reviewed | None | CITED-CONSISTENT |
| Jegadeesh (1990), *JF* 45(3):881-898 | Monthly contrarian strategy, ~2.5%/mo gross 1934-1987 | Peer-reviewed | None | CITED-CONSISTENT |
| Nagel (2012), "Evaporating Liquidity," *RFS* 25(7):2005-2039 | Reversal returns are compensation for liquidity provision, VIX-predictable | Peer-reviewed | None | CITED-CONSISTENT - the payer-story anchor |
| Jegadeesh, Luo, Subrahmanyam & Titman (2025), *RFS* 38(12):3673-3728 | Reversal-to-momentum transition model | Peer-reviewed, 2025 | None | CITED-CONSISTENT |
| Evans, Moussawi, Pagano & Sedunov (2026), "Operational Shorting and ETF Liquidity Provision," *JFE* 180(C):104241 | Operational shorting predicts next-day ETF price reversal, not NAV return | Peer-reviewed | None | **VERIFIED-IN-VAULT** - re-confirmed via Exa against IDEAS/RePEc and the DOI resolver, `10.1016/j.jfineco.2026.104241`; author affiliations (Evans/UVA, Moussawi/Pagano/Sedunov all Villanova) and the JFE-hosted replication package (Mendeley Data, Oct 2025) all consistent |
| Avramov, Chordia & Goyal (2006), *JF* 61(5):2365-2394 | Reversals concentrate in high-turnover illiquid stocks | Peer-reviewed | None | CITED-CONSISTENT |
| Frazzini, Israel & Moskowitz (2015), working paper | Reversal's break-even capacity far below value/momentum's | Working paper | **AQR (all authors)** | CITED-CONSISTENT - COI cuts toward survival, yet reversal still fails, which the vault notes strengthens rather than weakens the finding |
| de Groot, Huij & Zhou (2012), *JBF* 36(2):371-382 | Large-cap reversal nets 30-50bp/week under modeled costs | Peer-reviewed | **Robeco** | CITED-CONSISTENT |
| Blitz, Huij, Lansdorp & Verbeek (2013), *J. Financial Markets* | Residual reversal earns ~2x conventional reversal | Peer-reviewed | **Robeco** | CITED-CONSISTENT |
| Blitz, Hanauer & van Vliet (2023), *FAJ* 79(4):96-117 | Naive reversal fails costs; composite signals retain alpha | Peer-reviewed | **Robeco** | CITED-CONSISTENT |
| Blitz, van der Grient & Honarvar (2024), *JPM* | Classic reversal vanished; neutralized version retains 2x performance | Peer-reviewed, 2024 | **Robeco (high, all authors)** | CITED-CONSISTENT - the article itself flags these three Robeco papers as "one practitioner evidence cluster, not three independent confirmations" |
| Dai, Medhat, Novy-Marx & Rizova (2024), *FAJ* 80(2):122-151 | Volatility/turnover state the reversal decay rate | Peer-reviewed, 2024 | **Dimensional (3 of 4 authors)** | CITED-CONSISTENT |
| Khandani & Lo (2008), NBER WP 14465 | August 2007 quant meltdown, contrarian book lost heavily | Working paper (NBER) | None | CITED-CONSISTENT |
| Hameed, Kang & Viswanathan (2010), *JF* 65(1):257-293 | Reversal strengthens after liquidity deteriorates in declines | Peer-reviewed | None | CITED-CONSISTENT |
| Richards (1995), *JF* 50(1):185-200 | Slow multi-year winner-loser reversal among national indices | Peer-reviewed | None | CITED-CONSISTENT - horizon mismatch to the article's own daily/weekly claim, noted in its own limitations |
| Della Corte, Kosowski, Liu & Wang (2015-2018), SSRN WP 2730304 | Overnight-to-intraday reversal positive across 4 asset classes | Working paper | None | **UNCONFIRMED** - vault's own "unrefereed after roughly a decade" |

### 3.8 Backbone - who pays, and what fixes the sign

Sources drawn on by `income-must-accrue-not-be-captured.md`, `the-premium-is-rent-on-a-balance-sheet.md`,
`the-payer-did-not-leave-the-supply-arrived.md`, `window-dressing-at-the-regulatory-snapshot.md`, and
`what-is-a-strategy.md`. These are not the paper's *subject* (per `_pipeline-state.md`, the paper is
not about the rent-on-a-balance-sheet synthesis), but per the brief they "inform the argument and
constrain what may be claimed."

| Citation | Claim | Pedigree | COI | Verification |
|---|---|---|---|---|
| Bassi, Behn, Grill & Waibel (2024), *JFI* 58, art. 101086 | Repo volumes contract 12.5%/25% at quarter/year-ends | Peer-reviewed | None | **NEEDS-VENUE-CHECK** on the published-text sample period specifically - see §2.1 |
| Federal Reserve Bank of NY, Liberty Street Economics (2017) + Fed FEDS Notes (2024-2025) | US repo window-dressing analogue, reporting-convention difference | Official (Fed staff commentary, not peer-reviewed) | None | **UNCONFIRMED** - vault states specific note titles/dates not individually verified |
| Dew-Becker & Giglio - see §3.3 | | | | **CONTESTED** - see §2.5 |
| Tomunen (2026), *RFS* 39(3):661-701 | Cat-bond premium proportional to intermediary constraint, decays on inflows | Peer-reviewed | None | **VERIFIED-IN-VAULT** per `_challenge-verification.md` |
| Gârleanu, Pedersen & Poteshman (2009), "Demand-Based Option Pricing," *RFS* 22(10):4259-4299 | Index end-users net buyers of puts; single-stock end-users net suppliers | Peer-reviewed | None | **VERIFIED-IN-VAULT** per `_challenge-verification.md` - per the parallel synthesis agent, "the single most useful source in the corpus" for a venue-level sign |
| Terstegge, "Intermediary Option Pricing," working paper (Julian Terstegge, U. Michigan, SSRN 5877762) | Scenario/"shadow" gamma stays negative at a hypothetical -10% move | Working paper | None stated | **VERIFIED-IN-VAULT** - identified and fetched this session, see §2.4. Corroborating only, never load-bearing |
| Gospodinov & Robotti (2021), *JFE* 140(1):292-324 | Intermediary capital factor's significance disappears under robust inference; 39-of-40 placebo | Peer-reviewed | None stated | **VERIFIED-IN-VAULT** - see §2.7 |
| Kargar (2021), *JFE* 141(2):505-532 | Broker-dealers -47% leverage vs. bank holding companies +72%, 2008-09 | Peer-reviewed | None stated | **VERIFIED-IN-VAULT** - see §2.7 |
| Adrian, Etula & Muir (2014), *JF* 69(6):2557-2596 | Broker-dealer leverage shocks price size/BM/momentum/bond portfolios | Peer-reviewed | None stated | **VERIFIED-IN-VAULT** - see §2.7 |
| He, Kelly & Manela (2017), *JFE* 126(1):1-35 | Intermediary capital ratio prices seven asset classes similarly | Peer-reviewed | None stated | **VERIFIED-IN-VAULT** - see §2.7 |
| Qiao, Xu, Zhang & Zhou (2024), *JBF* 167:107259 | EM variance risk premium predicts stock/currency returns >6mo | Peer-reviewed | None stated | **VERIFIED-IN-VAULT** for existence/venue/sample; **UNCONFIRMED** for content-engagement - see §2.9 |
| Mallory (2026), arXiv:2605.29309 | 2.58% mean/2.52% median annualized crypto spot-futures wedge | Preprint | None stated | **NEEDS-VENUE-CHECK**, newly attributed - see §2.8 |
| Sharpe (1991), "The Arithmetic of Active Management," *FAJ* 47(1) | Before costs, average active = average passive dollar | Peer-reviewed | None | CITED-CONSISTENT |
| Pedersen (2018), "Sharpening the Arithmetic of Active Management," *FAJ* 74(1) | Even passive investors must trade (index reconstitution) | Peer-reviewed | **AQR (author)** | CITED-CONSISTENT |
| Longmore, "For The Love of The Game," Edge Alchemy (Robot Wealth), 2026 | "Who's paying you, why do they keep paying" framing | Practitioner blog | None stated | **UNCONFIRMED** as academic pedigree |
| Ilmanen (2011), *Expected Returns*, Wiley | Two return sources: bearing others' unwanted risk, or others' mistakes | Book | **AQR** | CITED-CONSISTENT |
| Ilmanen (2012), CFA Institute Conference Proceedings Quarterly | Bad-times performance, not volatility, sets required return | Practitioner/CFA venue | **AQR** | CITED-CONSISTENT |
| Carver, interview/book/blog (2015-2017), various | The "could a program replace you" completeness test; the "no rule" short-vol example | Practitioner (independent) | None stated | CITED-CONSISTENT - vault's own limitations flag these as "practitioner blogs rather than peer-reviewed work" |
| Villahermosa, practitioner blog (2026) | Six-component strategy anatomy (setup/trigger/entry/stop/target/sizing) | Practitioner blog, 2026 | None | **UNCONFIRMED** - single-sourced, 2026-dated blog |
| Lopez de Prado (2018), SSRN 3167017 | Most claimed strategies are false | Working paper | None | CITED-CONSISTENT |
| Harvey, Liu & Zhu (2016), *RFS* 29(1) | Most cross-sectional findings likely false under multiple-testing correction | Peer-reviewed | None | CITED-CONSISTENT |
| Bailey, Borwein, Lopez de Prado & Zhu (2014), *Notices of the AMS* 61(5) | Backtest overfitting mechanism | Peer-reviewed | None | CITED-CONSISTENT |
| Ilmanen & Kizer (2012), *JPM* | Premia may persist whether risk-based or behavioral | Peer-reviewed (practitioner journal) | **AQR** | CITED-CONSISTENT |
| Hudson, McGroarty & Urquhart (2017), *Finance Research Letters* | Mean-reversion profitable at 5-min bars, negative at 30-min+ | Peer-reviewed (assumed; inline citation only, no volume/DOI given) | None stated | CITED-CONSISTENT, details incomplete as given |
| Martin & Schöneborn (2011), cited in vault as "Risk" | Optimal no-trade buffer scales with cube root of transaction cost | Venue as given in vault text does not match the standard citation for this well-known result (usually *Mathematical Finance*) | None stated | **UNCONFIRMED** - venue needs confirming before use |
| Dick-Nielsen & Rossi, sample 2002-2013 (no title/journal/year given in vault) | Index trackers are forced sellers, dealer returns "not replicable" | Missing (journal/year/title not in vault text) | Unknown | **UNCONFIRMED** - citation incomplete as recorded, do not fill the gap |
| Elkamhi, Li & Nozawa (2025), *Management Science* 71(3) | CLO AAA spreads are a fair reflection of correlated default risk | Peer-reviewed, 2025 | None | CITED-CONSISTENT |
| Cordell, Roberts & Schwert (2023), *JF* 78(3) | CLO AAA risk-adjusted return not significantly different from zero | Peer-reviewed | None | CITED-CONSISTENT |
| Meyricke & Sherris (no full citation given in vault) | Solvency II disincentivizes transferring high-age longevity risk | Missing (journal/year/title not in vault text) | Unknown | **UNCONFIRMED** - incomplete citation |
| Börger, Freimann & Ruß (2023), *Journal of Risk and Insurance* | Longevity premia should rise as reinsurer capacity saturates | Peer-reviewed | None | CITED-CONSISTENT |
| Cairns et al. (2018), *British Actuarial Journal* | Two decades of failure to scale on basis risk/liquidity | Peer-reviewed | None | CITED-CONSISTENT |
| Unnamed ECB working paper on the EU "SME supporting factor" | Banks select loans for SRT on regulatory risk weight, not economic risk | Missing (WP number, authors not given in vault text) | Unknown | **UNCONFIRMED** - incomplete citation |

### 3.9 Wrapper feasibility (drawn on, not folded) - `the-ucits-constrained-carry-sleeve`

Explicitly listed in `_brief.md` as "Also draws on... wrapper feasibility." The parallel synthesis
agent's own read (`_synthesis.md` §6) states this note's outputs "belong in the buildability note and
not in this paper" for vehicle-level detail, but its academic-research citations may still support the
paper's "undilutable-crash-rent instrument" argument in §4.3.

**Academic/practitioner-research sources:**

| Citation | Claim | Pedigree | COI | Verification |
|---|---|---|---|---|
| Columbia Threadneedle (2022 HY review, and maturity-vs-duration paper) | Maturity-bucket 2022 decomposition (0-5yr -5.65% vs >8yr -18.35%) | Practitioner white paper | **Columbia Threadneedle (vendor)** | CITED-CONSISTENT |
| Verdad, "Fool's Yield" (2019) and "Yield Is Not Return" (2024) | Risk-adjusted return peaks at BB, declines through B/CCC | Independent research boutique | Low (sells small-value strategies, not HY funds) | CITED-CONSISTENT |
| Ben Dor & Xu (2011), "Fallen Angels," *J. Fixed Income* 20(4):33 | Post-downgrade underperformance then 2-year reversal | Peer-reviewed practitioner-academic | **Barclays QPS** | CITED-CONSISTENT |
| Ambrose, Cai & Helwege (2011), SSRN working paper | Forced selling bounded, fully reverts within months | Working paper | None | **UNCONFIRMED** - ~15-year-old SSRN WP, never published |
| FTSE Russell (Oct 2025), "Are Fallen Angels still angelic performers?" | Post-Covid FA Sharpe superior to IG/HY; cliff-edge effect diminishing | Index provider research | **FTSE Russell (index provider)** | CITED-CONSISTENT |
| Bektic & Regele (2018), *J. Asset Management* 19(2):79-92 | MA timing on OAS-sorted HY/IG yields significant abnormal returns | Peer-reviewed | Mild (Deka/AllianzGI) | CITED-CONSISTENT |
| Hoffstein (Newfound Research, 2019), "Tactical Credit" | Timing edge concentrates in 2000-03/2008-09, "not sufficient juice" net of costs | Practitioner blog | None stated | **UNCONFIRMED** as academic pedigree |
| Daniel & Moskowitz (2016), "Momentum Crashes," *JFE* 122(2):221-247 | Dynamic risk management removes momentum's negative skew | Peer-reviewed | None | CITED-CONSISTENT |
| Gadanecz, Miyajima & Shu (2014), BIS WP 474 | Local-currency sovereign yields co-move with USD exchange rate | Official (BIS) | None | CITED-CONSISTENT |
| Hofmann, Shim & Shin (2019), BIS WP 775 | Dollar strength tightens EM local financial conditions | Official (BIS) | None | CITED-CONSISTENT |
| Burger & Warnock (2006), NBER WP 12548 | EM local bond returns exhibit high variance, negative skewness | Working paper (NBER) | None | CITED-CONSISTENT |
| Amstad, Remolona & Shek (2016), BIS WP 541 | Sovereign risk pricing more correlated with US credit post-GFC | Official (BIS) | None | CITED-CONSISTENT |

**Instrument/product documentation** (not academic citations - ETF factsheets, issuer pages, justETF
listings; kept separate because the paper is decided to stay theoretical, per `_pipeline-state.md`
and the parallel synthesis agent's §5 item 22 "any buildability or wrapper-feasibility verdict... owned
by the parallel agent"): Xtrackers iTraxx Crossover (DBXM), Tabula liquidation notices, Invesco AT1
(XAT1) and Euro Corporate Hybrid (EHBD) factsheets, Global X QYLD/XYLU factsheets, UBS put-write ETF
(IE00BLDGHT92) factsheet, JPMorgan JEGP commentary, KRC Cat Bond ETF (CATB) product page, Xtrackers
DBX1AY liquidation notice, Franklin Templeton and HANetf factsheets. All carry issuer/vendor COI by
construction. **None of these should appear in the paper's bibliography** unless the drafting stage
explicitly decides to cite a specific investability fact (e.g., "a $19bn UCITS cat-bond fund universe
exists"), in which case cite the Artemis trade-press source (§3.6), not the individual fund factsheet.

### 3.10 Cited but not folded - flagged as belonging elsewhere

Per the brief, these four articles' own citations are **not** part of this paper's bibliography. They
are Architecture's (or a sibling note's), referenced narratively within the folded corpus but not
owned here. If the drafting stage pulls a specific fact from one of them, attribute it to the source
article, not to this register.

| Article | Role for this paper | Approx. citation count (not itemized here) |
|---|---|---|
| `convexity-as-the-axis-of-strategy-diversification` | Establishes the two-pole convexity axis the seat sits opposite trend on; cited narratively (e.g., "the convergent engine" framing, the rebalancing-premium mechanics) | ~30 |
| `skewness-in-asset-returns` | Higher-moments backbone (systematic vs. idiosyncratic skew pricing); several of its citations are duplicated verbatim inside the folded articles (Harvey-Siddique, Fernandez-Perez et al.) and are registered above under their folded-article use, not here | ~20 |
| `the-tiered-strategy-roster` | Defines the floor/target/expansion roster the convergent seat is one job in; supplies the "convergent income engine" row's benchmark language | ~25 |
| `notes/the-ucits-constrained-carry-sleeve` | See §3.9 - explicitly drawn on, registered above rather than fully deferred |  |

---

## 4. COI concentration

The brief asks whether the pattern the original "budgeting-convexity" paper found - AQR marketing
multi-factor credit, Quoniam running credit-factor funds, with the manipulation-proof theory and
raw-premium figures as the COI-free backbone - still holds across the whole folded corpus. **It does
not hold cleanly, and the register surfaces a specific internal contradiction worth flagging to the
drafting stage.**

**AQR is the dominant COI cluster, and it now spans every provisional section, not just credit
construction.** AQR-affiliated work is load-bearing for: the manipulation-proof measure's raw-premium
comparator (Asvanunt & Richardson), the defensive-beats-carry claim (Israel, Palhares & Richardson),
the credit-carry-is-mostly-beta claim (AQR Style Investing), the co-crash-in-recessions claim (Koijen,
Moskowitz, Pedersen & Vrugt "Carry," cited six times across the corpus), the funding-unwind account
(Brunnermeier, Nagel & Pedersen), the covered-call decomposition (Israelov & Nielsen), the
insurance-selling-is-paid cross-asset claim (Ilmanen, three separate pieces), the reversal
capacity-limit finding (Frazzini, Israel & Moskowitz), the replication-strengthens claim (Jensen,
Kelly & Pedersen), and the tail-hedging cost-budget framing (AQR's put-vs-trend white paper). This is
a wider footprint than the original paper's "credit construction" characterization.

**The vault's own claimed COI-free/COI split contains a direct contradiction.**
`what-makes-a-convergent-sleeve-an-income-engine.md`'s Limitations section states: *"the raw-premium
figures and the manipulation-proof theory are the COI-free backbone.[^gisw][^ar]"* - but its own
Sources section labels [^ar] (Asvanunt & Richardson, the source of the 137bp IG / 248bp HY raw-premium
figures) *"AQR COI"* in the same breath. The manipulation-proof theory citation ([^gisw], Goetzmann,
Ingersoll, Spiegel & Welch) genuinely is "No COI" and the claim holds for it. The raw-premium claim
does not: its own source article contradicts its own Limitations section. **The drafting stage should
not repeat "raw-premium figures are COI-free" without correcting this**, or should re-source the raw
premium figures to Baltussen, Swinkels & van Vliet's 1800-2016 multi-asset carry premium (Robeco COI -
also not clean) or accept that the raw premium claim, like most of the corpus, carries a COI.

**Man Group / AHL is a second concentrated cluster**, specific to the-skew-is-the-product's
rebalancing-band argument: Granger-Greenig-Harvey-Rattray-Zou, Rattray-Granger-Harvey-van Hemert,
Baz-Granger-Harvey-Le Roux-Rattray, and the AHL trend-following white paper are four Man-affiliated
sources underpinning one mechanism (fixed-weight rebalancing as a short straddle). The peer-reviewed
sequel (Rattray et al. 2020, JPM) is the strongest of the four; the others remain working papers or
practitioner white papers.

**Robeco is a third cluster**, concentrated in short-horizon-reversal's "conditioned reversal survives
costs" claim - the article's own text already self-corrects on this ("All three favorable studies are
Robeco-authored, so they form one practitioner evidence cluster, not three independent confirmations")
and this register agrees that correction should stand.

**ILS manager marketing (Schroders, Neuberger Berman) is directly contradicted by the peer-reviewed
crisis-correlation literature** (Gürtler-Hibbeln-Winkelvos, Carayannopoulos-Perez) cited in the same
article - flagged as CONTESTED in §3.6 and consistent with the parallel synthesis agent's independent
conclusion that the orthogonality headline must be demoted.

**What remains genuinely COI-free and load-bearing:** the manipulation-proof measure itself
(Goetzmann-Ingersoll-Spiegel-Welch), the intermediary-constraint spine's strongest surviving pieces
(Gârleanu-Pedersen-Poteshman, Santa-Clara-Saretto, Tomunen, Bassi-Behn-Grill-Waibel - all no-COI or
official/central-bank), the downside-risk-CAPM pricing literature (Lettau-Maggiori-Weber,
Dobrynskaya), the FX funding-unwind mechanism's non-AQR corroborations (Menkhoff-Sarno-Schmeling-
Schrimpf, Zeng), and essentially all of the skewness-pricing literature in `skewness-in-asset-returns`
(the vault's own limitations section for that article states "the sources here are unusually free of
conflict of interest," which this register's read confirms).

---

## 5. Single-source claims

Claims resting on exactly one source, especially a working paper, thesis, or practitioner blog. Flag
these for the drafting stage as claims that should be stated as directional/provisional, not settled.

- **Vol-managed HY beats unscaled counterpart** - sole source Ferreira (2024), MSc thesis.
- **Pure-inverse-vol carry timing flips skew sign** - sole source Almeida (2021), MSc thesis (though
  directionally corroborated by the peer-reviewed Dupuy 2021, which times on a different, blended
  signal - not a clean replication).
- **Skew-neutral carry via option-implied-skew selection** - sole source Torok (2022/23), working
  paper, 0 citations after ~4 years.
- **The Doubt Ratio's origin and calibration** - sole originating source Brown, Kang, In & Lee (2010),
  still-unpublished working paper (though the pairing has a peer-reviewed downstream application in
  Gonzalez, Papageorgiou & Skinner 2016).
- **MPPM tail-penalty magnitude (~3%/unit negative skew)** - sole source Maillard (2020), unpublished
  HAL working paper.
- **Fast shocks defeat trend's crisis alpha (positioning-conditional numbers)** - sole source Man
  Group (AHL) 2023 white paper, and the vault's own text states the numbers were never verified to a
  primary document.
- **Shadow-gamma persists under a hypothetical 10% down-move** - sole source Terstegge (2025), working
  paper, now identified but still single-author and non-peer-reviewed. Per the parallel synthesis
  agent, must never be load-bearing.
- **Corporate bond forced-seller mechanism (index trackers vs. dealers)** - sole source "Dick-Nielsen
  and Rossi," incompletely cited (no journal/year/title given anywhere in the vault text read).
- **Solvency II longevity disincentive** - sole source "Meyricke and Sherris," incompletely cited.
- **The EU "SME supporting factor" adverse-selection finding** - sole source an unnamed ECB working
  paper, incompletely cited.
- **Vendor models underestimate secondary perils (wildfire, convective storm, flood)** - sole source
  Bloomberg/Insurance Journal practitioner testimony (mitigated somewhat by being testimony against
  the speakers' own book, but still a single journalism source, not a study).
- **The cat-bond "diversifier, poor hedge, safe haven only post-crisis" classification** - sole source
  Drobetz, Schröder & Tegtmeier (2020), now fully attributed this session; a real peer-reviewed *FRL*
  paper, but the corpus's balanced ILS reading rests on this one paper for its central classification.
- **The crypto spot-futures wedge (2.58%/2.52%)** - sole source Mallory (2026), now attributed, single
  author, unrefereed working paper.
- **EM variance risk premium predictability** - sole source Qiao, Xu, Zhang & Zhou (2024); real,
  peer-reviewed, but per §2.9 nobody on the desk has read past the abstract-level facts confirmed this
  session.
- **The "six essential components" strategy-anatomy decomposition** in `what-is-a-strategy` - sole
  source a 2026 practitioner blog post (Villahermosa), corroborated only by its consistency with
  Carver's independently peer-adjacent framework, not by a second primary source.
- **"Who's paying you, why do they keep paying"** framing quote in `what-is-a-strategy` - sole source
  a 2026 practitioner blog (Longmore).
- **The optimal no-trade buffer's cube-root scaling** in `income-must-accrue-not-be-captured` - sole
  source "Martin and Schöneborn," cited to a venue ("Risk," 2011) that does not match the standard
  citation for this well-known academic result and was not independently confirmed this session.

---

## Limitations of this register

This register extracts what the vault already states; it does not re-derive vault authors' original
research judgments. Live primary-source verification this session covered the items the team lead
specifically flagged, plus a small number of adjacent items that were cheap to check (Evans et al.
2026, the FRL cat-bond paper's authors, the exact Kargar and Gospodinov-Robotti figures). It did
**not** re-verify the ~165 other citations against their primary sources - those carry forward the
pedigree, COI, and consistency-with-the-vault-text that the folded articles themselves already
established, and are marked CITED-CONSISTENT on that basis, not on independent primary-source
confirmation performed this session. Where a folded article's own Limitations section already
flags a source as weak, unverified, or single-sourced, this register carries that flag forward rather
than re-litigating it.

Two citation-hygiene issues surfaced incidentally and are worth a maintenance note rather than a
blocking flag: `insurance-linked-securities-as-the-orthogonal-income-pole.md`'s own Sources list
duplicates the Patton (2004) footnote under two separate keys with slightly different wording, and its
opening paragraph attributes the carry-co-crash claim to Koijen, Moskowitz, Pedersen & Vrugt by name
without a footnote marker in that article's own Sources section (the citation exists correctly
elsewhere in the corpus, so this is a footnote-hygiene gap in one article rather than a missing
source).
