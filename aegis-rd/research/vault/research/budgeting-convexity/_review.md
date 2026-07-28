---
title: "Budgeting Convexity - Stage 3 peer review"
paper: "Budgeting Convexity"
status: "Stage 3 peer review"
tags:
  - review
  - stage3
---

# Budgeting Convexity - Stage 3 peer review

Reviewer panel deliverable (`academic-paper-reviewer`, full mode: EIC + 3 peer reviewers + Devil's
Advocate, then editorial synthesis). Reviewed artifact: [[research/budgeting-convexity/_draft|_draft]].
Context read but not re-reviewed: [[research/budgeting-convexity/_outline|_outline]],
[[research/budgeting-convexity/_argument|_argument]], [[research/budgeting-convexity/_sources|_sources]],
[[research/budgeting-convexity/_integrity|_integrity]]. No changes were made to the draft.

## Reviewer configuration

| Seat | Identity | Focus |
|---|---|---|
| EIC | Editor overseeing *The Journal of Portfolio Management*'s portfolio-construction / risk-budgeting section | Journal fit, originality, significance, structural coherence |
| R1 (Methodology) | Research methodologist specializing in the epistemology of quantitative-finance claims (ex-ante rationale discipline, estimation-risk awareness); for this theoretical/integrative paper the seat is read per the skill's Edge Case 1 as argumentation-logic reviewer, not statistics reviewer | Argument-logic structure, counterargument handling, testability |
| R2 (Domain) | Senior academic in empirical asset pricing (higher-moment pricing, carry, trend/CTA literatures) | Literature coverage, theoretical-framework fit, claim-to-source fidelity |
| R3 (Perspective) | Multi-strategy CIO / head of portfolio construction at an institutional allocator | Implementation feasibility, governance/mandate friction, practitioner stakeholders |
| Devil's Advocate | Adversarial stress-tester, no fixed identity | Strongest counter-argument, logic gaps, evidence gaps |

Paper type: theoretical / integrative framework paper, quantitative finance / investment management,
target venue *The Journal of Portfolio Management*. Judged as a framework paper against its own
stated evidence standard (ex-ante economic rationale before any confirming backtest; the authors'
own runs/ADRs are estimate-tier illustration, never proof).

---

# Part 1: Individual Reviewer Reports

## EIC Review Report

### Overall Recommendation
Minor Revision

### Confidence Score
5 - fully within scope; JPM-style integrative portfolio-construction papers are the core of this seat's remit.

### Summary Assessment
The paper reframes multi-strategy diversification from "count low-correlated mechanisms" to "span an
order of operations over failure modes on the convexity axis," and defends three linked claims: the
axis is real and independently recovered, skew classifies the axis but cannot budget it, and the
resulting tiered roster should be realized by budgeting risk and sourcing convexity structurally
rather than by timing returns. Execution is strong: the pivot chapter (Ch3) is the best-argued section
in the manuscript, the paper discloses and triangulates past its own conflicts of interest, and the
integrative scope (three claims asserted here, proved by three forthcoming "seat" papers) is stated
honestly rather than hidden. Two chapters overclaim relative to their own evidence: Ch4's roster reads
as more derivationally forced than the cited literature can support, and Ch5's risk-conditioning /
return-timing boundary, which the paper itself calls its most contested line, needs a tighter defense.
Neither is a structural defect; both are addressable without rearchitecting the paper. Excellent fit
for the target venue, whose own back-catalog this paper largely synthesizes.

### Strengths

1. **Native fit for the venue's own literature**: nine of the paper's own citations (Grinold 1989;
   Choueifaty & Coignard 2008; Maillard, Roncalli & Teiletche 2010; Lopez de Prado 2016; Bhansali,
   Davis, Dorsten & Rennison 2015; Bhansali, Chang, Holdom & Rappaport 2020; Hurst, Ooi & Pedersen
   2017; Baltas & Salinas 2022; Israelov & Nielsen 2015) were themselves published in *JPM*. The paper
   reads as a genuine synthesis of a decade of that journal's own portfolio-construction literature
   into one coherent, actionable roster, which is exactly what this readership rewards.
2. **Stated falsifiability** (Section 6, "The limits..."): "If a role the roster asserts to be
   structurally convex were shown to earn its crisis payoff only when a price-based timing signal was
   applied, or if book-level net-skew budgeting were shown to add stable out-of-sample value after
   honest estimation, the order of operations defended here would have to be rebuilt." Few
   practitioner-facing framework papers name in advance the evidence that would refute them; this one
   does, twice, in one sentence.
3. **Self-aware conflict-of-interest handling**: the paper flags CFM, AQR, and PIMCO affiliations
   in-text at first use, triangulates the core axis claim with two no-COI, independent methods
   (Lettau, Maggiori & Weber, 2014; Bollerslev & Todorov, 2011), and confines its own trading system
   (aegis-trader ADR-0004 / allocator) to "labeled illustration only, never evidence" in two separate
   places in Section 5. That discipline pre-empts the obvious "this is marketing dressed as research"
   read of a practitioner-adjacent framework paper.

### Weaknesses

1. **W1: Ch4's roster reads as more derivationally forced than its evidence establishes.**
   **Problem**: Section 4.4 states the order "is not an aesthetic preference but the antidote to a
   documented failure" and that the roster "has a natural stopping point." The only evidence load-bearing
   enough to carry that claim, Brown, Gregoriou & Pascalau (2011), establishes that over-diversification
   past roughly twenty funds raises left-tail risk; it does not establish that a Floor-then-Target-then-
   gated-Expansion sequence specifically is the fix. R1 and the Devil's Advocate reach the same finding
   independently (see below).
   **Why it matters**: the roster (Ch4) is the paper's most original contribution; if its ordering
   reads as compelled by evidence it does not fully carry, a skeptical reader's first objection will be
   that the paper describes one firm's book and calls the description a principle.
   **Suggestion**: state explicitly, where the argument is made (Section 4.4), that the order is
   non-arbitrary (each tier is forced by a named, evidenced failure) but not claimed unique or provably
   optimal, and that per-role optimality is deferred to the seat papers. Notably, the argument
   blueprint already planned exactly this concession (`_argument.md`, Sub-Argument 3 rebuttal) but it
   did not survive into the draft.
   **Severity**: Major.
2. **W2: The risk-conditioning / return-timing boundary (Section 5.5) is asserted more than defended.**
   **Problem**: the paper's own text calls this "the paper's most contested line," yet the mechanism
   by which risk-conditioning escapes the arbitrage-decay argument that (per Section 2.4) kills
   return-timing is not fully worked through against the well-known entanglement between realized
   volatility and forward returns (see R1 and Devil's Advocate below).
   **Why it matters**: this line does the load-bearing work of Section 5's most contestable concession;
   a reader unconvinced by it can question whether "structural, never timed" convexity sourcing is
   coherently different from what the regime-conditional counter-evidence (Costa & Kwon, 2019; Uysal &
   Mulvey, 2021; Fleming, Kirby & Ostdiek, 2001) already does.
   **Suggestion**: add two or three sentences engaging the leverage-effect / asymmetric-volatility
   literature directly, rather than resting the distinction on "risk is more stationary and estimable."
   **Severity**: Major.
3. **W3: Practitioner implementation friction is absent.** For a *JPM* readership of working allocators,
   the paper does not address mandate rigidity (investment policy statements typically allocate by
   asset class or manager type, not by convexity role), the capacity/cost of an actively monetized tail
   sleeve, or the governance discipline needed to hold an expensive Target sleeve through a multi-year
   calm period. **Severity**: Minor from a journal-fit standpoint (the venue also publishes
   theoretical/strategic-altitude pieces), but see R3 for the fuller case that this is worth a short
   paragraph.

### Detailed Comments

**Journal Fit**: excellent. The topic, register, and citation base are squarely *JPM*'s.
**Originality**: a genuine reframing (order over count; skew as classifier not budget) built from
existing literatures rather than a new dataset or estimator; incremental in method, non-trivial in
organizing insight.
**Significance**: high for the paper's stated audience (multi-strategy allocators); the tiered roster
and the gated-Expansion discipline (admit only if effective bets rise, never for label) are directly
usable by a risk team.
**Structural Coherence**: mostly strong (Title -> Abstract -> thesis -> chapters -> conclusion track
cleanly), with the one coherence gap noted in W1: Ch4's confident framing versus Ch6's honestly hedged
framing of the same claim are in mild tension.
**Title & Abstract**: title is precise and the abstract states the thesis, the pivot, and the scope
limit in one paragraph without overclaiming; well executed.
**Conclusion**: states limits without hedging and names concrete falsification conditions; a rare and
valuable practice for this genre.

### Questions for Authors

1. Is the Floor-Target-Expansion order claimed as the unique correct sequence, or as one non-arbitrary
   instantiation among several defensible orderings? The current Section 4.4 prose reads as the
   former; please state which explicitly.
2. Would the ordering claim survive a comparison, even a qualitative one, against an unordered,
   equal-risk-contribution blend of the same four sleeve types? If that comparison is deferred to the
   seat papers, say so rather than let Ch4 imply the ordering already stands on the evidence marshaled
   here.

### Minor Issues

- Two in-text citations name the venue/title rather than the author: "(Empirical Economics, 2026)" in
  5.1 should be "(Trucíos, 2026)"; "(When simplicity beats optimization, 2026)" in 5.3 should be
  "(Feng, 2026)." Both authors are correctly named in the reference list, so this is a mechanical fix.
- "Al Fallouji" (in-text, Section 4.2) versus "Al-Fallouji" (reference list) hyphenation is inconsistent.
- Several sentences in Sections 3 and 5 run 60-90 words; splitting a handful would help readability
  even for a specialist audience.

### Dimension Scores

| Dimension | Score | Descriptor | Notes |
|---|---|---|---|
| Originality (20%) | 76 | Strong | genuine reframing, incremental in method |
| Methodological Rigor (25%) | 78 | Strong | minor gaps per W1/W2 |
| Evidence Sufficiency (25%) | 82 | Strong | 54 references, high peer-review share; weaker locally in 5.4 |
| Argument Coherence (15%) | 80 | Strong | one coherence gap, W1 |
| Writing Quality (15%) | 80 | Strong | dense but professional |
| **Weighted Average** | **79.2** | **Minor Revision** | |

---

## Methodology Review Report (Peer Reviewer 1)

### Reviewer Identity
Research methodologist specializing in argumentation logic and evidentiary sufficiency for
theoretical/conceptual finance papers (per the skill's guidance for papers with no original dataset,
this seat evaluates premise-to-conclusion validity, counterargument handling, and testability rather
than statistical design).

### Overall Recommendation
Major Revision (see note on scoring below)

### Confidence Score
4

### Summary Assessment
This is a theoretical paper with no original experiments, so "methodology" here means the discipline
of ex-ante rationale before evidence, and the validity of the inference from cited evidence to the
paper's claims. On both counts the paper is mostly excellent: it states the arithmetic property behind
"skew classifies but cannot budget" (Section 3.1) before citing any confirming study, and it repeats
the same discipline in Section 5's ex-ante rationale before the empirical scoping. Two places break
this otherwise disciplined pattern. Section 4.4 asserts the tiered roster's order is compelled by
evidence that does not, on inspection, uniquely compel it, dropping a concession the paper's own
argument blueprint had planned. Section 5.5 draws a clean line between risk-conditioning and
return-timing without addressing the empirical entanglement between the two. My weighted dimension
average sits in the Minor Revision band (see table), but I am elevating my recommendation to Major
Revision because both gaps sit in the two chapters carrying the paper's most original claims (the
roster and the risk/return boundary), not in peripheral material; per this field's own guidance,
"specific content of reviewer comments is more important than numbers."

### Strengths

1. **Ex-ante-before-evidence discipline, applied consistently**: Sections 3.1 and 5 (opening
   paragraph) both state the mechanism-level rationale before any citation, directly operationalizing
   the paper's own governing standard (a backtest estimates an effect already expected; it never
   discovers one).
2. **The sign-vs-magnitude argument (Ch3) is a genuinely falsifiable, dataset-independent claim**:
   skewness as a cubed-deviation estimator is tail-dominated as a property of the statistic, stated
   before any data, then checked against three separate literatures (time-series coskewness pricing,
   cross-asset carry, portfolio optimization) that each independently confirm the same asymmetry. This
   is the strongest chapter in the manuscript.
3. **Guardrails are handled honestly, not as strawmen**: the genuine counter-evidence in 3.5
   (Baltas & Salinas Sharpe ~0.73) and 5.5 (Costa & Kwon: regime-switching risk parity "consistently
   outperforms" nominal) is stated at full strength before being scoped, rather than weakened before
   being dismissed.

### Weaknesses

1. **W1: The roster's order is argued as more necessary than the cited evidence supports, and a
   planned concession is missing.**
   **Problem**: Section 4.4 states the order "is not an aesthetic preference but the antidote to a
   documented failure" and later that a roster built this way "has a natural stopping point." The only
   load-bearing evidence, Brown, Gregoriou & Pascalau (2011), shows that adding sleeves past roughly
   twenty funds raises tail risk; it says nothing about whether a Floor-Target-Expansion sequence
   specifically is the required repair, as opposed to, say, fewer sleeves, or a different tiering. The
   paper's own argument blueprint anticipated exactly this objection: "Rebuttal (reframe, then concede
   and limit): The order is not claimed unique or optimal; it is claimed non-arbitrary... Concede that
   the specific roster is one instantiation and defer per-role optimality to the seats"
   (`_argument.md`, Sub-Argument 3). That concession does not appear anywhere in Section 4 of the
   draft; the only hedging language appears three chapters later, in Section 6's general limits
   paragraph, which discusses regime-conditional risk sizing and HRP superiority, not roster
   uniqueness.
   **Why it matters**: Ch4 is the paper's most original contribution (the "framework core," per its
   own Section 4 header). Presenting its central claim more confidently than the plan intended, and
   more confidently than the cited evidence supports, is exactly the gap a skeptical referee or a
   later "seat" paper would press hardest.
   **Suggestion**: restore the planned concession in Section 4.4, in the same place the confident
   claim is made, not only in Section 6.
   **Severity**: Major.
2. **W2: The risk-conditioning / return-timing line is asserted, not defended, against a known
   entanglement.**
   **Problem**: Section 5.5's ex-ante rationale is that a return or crash signal computable from
   public prices gets priced away by the limits-to-arbitrage logic of Section 2.4, while
   risk-conditioning survives because "realized risk is comparatively stationary and estimable,
   whereas a return forecast is not." This omits that realized volatility and forward returns are
   empirically entangled through the well-established leverage effect / asymmetric volatility
   (volatility spikes co-occur with negative returns); a rule that de-risks when realized vol rises is,
   mechanically, close kin to a lagging return-timing rule. The paper does not explain why this
   entanglement does not undermine the clean partition it draws.
   **Why it matters**: this is, in the paper's own words, "the paper's most contested line," and it is
   the hinge on which the entire construction chapter's permitted/rejected boundary turns.
   **Suggestion**: add direct engagement with the leverage-effect literature, explaining precisely why
   a risk-conditioning rule is not simply return-timing wearing a different metric, e.g. by
   distinguishing "reduces variance/tail exposure regardless of whether the market has mispriced
   anything" (risk management) from "seeks to profit from a mispriced return forecast" (timing), if
   that is the intended distinction; currently it is implied rather than stated.
   **Severity**: Major.
3. **W3: The ranking-vs-budgeting distinction (3.5) is plausible but not formalized.**
   **Problem**: the paper distinguishes cross-sectional skew ranking (Baltas & Salinas; real,
   tradeable, Sharpe ~0.73) from book-level net-skew budgeting (refuted) without stating precisely why
   a repeatedly resampled, ordinal, cross-sectional comparison escapes the estimation fragility that a
   fixed-magnitude, book-level target inherits.
   **Suggestion**: one added sentence making the ordinal/repeated-average versus cardinal/point-estimate
   distinction explicit would close this gap; it is the pivot chapter, so it deserves the extra
   precision.
   **Severity**: Minor, bordering Major given the chapter's centrality.
4. **W4: The Floor's ordering claim (4.1) is not tested against the natural null.** The paper never
   compares its ordered roster against a flat, unordered risk-parity blend of the identical sleeve set,
   which would isolate what "ordering" specifically buys over sleeve selection alone. This echoes,
   from the argument-logic angle, the Devil's Advocate's independent "alternative paths" point below.
   **Severity**: Minor.
5. **W5: Several load-bearing citations are very recent, unreplicated work.** Noguer i Alonso &
   Al-Fallouji (2026, preprint) formalizes the Section 4.2 speed-gap argument; Baltussen, Martens & van
   der Linden (2026), Feng (2026), and Trucíos (2026) are all just-published. Existence and
   attribution were already verified at Stage 2.5; the residual methodological point is that the paper
   cites these with the same evidentiary weight as twenty-year-old, heavily replicated results, without
   flagging them as not-yet-time-tested. **Severity**: Minor.

### Detailed Comments

**Research Questions & Hypotheses**: the sub-question chain (SQ1-SQ6, per the outline) is clear and
each chapter answers exactly one; no drift observed between outline and draft at the chapter level.
**Research Design** (read as: argument design): sound overall structure (axis -> pivot -> roster ->
construction -> limits); the two logic gaps above sit within otherwise well-formed chapters.
**Analysis Methods** (read as: inferential moves): the ex-ante-then-evidence pattern is applied
correctly in Chs 3 and 5's opening paragraphs; W1 and W2 are the two places the paper's own standard
is not fully met.
**Results Presentation**: quantitative claims (Harvey-Siddique magnitude range, Baltas-Salinas Sharpe,
Brown et al.'s ~20-fund threshold) are stated with appropriate hedges and match the source
annotations in `_sources.md` and the corrections logged in `_integrity.md`; no new distortions found
beyond the four already caught and fixed at Stage 2.5.
**Reproducibility**: not applicable in the empirical sense (no original data/code); the argument
itself is reproducible from the cited literature, which is the correct standard for this paper type.

### Methodological Fallacies Detected
No naked appeal to authority, no circular reasoning, no false dichotomy (Section 5.5 explicitly holds
a third position between "solve live" and "ignore regime"). The closest fallacy risk is an
underdetermination gap in Ch4 (W1): evidence consistent with a conclusion is treated as evidence for
that specific conclusion over its unexamined alternatives.

### Questions for Authors

1. In Section 4.4, is the Floor-Target-Expansion order claimed unique, or one non-arbitrary
   instantiation? Please state this explicitly in the text, not only in response to review.
2. Can Section 5.5 state directly why a realized-volatility risk-conditioning signal is not, in effect,
   a lagging return-timing rule, given the leverage effect?
3. Is a comparison against an unordered equal-risk-contribution blend of the same sleeves planned for
   a seat paper? If so, say so in Section 4 or 6.

### Minor Issues
- In-text citation-by-title for Trucíos (2026) and Feng (2026) (see EIC report for detail).

### Dimension Scores

| Dimension | Score | Descriptor | Notes |
|---|---|---|---|
| Originality (20%) | 74 | Adequate | genuine synthesis, not a new estimator |
| Methodological Rigor (25%) | 60 | Adequate (low end) | W1 and W2 are core-argument gaps |
| Evidence Sufficiency (25%) | 72 | Adequate | strong corpus, locally thin in 5.4 |
| Argument Coherence (15%) | 74 | Adequate | W1 is a plan-to-draft coherence gap |
| Writing Quality (15%) | 78 | Strong | |
| **Weighted Average** | **70.6** | Minor Revision (numeric); **elevated to Major Revision** | see rationale above |

---

## Domain Review Report (Peer Reviewer 2)

### Reviewer Identity
Senior academic in empirical asset pricing, spanning higher-moment pricing (coskewness,
variance-risk-premium literature) and the trend-following / managed-futures literature.

### Overall Recommendation
Major Revision (see note on scoring below)

### Confidence Score
5

### Summary Assessment
The paper integrates three distinct sub-literatures, higher-moment asset pricing, CTA/trend-following,
and portfolio-construction/risk-parity, with real command of each, representing both foundational and
2023-2026 work. The cross-sectional-skew concession (3.5) is handled with genuine intellectual honesty
rather than as a token caveat, and the asset-class-specific carry-skew argument (3.3) correctly reads
Koijen, Moskowitz, Pedersen & Vrugt (2018) alongside its mechanism (Brunnermeier, Nagel & Pedersen,
2008). My concerns are narrower than R1's or the Devil's Advocate's structural points: they concern
evidentiary balance in one sub-section (5.4) and a conflict-of-interest disclosure gap the paper's own
practice elsewhere would flag. My weighted average sits in the Minor Revision band, but as with R1 I am
elevating to Major Revision because the 5.4 gap sits under the paper's single most operationally
specific claim.

### Strengths

1. **Comprehensive, currently maintained literature integration**: the paper cites both the origin
   (Harvey & Siddique, 2000) and the 25-year out-of-sample revisit (Harvey & Siddique, 2023) of the
   coskewness premium, both the classic (Fung & Hsieh, 2001) and recent (Baltussen, Martens & van der
   Linden, 2026) defensive-strategy literature, and both foundational (DeMiguel, Garlappi & Uppal,
   2009) and 2026 (Trucíos; Feng) risk-based-construction robustness checks. This is an unusually
   well-maintained corpus for an integrative paper.
2. **The 3.5 guardrail is a model of honest scoping**: rather than a blanket "skew is useless," the
   paper concedes Baltas & Salinas (2022) and Le, Kourtis & Markellos (2023) at full strength and draws
   a precise line (cross-sectional ranking and option-implied skew are real, tradeable signals;
   book-level net-skew budgeting is a different, refuted claim). This is exactly the behavior a domain
   reviewer wants given how easy it would be to overclaim here.
3. **Carry's asset-class-specific skew sign is correctly and precisely read**: currency/options carry
   negatively skewed, equity/Treasury/credit carry positively skewed, diversified global carry
   negligible, with the funding-liquidity-unwind mechanism (Brunnermeier, Nagel & Pedersen, 2008)
   correctly identified as what fixes the sign ex-ante rather than as a post-hoc description.

### Weaknesses

1. **W1: Section 5.4's most specific, actionable claim is undersupported by peer-reviewed evidence.**
   **Problem**: "the tail as a convexity-premium budget" rests on Israelov & Nielsen (2015) and
   Israelov (2019), both peer-reviewed and *JPM*/*JAI*-published but supporting a narrower claim
   (standing puts underperform simply holding less risk), plus One River (2024), Man Group, and
   LongTail Alpha / Bhansali (2020), three non-peer-reviewed practitioner pieces from firms with a
   direct commercial interest in the tail-overlay/monetization products their pieces describe. No
   peer-reviewed or independent-academic source corroborates the specific claim that active
   monetization/rebalancing beats static holding.
   **Why it matters**: this is the paper's most operationally specific recommendation (the title's own
   "budgeting convexity" is realized here), and it is the paper's weakest-evidenced claim. It also
   breaks the paper's own established practice: elsewhere, product-affiliated sources are consistently
   COI-flagged and triangulated with an independent, non-COI source (e.g., Lempériere et al. / CFM
   triangulated with Lettau-Maggiori-Weber and Bollerslev-Todorov in 2.1; Ilmanen / AQR corroborated by
   Carr & Wu and Bollerslev, Tauchen & Zhou in 2.2). Section 5.4 does neither for One River, Man Group,
   or LongTail Alpha.
   **Suggestion**: either add a peer-reviewed, non-COI corroboration of the monetization claim, or
   explicitly COI-flag the three practitioner sources the way CFM/AQR/PIMCO material is flagged
   elsewhere, and soften the claim's framing to match what the peer-reviewed anchors (Israelov et al.)
   actually establish. No specific replacement reference is recommended here; inventing one would
   violate the no-invention rule for reviewer-suggested citations, and the authors are better placed to
   know whether a peer-reviewed corroboration exists in their own research trail.
   **Severity**: Major.
2. **W2: Choueifaty & Coignard (2008) is cited without a conflict-of-interest flag.**
   **Problem**: Section 4.3 cites the diversification ratio for the Expansion tier's gate metric.
   Yves Choueifaty is the founder and CIO of TOBAM, which markets a fund built on this exact metric,
   a commercial interest of the same kind the paper flags for CFM, AQR, and PIMCO citations elsewhere.
   **Suggestion**: add the same "[COI: ...]"-style flag used consistently elsewhere in the reference
   list.
   **Severity**: Minor.
3. **W3: The risk-premium reading of trend's return is adopted without engaging the alternative
   reading present in the same cited literature.** Section 2.3 reads trend's return as hedgers paying
   speculators an insurance-style premium (Moskowitz, Ooi & Pedersen, 2012; Kang, Rouwenhorst & Tang,
   2020), which disciplines the "pure alpha" label as the paper intends. Moskowitz, Ooi & Pedersen's
   own paper, however, also discusses a slow-moving information-diffusion / underreaction channel as a
   candidate explanation for time-series momentum's persistence, which the draft does not mention.
   **Suggestion**: either note this is a deliberate scope choice (the risk-premium reading is what the
   persistence argument in Section 2.4 needs) or briefly acknowledge the alternative.
   **Severity**: Minor.

### Detailed Comments

**Literature Review - Coverage**: comprehensive across the three sub-literatures named above; no
major missing seminal work identified.
**Literature Review - Integration quality**: genuine critical synthesis, not enumeration; sources are
consistently used to carry a specific step of the argument rather than listed for coverage's sake.
**Research Gap Argument**: persuasive; the "count vs. order" reframing is a real gap in how the field
poses the diversification question.
**Theoretical Framework - Appropriateness**: the convexity-axis framework is well matched to the
research question and is recovered by genuinely independent methods (2.1), which is unusual rigor for
this genre.
**Theoretical Framework - Application depth**: applied throughout, not merely named; the roster (Ch4)
and construction (Ch5) both operationalize the axis rather than restating it.
**Academic Argument Quality - Factual accuracy**: spot-checked quantitative claims (Harvey-Siddique
magnitude range, Baltas-Salinas Sharpe ~0.73, Olszewski-Zhou Sharpe/Calmar lifts, Brown et al.'s
~20-fund threshold, McLean-Pontiff decay rates) against `_sources.md` and `_integrity.md`; all
consistent, no new distortions beyond the four already corrected at Stage 2.5.
**Contribution to the Field**: a genuine, if incremental-in-method, organizing contribution; the
explicit deferral of per-role proof to three seat papers is honestly scoped, not a cover for thin
depth.

### Missing Key References
None recommended as required additions; W1 is a triangulation gap for an existing claim, not a missing
citation, since a fabricated recommendation here would enter the paper unchecked.

### Questions for Authors

1. Is there a reason Choueifaty & Coignard (2008) was not COI-flagged alongside CFM/AQR/PIMCO
   citations elsewhere in the paper?
2. Is the authors aware of peer-reviewed literature on systematic option-overlay rebalancing that
   could corroborate or temper the Section 5.4 monetization claim?
3. Is the risk-premium reading of trend's return in 2.3 a deliberate scope choice against the
   underreaction/information-diffusion alternative present in Moskowitz, Ooi & Pedersen (2012) itself?

### Minor Issues
- See EIC report for the in-text citation-by-title issue (Trucíos/Feng); independently confirmed here.

### Dimension Scores

| Dimension | Score | Descriptor | Notes |
|---|---|---|---|
| Originality (20%) | 74 | Adequate | |
| Methodological Rigor (25%) | 72 | Adequate | |
| Evidence Sufficiency (25%) | 74 | Adequate | pulled down by 5.4 |
| Argument Coherence (15%) | 76 | Strong (low end) | |
| Writing Quality (15%) | 79 | Strong | |
| Literature Integration (optional) | 82 | Strong | comprehensive, currently maintained |
| **Weighted Average** | **74.6** | Minor Revision (numeric); **elevated to Major Revision** | see rationale above |

---

## Perspective Review Report (Peer Reviewer 3)

### Reviewer Identity
Multi-strategy CIO / head of portfolio construction at an institutional allocator, bringing the
practitioner-implementation and governance perspective the academic literature this paper cites does
not itself carry.

### Overall Recommendation
Minor Revision

### Confidence Score
4

### Summary Assessment
From the seat of someone who has to defend an allocation to an investment committee, this paper's
Floor / Target / Expansion roster is immediately more usable than "harvest low-correlated premia,"
because it maps onto how allocators already bucket risk internally (defensive/carry sleeves, tail
overlays, alpha/breadth sleeves) while giving each bucket a testable job rather than a label. The
down-only vol ceiling (5.2) speaks directly to a real, recent practitioner pain point: symmetric vol
targeting chasing leverage into a false calm before a shock. What the paper does not address, and what
an allocator reading it will immediately ask, is what it costs in organizational friction to actually
run this: mandate rigidity, sleeve capacity and cost, and the discipline required to hold an expensive
Target sleeve through a multi-year period where it is, by the paper's own description, "a cost paid
continuously and recovered only in stress." None of this undermines the academic argument; all of it
bears on whether the framework travels from the page to a committee memo, which is this venue's
reason for existing.

### Strengths

1. **The roster maps onto existing allocator vocabulary while adding testable structure.** Most
   institutional books already informally separate "income" sleeves from "crisis" sleeves from
   "alpha" sleeves; naming the axis that should organize that separation, and giving the Expansion
   tier a checkable gate (effective number of bets, not position count), is something a risk team can
   actually implement and audit.
2. **The down-only vol ceiling (5.2) targets a real, recently painful failure mode.** Symmetric vol
   targeting's tendency to lever up into a false calm, then face a forced deleveraging exactly when
   liquidity is worst, is a pattern several allocators experienced around 2018 and again in 2020; a
   framework that names "do not scale up merely to hit the target" as a design principle, and states
   plainly that the book still runs leverage up to a fixed gross cap rather than being unlevered by
   this choice, is giving genuinely actionable, honestly scoped guidance rather than a symmetric,
   textbook vol-targeting prescription.
3. **The Expansion gate is operationally checkable.** "Admitted only when it adds an independent bet,
   never for its label" (4.3) is a standard a risk committee can actually enforce against a manager
   pitch, unlike vaguer "diversify more" guidance.

### Weaknesses

1. **W1: Mandate and governance friction is not addressed.** Most institutional investment policy
   statements allocate by asset class or manager type ("10% managed futures," "5% relative value"),
   not by convexity role. Adopting this framework means re-underwriting the policy statement and
   educating a board or investment committee on an unfamiliar organizing taxonomy. In practice this
   organizational switching cost, not the statistical argument, is often the binding constraint on
   whether a framework like this gets adopted. **Suggestion**: a short paragraph acknowledging this,
   even without solving it, would materially strengthen the paper's credibility with its target
   readership. **Severity**: Minor.
2. **W2: Capacity and cost of the "sourced structurally, monetized actively" tail are not discussed.**
   Trend-following and options-overlay capacity is finite and costly at scale; the actively monetized
   tail (5.4) requires options-trading infrastructure many allocators do not run in-house, which in
   practice often means delegating that sleeve to an external manager, reintroducing exactly the
   manager-selection and correlated-book risk (Brown, Gregoriou & Pascalau, 2011) the roster is
   designed to avoid at the top level. **Severity**: Minor.
3. **W3: The behavioral/governance discipline required to hold the Target tier through a multi-year
   calm period is not discussed.** Section 5.4 is explicit that the tail sleeve "is a cost paid
   continuously and recovered only in stress"; the paper does not address the career-risk and
   committee-patience problem of holding a persistently losing line item, a problem the paper's own
   cited persistence argument (Shleifer & Vishny, 1997, on capital-constrained arbitrageurs) is
   actually well suited to extend to the allocator's own seat, not only to the market's payers.
   **Severity**: Minor.

### Detailed Comments

**Assumption Audit**
- *Explicit*: the paper assumes the reader/allocator can build or already runs all three roster tiers.
- *Implicit*: that organizing by convexity role is more actionable for a governance committee than
  organizing by strategy label; this is contestable and worth stating as an assumption rather than a
  given.
- *Paradigmatic*: the paper's paradigm validates a position by identifying a durable payer (a
  risk-premium/limits-to-arbitrage lens). A market-microstructure or dealer-flow paradigm might read
  some of the same convexity phenomena differently, for instance dealer gamma-hedging flows affecting
  realized volatility through a mechanism distinct from "structural insurance demand." This is not a
  defect; it is a paradigmatic choice the paper could name as such.

**Practical Impact**
- *Real-world application*: high, if the governance friction above is at least acknowledged.
- *Implementation feasibility*: the Floor and Target tiers are readily implementable by allocators who
  already run trend and tail programs; the Expansion tier's gate requires a risk system capable of
  computing an effective-number-of-bets metric, which not every allocator has in production today.
- *Stakeholders*: end allocators and LPs who must underwrite manager risk when the sole "labeled
  illustration" of the framework is the authors' own trading system; the estimate-tier labeling
  mitigates but does not fully remove the optics of a research paper that reads, in its construction
  chapter, like documentation for a specific book.

**Broader Implications**
- *Reflexivity*: the paper applies McLean & Pontiff's (2016) publication-decay guard to return-timing
  strategies but does not ask the same question of itself: could this paper's own publication shrink
  the structural payers (insurance demand, hedging pressure) it relies on, the way the paper argues a
  published return-timing signal gets arbitraged away? The paper's own answer (these payers are
  structural, not informational) is a reasonable one, but stating it explicitly, even in one sentence,
  would close an obvious reader question.

### Cross-Disciplinary Reading Recommendations
- The behavioral/governance discipline point above (W3) is a natural extension of a source the paper
  already cites (Shleifer & Vishny, 1997) rather than a new citation; no external recommendation
  needed. General practitioner-facing treatments of the "you must hold trend/tail exposure through
  pain to collect it" problem exist in the wider investment-management literature (e.g., Antti
  Ilmanen's writing on harvesting risk premia, an author already cited once in this paper for a
  different claim); flagged as a general search lead, not a specific citation to add, since the
  authors are better placed to pick the reference that fits their own argument.

### Questions for Authors

1. What would change in the paper's investment-committee-facing framing if convexity roles had to be
   mapped back onto conventional asset-class or manager-type mandate buckets?
2. Is the Expansion tier's effective-number-of-bets gate intended to be computed in-house, or is
   third-party risk-system support assumed?
3. Does the paper have a view on whether its own publication could, over time, shrink the structural
   payers it relies on, the way it argues published return-timing signals get arbitraged away?

### Minor Issues
None beyond those already logged by other reviewers.

### Dimension Scores

| Dimension | Score | Descriptor | Notes |
|---|---|---|---|
| Originality (20%) | 78 | Strong | |
| Methodological Rigor (25%) | 76 | Strong | |
| Evidence Sufficiency (25%) | 80 | Strong | |
| Argument Coherence (15%) | 78 | Strong | |
| Writing Quality (15%) | 76 | Strong | dense for a practitioner audience in places |
| Significance & Impact (optional) | 84 | Strong | clear practical implications for allocators |
| **Weighted Average** | **77.7** | **Minor Revision** | |

---

## Devil's Advocate Review

The paper is well-disciplined where it is most exposed: the pivot chapter states its statistical claim
before any evidence, and the honest concessions in 3.5 and 5.5 show the authors know where their own
argument is weakest. That self-awareness makes what follows sharper criticism, not softer.

### Strongest Counter-Argument

The paper's most original claim, that diversification should be organized as a tiered "order of
operations" (Ch4) rather than a mechanism count, is underdetermined by the evidence offered for it.
The only general-purpose empirical anchor, Brown, Gregoriou & Pascalau (2011), shows that adding
sleeves past roughly twenty funds raises left-tail risk and lowers returns. That result supports "stop
diversifying by count" and "prefer fewer, purposeful sleeves." It does not support, and cannot
distinguish between, a Floor-then-Target-then-gated-Expansion sequence and any number of other
non-arbitrary orderings a different author could construct from the same failure-mode logic (for
instance: build the Expansion breadth base first under a strict correlation cap, then add a crisis
responder, then add a fast tail; each step could equally be narrated as "fixing a failure the tier
below cannot"). The paper's own planning document anticipated this exact objection and drafted a
rebuttal for it ("the order is not claimed unique or optimal, it is claimed non-arbitrary,"
`_argument.md` Sub-Argument 3), but that concession is absent from the actual Ch4 prose, which instead
states the order "is not an aesthetic preference" and has "a natural stopping point," language that
claims more necessity than the cited evidence delivers. The most parsimonious alternative account is
that the roster describes the authors' own existing multi-strategy book (explicitly the "motivating
system" behind Section 5) and the order-of-operations narrative was constructed afterward to explain
it, a description dressed as a derivation. This does not mean the roster is wrong; the individual role
claims may well hold up, which is exactly what the three forthcoming seat papers are for. It does mean
the paper's rhetorical confidence in Ch4 currently outruns what Ch4 alone establishes, and a reader who
notices the gap between the confident claim and the hedged one in Ch6 will reasonably ask which one
the authors actually believe.

### Issue List

#### CRITICAL
None identified. The paper's own Section 6 already discloses the roster's provisional, per-role-unverified status as a named limit rather than concealing it, which keeps the underdetermination finding below the "cannot be rescued by revision" bar; see MAJOR #1.

#### MAJOR

| # | Dimension | Issue Description | Location | Field-Norm Boundary | Evidence-Crossing Rationale |
|---|---|---|---|---|---|
| DA-M1 | Core Thesis Challenge / Logic Chain | The tiered roster's specific order is argued as compelled by evidence (Brown et al.'s over-diversification result) that establishes only the general principle (fewer, purposeful sleeves beat counting), not the specific three-tier sequence; the paper's own argument blueprint planned a non-uniqueness concession that is missing from the draft. | Section 4.4 (cf. `_argument.md` Sub-Argument 3 rebuttal) | - | - |
| DA-M2 | Foundation / Logic Chain | The risk-conditioning-versus-return-timing partition (5.5) treats the two as cleanly separable, but realized volatility and forward returns are empirically entangled via the leverage effect / asymmetric volatility; a rule that de-risks when realized vol rises is close kin to a lagging return-timing rule, and the paper's ex-ante rationale ("risk is more stationary and estimable") does not address this directly. | Section 5.5 | - | - |
| DA-M3 | Cherry-Picking Detection | Section 5.4's specific, actionable claim (active monetization/rebalancing beats static holding) is supported almost entirely by three non-peer-reviewed practitioner pieces (One River, Man Group, LongTail Alpha/Bhansali 2020) from firms with a direct commercial interest in the described products, none of which is COI-flagged, while the paper's own established practice elsewhere is to COI-flag and independently triangulate product-affiliated sources. | Section 5.4 | The paper's own practice (Sections 2.1-2.2) is that product-affiliated sources are admissible in this genre provided they are COI-flagged and triangulated with at least one independent, ideally peer-reviewed source for any load-bearing claim (e.g., Lempériere et al./CFM triangulated with Lettau-Maggiori-Weber and Bollerslev-Todorov; Ilmanen/AQR corroborated by Carr-Wu and Bollerslev-Tauchen-Zhou). | Section 5.4 breaks this self-imposed pattern on both counts: no COI flag on One River/Man Group/LongTail Alpha despite evident commercial interest, and no independent or peer-reviewed triangulation of the specific "monetization beats static holding" claim (Israelov & Nielsen and Israelov, the section's peer-reviewed anchors, support a narrower, different claim). This is a within-paper double standard, not an external norm imported from a different subfield. |

#### MINOR

| # | Dimension | Issue Description | Location |
|---|---|---|
| DA-Mi1 | Cherry-Picking Detection (COI) | Choueifaty & Coignard (2008) is cited for the Expansion tier's diversification-ratio gate without a COI flag, despite Yves Choueifaty founding and running TOBAM, which markets a fund built on this metric, inconsistent with the paper's COI-flagging elsewhere. | Section 4.3 |
| DA-Mi2 | Confirmation Bias / Reporting | Two in-text citations name the venue/title rather than the author ("Empirical Economics, 2026" for Trucíos; "When simplicity beats optimization, 2026" for Feng), against APA 7 author-date convention already followed everywhere else in the paper. | Sections 5.1, 5.3 |

### Ignored Alternative Explanations/Paths

1. **A regularized, book-level skew tilt, rather than a fixed net-skew target, is not tested against.**
   The paper's Section 3 argument forecloses "budgeting skew" by definitional fiat (distinguishing
   cross-sectional ranking from book-level budgeting) rather than by showing that a rolling,
   shrinkage-regularized book-level skew tilt (a natural middle ground between "solve a fixed target
   live" and "never budget skew at all") actually fails out of sample. The distinction is asserted more
   than demonstrated to be exhaustive.
2. **An unordered, equal-risk-contribution blend of the same sleeves is never run as the comparison
   case.** The paper's central "order beats count" claim would be most directly tested by comparing the
   ordered roster against a flat risk-parity blend of the identical Floor/Target/Expansion sleeve set,
   holding sleeve selection constant and varying only the ordering logic. No such comparison, even a
   qualitative one, appears; R1 raises the identical point independently (W4).

### Missing Stakeholder Perspectives
- End allocators and LPs who must underwrite the paper's own "estimate tier" illustration as manager
  risk, not merely as an academic example (R3 raises this from the practitioner-feasibility angle;
  here it is the plain conflict-of-interest optics question: is a construction chapter that documents
  one firm's book, however carefully labeled, still functioning partly as a credibility signal for that
  firm's own product?).
- The paper applies McLean & Pontiff's (2016) publication-decay logic to return-timing strategies but
  never turns it on itself: could publishing this framework shrink the structural payers (insurance
  demand, hedging pressure) it relies on, the same way it argues a published return-timing signal gets
  arbitraged away? (R3 raises this too, independently, as a reflexivity question.)

### Unexamined Premise
The entire roster presupposes that a "book" is properly assembled at the level of a small number of
named strategy sleeves (carry, trend, tail, breadth), each admitted or not as a whole. If the true
unit of construction were finer-grained, individual instruments or factors rather than strategy
families, would "order of operations over failure modes" still be the right organizing principle, or
would it collapse into the risk-budgeting problem Section 5.1 already solves at a finer grain,
rendering the tiered-roster narrative in Ch4 a description of convenience rather than a necessary
intermediate structure? The paper does not examine whether the roster is doing real work beyond what a
properly risk-budgeted, factor-level portfolio would already achieve.

### Observations (Non-Defects)
- The explicit falsification conditions in Section 6 are a genuinely rare and valuable practice for
  this genre; naming what would force a rebuild is exactly the right response to DA-M1, even though it
  does not fully resolve it (naming the test is not the same as running it, which the paper itself
  says is the seat papers' job).
- The "estimate tier" discipline (the authors' own trading system as labeled illustration, never
  evidence, stated twice in Ch5) is a strong, self-aware practice that pre-empts the more corrosive
  version of the missing-stakeholder-perspective point above.

---

# Part 2: Editorial Decision

## Reviewer Summary Matrix

| Dimension | EIC | R1 (Methodology) | R2 (Domain) | R3 (Perspective) |
|---|---|---|---|---|
| Overall Recommendation | Minor Revision | Major Revision | Major Revision | Minor Revision |
| Confidence Score | 5 | 4 | 5 | 4 |
| Weighted Numeric Score | 79.2 | 70.6 (elevated) | 74.6 (elevated) | 77.7 |
| Key Strength | Venue fit; stated falsifiability | Ex-ante discipline; Ch3 rigor | Comprehensive, honest literature integration | Roster maps onto allocator practice |
| Key Weakness | -> Step 1b below | -> Step 1b below | -> Step 1b below | -> Step 1b below |

## Sub-Claim Inventory and Consensus (Step 1b/2, applied to the 4 non-DA reviewers; DA tracked separately)

| Sub-claim | Description | EIC | R1 | R2 | R3 | Disposition |
|---|---|---|---|---|---|---|
| SC-1 | Ch4's roster order is presented as more derivationally forced than its evidence establishes; the planned non-uniqueness concession is missing from the draft | raised (W1) | raised (W1) | not-mentioned | not-mentioned | Corroborated (2/4), no conflict; **cross-corroborated by DA-M1 (independent adversarial angle)** |
| SC-2 | The risk-conditioning/return-timing line (5.5) needs a tighter defense against vol-return entanglement | not-mentioned | raised (W2) | not-mentioned | not-mentioned | Single-reviewer (1/4); **cross-corroborated by DA-M2** |
| SC-3 | Section 5.4's monetization claim is undersupported by peer-reviewed, non-COI evidence | not-mentioned | not-mentioned | raised (W1) | not-mentioned | Single-reviewer (1/4); **cross-corroborated by DA-M3** |
| SC-4 | Choueifaty & Coignard (2008) COI undisclosed | not-mentioned | not-mentioned | raised (W2) | not-mentioned | Single-reviewer (1/4); cross-corroborated by DA-Mi1 |
| SC-5 | In-text citation-by-title instead of author (Trucíos/Feng) | raised (Minor Issues) | raised (Minor Issues) | raised (Minor Issues, corroborating) | not-mentioned | Corroborated (3/4); no conflict; cross-corroborated by DA-Mi2 |
| SC-6 | Practitioner implementation/governance friction (mandate rigidity, tail-sleeve capacity/cost, career risk of holding through pain) is unaddressed | raised (W3, briefly) | not-mentioned | not-mentioned | raised (W1/W2/W3, in depth) | Corroborated (2/4), no conflict |
| SC-7 | Trend's return is read only via the risk-premium/hedging-pressure channel, not the underreaction alternative present in the same cited source | not-mentioned | not-mentioned | raised (W3) | not-mentioned | Single-reviewer (1/4) |

No sub-claim reaches CONSENSUS-4 or CONSENSUS-3; this is expected given the panel's designed
non-overlapping perspectives (Iron Rule: reviewers do not cross-reference). SC-1 through SC-3, the
three most consequential sub-claims, are each independently corroborated by the Devil's Advocate from
a different angle than the peer reviewer who raised them, which the synthesis below treats as
meaningful convergence even though it does not meet the 4-reviewer consensus bar. No `disputed`
position was raised on any sub-claim; there are no genuine SPLITs requiring arbitration between
reviewers in this round.

## Points of Agreement (Consensus, qualitative)

Not formally CONSENSUS-4/3 by the sub-claim count, but worth naming as agreement in substance: three of
four reviewers (EIC, R1, R2) independently praised the paper's ex-ante-before-evidence discipline and
its honest handling of genuine counter-evidence (the 3.5 and 5.5 guardrails), and three of four (EIC,
R1, R2) independently flagged citation-formatting slips (SC-5). These are read as real convergence,
not manufactured unanimity.

## Decision Rationale

Applying the decision matrix (EIC: Minor, R1: Major, R2: Major, R3: Minor) yields Major Revision, and
the qualitative record supports the same conclusion. The paper's foundation is sound: the axis claim
(Ch2) is triangulated past its own conflicts of interest, the pivot (Ch3) is a well-executed,
falsifiable, and honestly guarded argument, and the paper's integrative scope is disclosed rather than
hidden. Three issues, however, sit under the paper's two most original and most operationally specific
claims, not in peripheral material, and each was found independently by at least one peer reviewer and
corroborated from a different angle by the Devil's Advocate: the roster's order is argued more
confidently than its evidence and the paper's own planning documents intended (SC-1 / DA-M1); the
risk-conditioning/return-timing boundary, which the paper itself calls its most contested line, needs
a materially tighter defense against the leverage-effect entanglement (SC-2 / DA-M2); and the tail-
monetization claim in 5.4 is the paper's weakest-evidenced, most self-interested-sourced claim
attached to its most actionable recommendation (SC-3 / DA-M3). None of these is a fundamental,
unfixable flaw: each has a concrete, scoped textual fix (restore a planned concession; add a paragraph
engaging a known empirical entanglement; rebalance or re-flag a citation cluster), none requires new
data, a new dataset, or a restructured argument. That combination, real and specific core-argument
gaps that are nonetheless clearly fixable without re-architecture, is exactly what distinguishes Major
Revision from both Minor Revision (the gaps are too central to call "supplementation") and Reject (the
paper's foundation, and most of its execution, is sound).

## Top Blocking Issues (ranked)

| Rank | Blocking issue | Source reviewer(s) | Evidence anchor | Resolving roadmap item |
|---|---|---|---|---|
| 1 | Ch4's tiered roster order is argued as more evidence-compelled than it is; the argument blueprint's planned non-uniqueness concession is missing from the draft | R1, EIC, Devil's Advocate (DA-M1) | Section 4.4, "not an aesthetic preference... has a natural stopping point"; cf. `_argument.md` Sub-Argument 3 rebuttal | R1 |
| 2 | Section 5.4's active-monetization claim rests on non-peer-reviewed, undisclosed-COI, self-interested practitioner sources with no independent triangulation | R2, Devil's Advocate (DA-M3) | Section 5.4, One River / Man Group / LongTail Alpha citations | R2 |
| 3 | The risk-conditioning/return-timing boundary (the paper's own "most contested line") is asserted without engaging the leverage-effect entanglement between realized volatility and forward returns | R1, Devil's Advocate (DA-M2) | Section 5.5 | R3 |

---

# Part 3: Revision Roadmap

## Required Revisions (Must Fix)

| # | Revision Item | Sub-Claim(s) | Source | Priority | Estimated Effort |
|---|---|---|---|---|---|
| R1 | Restore the planned non-uniqueness concession in Section 4.4 (or an added closing paragraph): state that the Floor-Target-Expansion order is non-arbitrary (each tier is forced by a named, evidenced failure) but not claimed unique or provably optimal, with per-role optimality deferred to the seat papers, matching `_argument.md` Sub-Argument 3's rebuttal | SC-1 | R1/EIC/DA-M1 | P1 | 0.5-1 day |
| R2 | Rebalance Section 5.4's evidentiary base: add a peer-reviewed, non-COI corroboration of the "active monetization beats static holding" claim if one exists, or explicitly COI-flag One River / Man Group / LongTail Alpha as is done for CFM/AQR/PIMCO elsewhere, and soften the claim's framing to match what the peer-reviewed anchors (Israelov & Nielsen; Israelov) actually establish | SC-3 | R2/DA-M3 | P1 | 1-2 days |
| R3 | Add direct engagement, in Section 5.5, with the leverage-effect / asymmetric-volatility literature, explaining precisely why a risk-conditioning rule that de-risks on rising realized volatility is not simply a lagging return-timing rule, sharpening the distinction beyond "risk is more stationary and estimable" | SC-2 | R1/DA-M2 | P1 | 0.5-1 day |

## Suggested Revisions (Should Fix)

| # | Revision Item | Sub-Claim(s) | Source | Priority | Estimated Effort |
|---|---|---|---|---|---|
| S1 | Add a COI flag to Choueifaty & Coignard (2008), consistent with the paper's existing disclosure practice (TOBAM affiliation) | SC-4 | R2/DA-Mi1 | P2 | trivial |
| S2 | Add a short paragraph (Ch5 or Ch6) acknowledging implementation/governance friction: mandate rigidity against a convexity-role taxonomy, capacity/cost of the actively monetized tail, and the discipline needed to hold an expensive Target sleeve through a multi-year calm period | SC-6 | R3/EIC | P2 | 0.5 day |
| S3 | Add one sentence in Section 3.5 formalizing why cross-sectional skew ranking's stability (ordinal, repeatedly resampled) does not transfer to book-level net-skew budgeting (cardinal, point-estimate); tighten the pivot chapter's most contestable exposition point | R1 W3 | R1 | P2 | trivial |
| S4 | Note, in Section 2.3, that the risk-premium/hedging-pressure reading of trend's return is a deliberate scope choice against the underreaction/information-diffusion alternative present in Moskowitz, Ooi & Pedersen (2012) itself, or briefly acknowledge the alternative | SC-7 | R2 W3 | P2/P3 | trivial |

## Revision Checklist

### Priority 1 - Structural Revisions (estimated total: 2-4 days)
- [ ] R1: Restore the roster's non-uniqueness concession in Section 4.4
- [ ] R2: Rebalance or re-flag Section 5.4's monetization evidence
- [ ] R3: Defend the risk-conditioning/return-timing boundary against the leverage-effect entanglement in Section 5.5

### Priority 2 - Content Supplementation (estimated total: 1 day)
- [ ] S1: COI-flag Choueifaty & Coignard (2008)
- [ ] S2: Add an implementation/governance-friction paragraph
- [ ] S3: Formalize the ranking-vs-budgeting distinction in 3.5
- [ ] S4: Scope-note the risk-premium reading of trend's return in 2.3

### Priority 3 - Text and Formatting (estimated total: under half a day)
- [ ] Fix in-text citations: "(Empirical Economics, 2026)" -> "(Trucíos, 2026)"; "(When simplicity beats optimization, 2026)" -> "(Feng, 2026)"
- [ ] Reconcile "Al Fallouji" (in-text) versus "Al-Fallouji" (reference list) hyphenation
- [ ] Split a handful of 60-90-word sentences in Sections 3 and 5 for readability
- [ ] Confirm the reference-list re-alphabetization (Dao et al., Feng, Trucíos) already flagged as deferred to Phase 7 formatting in `_integrity.md` remains tracked

## Total Estimated Effort
Major Revision: approximately 3-5 working days of author effort. Recommended re-review after revision
is a targeted re-review (`re-review` mode) focused on the three Required Revisions and the Devil's
Advocate's MAJOR findings, not a full fresh panel.

---

# Appendix: Editorial Verdict Summary

**Decision: Major Revision.**

The paper's foundation, the convexity axis (Ch2) and the sign-versus-magnitude pivot (Ch3), is strong,
honestly triangulated past its own conflicts of interest, and well-argued. Three specific,
independently-corroborated gaps in its two most original chapters (the roster's order in Ch4, the
risk/return boundary and the tail-monetization evidence in Ch5) keep it from Minor Revision, but none
of them requires new data or a restructured argument, which keeps it well clear of Reject. All three
Required Revisions are text-level fixes: restore a concession the authors had already planned, add a
paragraph of direct engagement with a known empirical entanglement, and rebalance one sub-section's
evidence base.
