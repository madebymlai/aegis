---
title: Window Dressing at the Regulatory Snapshot
date: 2026-07-25
topic: funding-markets
status: research-note
aliases:
  - Quarter-end repo window dressing
  - Point-in-time regulatory reporting
related:
  - "[[income-must-accrue-not-be-captured]]"
  - "[[the-payer-did-not-leave-the-supply-arrived]]"
  - "[[what-is-a-strategy]]"
tags:
  - note
  - funding
  - regulation
  - market-behaviour
---

# Window Dressing at the Regulatory Snapshot

> [!abstract] One-line takeaway
> Bank leverage ratios and G-SIB scores are computed from balance-sheet *snapshots* on named
> reporting dates rather than period averages, so dealers shrink repo books and inventory
> immediately before those dates and rebuild immediately after. Anyone needing secured funding
> at that calendar moment pays for it. The behaviour survives because the party best placed to
> arbitrage it is the party the rule constrains - and it has a known, already-demonstrated
> kill condition, because half the world's regulators have already removed it.

## The mechanism

Regulatory capital metrics are not all measured the same way. Where a leverage ratio or a
G-SIB surcharge score is calculated from a point-in-time snapshot, the rational response is to
be small on the measurement date and normal on every other date. Dealers shrink repo books and
inventory into the reporting date and rebuild afterwards.

The sign is fixed before any data is examined. A rule that measures a snapshot invites
snapshot management; there is no scenario in which a constrained bank optimally expands its
balance sheet into the measurement date. This is the rare case where the behaviour follows
from the rule by inspection.

The magnitude follows the reporting calendar rather than the market. Year-end contraction runs
roughly double the quarter-end figure, which is what one expects when the annual date carries
the G-SIB score as well as the leverage ratio.[^bassi]

## Who pays, and why they cannot stop

Whoever needs secured funding or inventory financing at that exact calendar moment - pension
funds, hedge funds, other dealers - pays a temporary premium through repo rate spikes and
wider spreads. They cannot stop because the funding need is not calendar-elective. A
leveraged position financed in repo must be financed on the last day of the quarter as much
as on any other day.

This is a mandated payer in the strict sense used in [[income-must-accrue-not-be-captured]]:
the flow is compelled by the regulation on one side and by financing necessity on the other,
and no participant on either side is choosing to transact for a view.

## Why competing capital does not remove it

The dislocation is small and reverses within days, which by itself would suggest it should be
arbitraged flat. It is not, and the reason is structural rather than a matter of capital
being slow: **the party best placed to arbitrage it is the party the rule constrains.** A
dealer could profitably lend into the quarter-end squeeze and is precisely the entity forbidden
from carrying the balance sheet to do so.

What absorbs the flow instead is balance-sheet-unconstrained cash - money market funds, and in
the United States the Federal Reserve's overnight reverse repo facility. So the compensation
accrues to whoever is both unconstrained and already present in the market, which is a much
narrower set than "anyone with capital."

That is a limit to arbitrage of the durable kind. It does not dissolve as capital arrives,
because the constraint disqualifies the natural arbitrageur by rule rather than starving it of
funds.

## The natural experiment

The strongest feature of this literature is that the identification was not constructed by
researchers. The same Basel framework is implemented with different reporting conventions
across jurisdictions: the United States and United Kingdom compute the relevant ratio on a
period-average basis, while euro-area, Swiss and Japanese banks report point-in-time.[^feds]

Same regulation, two measurement conventions, and the behaviour appears where the convention
invites it. That is a cross-jurisdictional difference-in-differences available for free, and
it is much harder to argue away than a time-series correlation around calendar dates.

## Evidence

The primary source is Bassi, Behn, Grill and Waibel, "Window dressing of regulatory metrics:
evidence from repo markets," published in the *Journal of Financial Intermediation* in 2024,
using confidential ECB euro-area repo transaction data across a panel of 36 large euro-area
banks. It documents repo volume contractions of roughly 12.5% before quarter-ends and 25%
before year-ends.[^bassi]

Corroborating work exists on the US side from the Federal Reserve Bank of New York's Liberty
Street Economics (2017) and from several Federal Reserve FEDS Notes across 2024 and 2025, which
document the analogue and use the reporting-convention difference explicitly.[^feds] Those
notes describe the effect as currently intensifying as reserves become less abundant following
quantitative tightening - the squeeze is worse when the system's spare cash is thinner, which
is a sensible prediction of the same mechanism rather than a separate finding.

**Sample-period gap.** The Bassi et al. sample's first and last years are not confirmed here.
Everything below should be read with that open, and it should be closed before this note is
cited in a paper.

## What would kill it, and the half that is already dead

The kill condition is unusually concrete: **move the metric from a snapshot to a period
average and the behaviour disappears by construction.** There is nothing left to manage if
every day is a measurement day.

That is not hypothetical. The United States and United Kingdom already use period averaging,
which is exactly why the natural experiment exists. Half the relevant world has already
removed the incentive. Any expectation that this persists is an expectation about euro-area,
Swiss and Japanese regulatory choices specifically, not a claim about markets.

This is the sharper instance of a pattern recorded elsewhere in this vault: a regulatory wedge
is a **policy variable, not a structural feature**, and the rule-setter is a party to the
trade. The wedge moves in both directions - the eSLR relaxation effective 1 April 2026 loosens
a constraint, and a future reporting-convention change would tighten or remove this one. Anyone
holding a position premised on a rule is holding a position on regulatory intent.

## Relation to the intermediary-constraint literature

This is the intermediary capital constraint observed at a predictable moment, in transaction
data, rather than inferred from a cross-sectional asset-pricing test. That distinction matters
now: the He-Kelly-Manela single-factor result has been challenged on inference grounds by
Gospodinov and Robotti (*Journal of Financial Economics*, 2021), whose placebo test flags an
unrelated industry factor as priced in 39 of 40 cases under the original methodology.

Window dressing does not depend on that test surviving. The constraint is not estimated from
returns; it is a rule with a date, and the response is visible directly in repo volumes. If
one wanted a clean demonstration that intermediary constraints price anything at all, this is
a better exhibit than the cross-sectional factor.

## Strategy hypotheses this could seed

- [ ] The premium is a **funding rate**, not a price move. If so it is accrual-shaped in the
  sense of [[income-must-accrue-not-be-captured]] - earned by lending cash across the
  reporting date rather than by trading a tendency - and it should survive a cost floor that
  kills statistical strategies of similar magnitude.
- [ ] Effect size tracks reserve scarcity. If the mechanism is correctly described, the
  quarter-end premium should widen as aggregate reserves fall and narrow as they rise,
  measurable against published reserve balances without any proprietary data.
- [ ] The eSLR relaxation of 1 April 2026 is a live natural experiment. If dealers window-dress
  because the leverage ratio binds, measured US-side quarter-end pressure should fall after
  that date while euro-area pressure is unaffected. A clean falsification of the mechanism if
  both move together, or if neither moves.
- [ ] Year-end exceeds quarter-end because the annual date carries the G-SIB score as well.
  This predicts the year-end premium should be concentrated in banks near a G-SIB bucket
  boundary, which is observable from published scores.
- [ ] Any expression of this is a position on euro-area reporting convention. Pre-register the
  regulatory change that would end it, and treat a consultation on period averaging as the
  kill signal rather than waiting for realized decay.

## Limitations

The primary paper's sample period is unconfirmed here, so neither the currency of the 12.5%
and 25% figures nor their coverage of the post-2020 regime is established.

The US corroboration is drawn from Federal Reserve staff commentary rather than peer-reviewed
work. That is a strong source class for institutional mechanics and a weaker one for
magnitudes.

Nothing in this note establishes that the premium is *capturable* by any particular
participant, only that it exists and that the constrained party cannot compete it away. Repo
market access is a separate question and deliberately not addressed here - the vault's
workflow infers strategies downstream from behaviour, not the reverse.

## Sources

[^bassi]: Bassi, C., Behn, M., Grill, M. and Waibel, P., "Window dressing of regulatory metrics: evidence from repo markets," *Journal of Financial Intermediation*, 2024. Confidential ECB euro-area repo transaction data, panel of 36 large euro-area banks; documents approximately 12.5% repo volume contraction before quarter-ends and 25% before year-ends. Sample start and end years unconfirmed at time of writing.

[^feds]: Federal Reserve Bank of New York, Liberty Street Economics (2017), and Federal Reserve Board FEDS Notes (2024-2025). Document the US analogue and the cross-jurisdictional reporting-convention difference - United States and United Kingdom period-average versus euro-area, Swiss and Japanese point-in-time - and describe the effect as intensifying as reserves become less abundant post-quantitative-tightening. Specific note titles and dates not individually verified here.
