---
title: Sector-Family Promotion Campaign
date: "2026-06-11"
status: closed - promotion blocked at S3
tags:
  - campaign
---

# Sector-Family Promotion Campaign

Decides whether the sector-risk book replaces or joins the champion as the
deliverable. All gates below were written BEFORE any campaign run launched;
runs are logged in the daily diaries and link back here.

## The candidate book

- Risk block: XLK, XLY, XLP, XLV, XLI (the v30 five)
- Havens: TLT, GLD, UUP, DBC, XLE (the original block - the engine, per the
  v29-v32 crossed 2x2)
- Floor: UUP 0.3 (the insured variant is the deliverable-grade book)
- Mechanism and params inherited from the champion, NOT re-selected:
  tsmom lookback 252, vol window 30, core_wt 0.5, top_k 3, entry_band 0.0,
  breadth_norm 0.4, tau 0.15; component aegis.crisisBlendFamily, family
  "sector".

## Priors (already observed - this is the in-sample taint to manage)

- v30 (extended 2016-2025): floored composite **0.425** vs champion 0.255;
  bare 0.351 vs 0.151; 2018 split -0.77 vs champion-floored -1.09;
  worst-year drawdown 7.5%. Params inherited, so no new fitting - but the
  observation itself means the extended window is now peeked.
- v34 (GFC 2007-2016): floored composite 0.120 vs champion-equivalent 0.039;
  crisis-alpha gate failed for BOTH (the regime-flip blind spot is
  architecture-level, not universe-level).

## Data gates (verified 2026-06-11)

- All nine sector SPDRs (XLK/XLY/XLP/XLV/XLI/XLB/XLF/XLU/XLE) trade from
  1998-12-22.
- **Dot-com window is INFEASIBLE for the full book**: the haven block binds
  (TLT 2002-07, GLD 2004-11, DBC 2006-02, UUP 2007-03). 2007-03 stays the
  deepest full-book start; the GFC window is the only out-of-time crisis
  available. Recorded so nobody re-proposes the 2000-02 test without new
  haven proxies.

## The four risks this campaign must kill

1. **Param-inheritance luck** - the champion's params were selected on the
   champion universe; they might be accidentally optimal for sectors.
2. **Spec luck on the gate lookback** - the v28 failure mode; the 252d
   lookback must not uniquely carry the sector advantage.
3. **Universe-draw luck** - the v30 five is one draw of five from eight
   non-XLE sectors; the result must not live in that exact draw.
4. **Window taint** - both windows were peeked at inherited params. Managed
   by: no new param fitting on results (axis sweeps judge the INHERITED
   point, not pick winners), and the GFC window re-confirms any spec that
   changes.

## Stages and pre-registered gates

All runs: extended window 2016-01-01 to 2025-01-01 unless stated, floor_wt
0.3 pinned, ranking sharpe_ratio, grids <= 3 candidates, from_rolling
504/0.5 splits (held-out 2017..2023 as s0..s6).

### S1 - param-inheritance robustness (one axis per run, others pinned)

- v46 core_wt {0.3, 0.5, 0.7}
- v47 breadth_norm {0.0, 0.4, 0.7}
- v48 top_k {2, 3}
- v49 entry_band {0.0, 0.02}
- v50 tau {0.10, 0.15}
- **Gate per axis**: the inherited value's composite is within 0.05 of the
  axis best. If a different value wins by > 0.05 on some axis, the inherited
  point is flagged and S4 must re-run the GFC window at that axis's winner
  before any promotion talk (no chasing the winner on the peeked window
  alone). **Campaign kill**: the inherited point is worst on >= 2 axes by
  > 0.15 - that would mean v30 was a param accident.

### S2 - spec-luck floor on the gate lookback (the v28 discipline)

The claim under test is "sector book beats champion book", so the
comparison must be run at MATCHED lookbacks on both books:

- v51 sector @ lookback 63, v52 sector @ 126 (single-candidate runs)
- v53 original @ 63, v54 original @ 126 (champion universe via family
  "original", same floor 0.3)
- 252d pair already exists: sector 0.425 (v30) vs original 0.255 (v13c-
  equivalent baseline).
- **Gate**: sector floored composite > original floored composite at >= 2 of
  the 3 lookbacks (252 included). **Kill** if the advantage exists only at
  252d.

### S3 - universe-draw robustness (inherited params, floor 0.3)

- v55 alternate five: XLB, XLF, XLU, XLP, XLV (swaps three of five)
- v56 all-eight block: XLK, XLY, XLP, XLV, XLI, XLB, XLF, XLU
- **Gate**: each alternate block's floored composite > the champion's 0.255.
  **Kill** if only the exact v30 five clears it (draw luck); a partial pass
  (one of two) downgrades the claim from "sector risk is better" to "some
  sector draws are better" and blocks promotion.

### S4 - out-of-time confirmation

- If S1-S3 leave the inherited spec unchanged, v34 stands as the GFC
  evidence (floored 0.120, survival-grade).
- If any spec changed, re-run the GFC window at the final spec.
- **Gate**: GFC floored composite > 0 AND Lehman-split floored total return
  > -6% (v34's floored book printed ~-3%).

### S5 - promotion decision (mechanical, from the gates above)

PROMOTE the sector book to primary deliverable (champion demoted to
variant) only if ALL hold:

1. S1 passes with the inherited point robust on every axis;
2. S2 passes at >= 2 of 3 lookbacks;
3. S3 passes on BOTH alternate blocks;
4. S4 stands or re-confirms.

Any other outcome: champion stays primary. If S2 and S3 pass but S1 flags
an axis, the campaign pauses for a GFC re-confirmation rather than
promoting. If S2 or S3 kill, the v30 result goes to the graveyard as
draw/spec luck and the sector thread closes.

## Run log

- [x] S1: v46-v50 - **PASS on all five axes.** Inherited point within 0.05
  of the axis best everywhere (worst gap entry_band: 0.425 vs 0.468 =
  0.043; core_wt 0.033, top_k 0.021, breadth 0.024, tau 0.001). The
  inherited point sits on a plateau, not a peak - v30 was not a param
  accident. No winner-chasing: the better neighbors are noted, not taken.
- [x] S2: v51-v54 - **PASS at 2 of 3 lookbacks, with an honest asterisk.**
  252d: sector 0.425 vs original 0.255 (+0.17); 63d: 0.431 vs 0.405
  (+0.026, thin); 126d: 0.505 vs 0.544 (-0.039, original wins). The
  advantage's MAGNITUDE is 252d-concentrated even though the gate passes
  as written. Side observation recorded, not acted on (peeked window, would
  be new fitting): BOTH books improve at shorter lookbacks on 2016-2025.
- [x] S3: v55-v56 - **FAIL on the alternate five, PASS on all-eight.**
  Alt-five (XLB/XLF/XLU/XLP/XLV) floored composite 0.193 < 0.255; all-eight
  0.335 > 0.255. Per the pre-registered gate, a partial pass downgrades the
  claim to "some sector draws are better" and BLOCKS promotion. Mechanism
  note: the failing draw is exactly the financials + bond-proxy
  (XLF/XLU/XLB) tilt - the v30 five excludes the rate-sensitive sectors,
  which is plausibly the real content of its edge; all-eight still clearing
  shows the result is not pure draw luck.
- [x] S4: moot for promotion (S3 blocked) and no spec changed, so v34
  stands as the GFC evidence unchanged.
- [x] S5: **VERDICT - NOT PROMOTED. Champion stays primary.** The sector
  book is recorded as a validated VARIANT with a downgraded claim: a
  cyclicals-plus-staples sector draw (excluding financials and bond
  proxies) beats the champion universe on 2016-2025 at inherited params,
  robust to param axes, but the advantage is 252d-lookback-concentrated
  and not draw-universal. Graveyard row added for the promotion
  hypothesis. Run IDs: v46 20260611T121759279316Z, v47
  20260611T121823299374Z, v48 20260611T121846479836Z, v49
  20260611T121909418876Z, v50 20260611T121932543815Z, v51
  20260611T121955357643Z, v52 20260611T122018407135Z, v53
  20260611T122040945409Z, v54 20260611T122103837963Z, v55
  20260611T122126554027Z, v56 20260611T122149465878Z.

## What survives the block (recorded for future mechanism work)

- The rate-sensitivity thread: the failing alt-five loads on XLF/XLU/XLB.
  If a future article gives a mechanism for "exclude rate-sensitive and
  financial sectors from the risk sleeve of a crisis blend", the v30-vs-v55
  contrast is its ready-made first test.
- The lookback observation: on 2016-2025 both books prefer 63/126d gates to
  252d. Untouchable without a fresh window (this one is peeked twice over);
  a future standard-window or post-2025 evaluation could test it honestly.

## References

- Diary of record: [[2026-06-11]] (v30/v34 priors, this campaign's launch)
- Articles: crash-resistance-in-our-etf-universe (retired),
  [[when-conditioning-pays]] (the static-benchmark discipline),
  [[measuring-crisis-alpha]] (why floored composite, not Sharpe alone)
