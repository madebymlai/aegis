---
title: "The Income Engine - draft"
paper: "The Income Engine: Funding the Responder Through Ordinary Markets"
date: 2026-07-27
tags:
  - draft
---

# The Income Engine: Funding the Responder Through Ordinary Markets

> [!note] Draft status
> **Complete draft, all eight sections, 2026-07-27.** 6,532 words against a 6,600 budget. Counts at each section
> end are **computed, not estimated** (D17). Body conventions follow the architecture paper: no wikilinks, no
> section symbols, "Section N" spelled out, APA author-date inline. Wikilinks appear in this callout and in
> planning files only.
>
> **Not yet done:** references list, abstract, and the Stage 4.5 integrity pass. Section 7's mechanism argument is
> this paper's own reading and needs a citation checked against a primary source before submission; see D20.

## 1. The job, stated as a contract

An income sleeve is usually specified by what it holds. This paper specifies it by what it owes.

The distinction is not stylistic. The architecture paper of this series places two sleeves of opposite
convexity in the Floor and gives them complementary jobs: one funds the wait, and the other pays for it once
the drawdown lasts (Section 4.1). That assignment makes the income sleeve's job relational. It is not to earn
a return, which a great many exposures will do, but to earn a return that arrives while its partner is losing
and to survive in the state where its partner is finally paid. A sleeve that earns well and fails in the wrong
state has not performed this role poorly. It has not occupied it.

The obligation has four clauses.

**First, the income engine must earn a positive expected return in ordinary markets**, because the ordinary state is the
one it funds. Its partner bleeds in calm and choppy conditions, and the responder study of this series holds
that the bleed is not a defect to be engineered away but the premium the responder pays for its crisis
convexity. That premium is a continuing cost, and the engine's income is what meets it.

**Second, the engine must sell convexity, so that it carries a crash inventory at all** (Section 4.1). This
clause is easy to read as a restatement of the first, and it is not. Without it the third clause below is
satisfiable vacuously, because a behaviour with almost no loss to place will satisfy any requirement about
where its loss lands. Lacking an inventory is not the same as placing one well. The clause also does
structural work for the Floor. The architecture paper organises the book on the sign of convexity to the
common shock, so a Floor whose income half is not genuinely short convexity does not span the axis it was
built to span; it is instead two sleeves selected for low average correlation, which is the trap that paper
identifies in its Section 1 rather than the pairing it specifies in Section 4.1.

**Third, the inventory's loss must land where the responder does not also fail, at the horizon on which the
book is measured.** This is not decorrelation. Decorrelation is a statement about average co-movement, and the
condition here is additive: when the drawdown lasts, the responder must be able to cover its own bleed and the
engine's loss together. A pairing can be uncorrelated on average and still fail this, which is why the clause is
stated over states rather than over correlation coefficients.

**Fourth, the engine must be ranked on its contribution to the paired book rather than on its standalone
smoothness.** A sleeve that looks well behaved alone and adds nothing to the pair has met a criterion the book
does not care about. Ranking a candidate therefore requires a comparison its own record cannot supply: the
paired book has to be measured against the same book with the responder scaled up to fill the engine's weight,
because otherwise a candidate that merely substitutes for more of what the book already holds cannot be
distinguished from one that adds a role.

**What the contract does not claim.** The Floor is built so that each half would cover the other's
characteristic loss, and only one of those two coverages is evidenced. That the engine's income funds the
responder's calm-market bleed follows from the architecture paper's assignment and from the complementarity it
cites. The reverse direction, the responder's crisis payoff covering the engine's own loss through a protracted
drawdown, is a condition the Floor must satisfy rather than a property it is known to have. The condition has
two halves: the protracted-state loss must be bounded, and the calm income must have been collected for long
enough to have pre-paid it. The Floor fails if either half is missing. Whether either holds in the state that
matters is the subject of Section 5, which does not resolve it.

The first clause is weaker than it appears, and deliberately so. It is an ex-ante claim, warranted by an
account of who is compelled to act and why, and not by a measured return. Realised returns cannot separate a
fairly priced premium from an inadequate one when the feared state has not occurred in the sample, so no
return series certifies it. Where this paper says the role holds, it means the second, third and fourth clauses
hold. The first is admitted on rationale and bounded by a loss cap that Section 5 states as owed rather than
supplies.

**How the role fails.** The role fails structurally if the four clauses are jointly unsatisfiable given this
roster: if every behaviour carrying a genuine crash inventory places its loss where the responder also fails,
then no occupant satisfies the second and third clauses together and the role should not exist. That is a proof
about the roster, not a measurement, and it is not reached by accumulation. The space of compelled behaviours
cannot be enumerated, so a run of unsuccessful candidates licenses no conclusion about the role, and reporting
a failed candidate as evidence against the role is the inference this clause exists to forbid.

**What would refute the paper's central claim.** Section 3 argues that what a rule does, rather than what
compels a party, decides whether the compensated function is capacity-provision or risk-bearing. A bar-type
rule whose compensated party is a pure risk-bearer refutes it. If a rule removes a party's ability to hold,
and the party paid on the other side supplies no financing, warehousing, distribution or market-presence
function but simply bears the risk, then barring a holder does not create a capacity need and the derivation
in Section 3 is wrong. Regulatory bars are documented rather than inferred, so the search is specific and
does not require enumerating an unbounded space of candidates.

*Section 1: 984 words, against a budget of 800 revised to 950 (D17). Counted, not estimated.*

## 2. The axis, and why the second clause is constitutive

The architecture paper organises the book on one axis, and this paper adopts it rather than re-deriving it.
That axis is neither the mechanism a sleeve trades nor its average volatility but the **sign of its convexity to
the common shock** (Section 2). The paper establishes it three independent ways: a cross-section in which
risk-adjusted reward aligns with negative skewness rather than with volatility, a downside-beta conditional
model that prices several asset classes off a single price of downside risk, and an option-implied decomposition
separating compensation for diffusive variance from compensation for jumps. Convergence across methods with
different data and different failure modes is what makes the axis a foundation rather than a description, and
that argument is settled there.

This engine is the short pole of that axis. The responder is the long pole. Their pairing in the Floor is not a
diversification heuristic applied to two convenient sleeves; it is the axis itself, instantiated.

Which is why the second clause of the contract is constitutive rather than decorative, and it is worth being
precise about the failure it prevents. Two sleeves can be selected for low average correlation and still be
short the same convexity to the common shock, in which case they diverge in the middle of the distribution and
converge in the tail, exactly where a book needs them apart. The architecture paper names that trap in its
Section 1 and builds the Floor to avoid it by choosing sleeves of **opposite convexity** rather than low
correlation. An income sleeve that earns steadily and carries no crash inventory does not fail this test
loudly. It passes every correlation screen and quietly leaves the Floor spanning half an axis, because the pole
it was supposed to occupy is vacant. That is the specific way a Floor can look balanced on every summary
statistic available before a drawdown and fail during one.

The clause has a second consequence, which organises the rest of the paper. Being short convexity is a
statement about payoff shape, and payoff shape does not identify a payer. Several distinct mechanisms produce a
short-convexity profile, and they are paid by different parties for different reasons, so they inherit different
durability. Treating them as one premium because they share a shape is the error the next section exists to
avoid: it licenses the assumption that evidence gathered in one venue transfers to another that merely looks
similar in its return distribution. The shape tells you which pole a sleeve occupies. It does not tell you
whether anyone will keep paying for it, and that question has to be answered payer by payer.

*Section 2: 437 words, budget 500. Came in short; see D19 rather than padded.*

## 3. What a rule does decides who is paid

The architecture paper identifies the short pole's payer concretely, and this section refines that
identification rather than replacing it. Its account is that demand for protection is price-insensitive, coming from hedgers,
mandate-constrained institutions and lottery-seeking buyers whose need does not go on sale when the premium
widens, but that inelastic demand is necessary and not sufficient: a price-insensitive buyer facing abundant
sellers pays little. The premium therefore depends on the capacity of
the side supplying protection as much as on the urgency of the side demanding it, and the short pole is paid
"for bearing unhedgeable risk where the intermediary's capacity binds", with the size of the payment tracking
the constraint rather than a fixed preference (Section 2.2).

That formulation is adopted whole. What it does not settle is which binding constraints pay a party that can
only bear risk, and that is the question this section answers.

**Three mechanisms sit under one label.** "Capacity binds" is doing work for at least three distinct stories
that are not interchangeable. In demand-pressure pricing, market makers who cannot hedge perfectly must be paid
to absorb an order imbalance, which is why index options, where end users are net buyers, carry a premium that
single-stock options, where end users are net suppliers, do not (Gârleanu, Pedersen, & Poteshman, 2009). In
capital-constrained pricing, an intermediary's marginal value of wealth is itself the pricing kernel, so
premia widen when intermediary equity is impaired (He, Kelly, & Manela, 2017; Adrian, Etula, & Muir, 2014;
Kargar, 2021). In rule-based exclusion, a regulation disqualifies a class of holder outright, independent of
anyone's capital position. "Size tracks the constraint" is native to the first two and not obviously a property
of the third, which is reason enough to keep them apart.

**Compulsion, and its two failure modes.** What the three share is that the party on the other side is acting
for a reason that is not a view. It is compelled. Compulsion arrives two ways: a **rule** can name who may not
hold, or a **circumstance** can create a need that anyone with capital can serve. The distinction matters
because the two fail differently. A premium created by a rule fails when the rule changes, and rules are policy
dials: period-averaging of the relevant regulatory measure removes the incentive behind one of the cleanest
documented cases, and much of the world already uses it. A premium created by circumstance fails when capital
arrives and substitutes for the constrained party. Neither is permanent, and immunity to capital is not
durability.

**But rule versus circumstance is not the discriminating question.** What discriminates is **what the rule
does**, and the distinction can be derived rather than counted.

A rule that **bars** a party from holding removes that party from a position which still has to exist
somewhere. Someone must therefore supply the holding itself. That is a service, and it is why the compensation
is rent on capacity rather than payment for risk: the barred party's willingness to pay is not a preference
about risk, it is the price of a function it is forbidden to perform for itself. A rule that merely **prices**
holding leaves the party perfectly able to hold, only expensively. The position can migrate to whoever bears it
at the lowest capital cost. Nothing is supplied, risk is transferred to a cheaper bearer, and the compensation
is for bearing it.

Nothing in that derivation is specific to an income sleeve, and that generality is deliberate. It is a
statement about what any **risk-bearing allocation** can be paid for, and it applies to the long pole and to
any other tier in the roster on the same terms. A portfolio role admitted on risk borne and priced cannot
collect rent on a function it does not perform, whoever occupies it. Section 8 returns the roster-wide form of
this constraint to the architecture paper, which does not currently carry it.

**Two tests, then, not one.** A candidate behaviour has to pass both. First, does it genuinely sell convexity,
or does it satisfy the loss-placement clause vacuously by having almost no loss to place? Second, is the
compensated function risk-bearing, or is it capacity-provision? The tests are independent and the second is the
one that does unexpected work, because a behaviour can carry real crash-correlated inventory and still be
paid for a service an allocation cannot perform.

One boundary must be held. The test cuts on **function**, not access: it states what a mechanism pays for,
which is economics, and says nothing about what any account can reach, which is implementation. Conflating them
would smuggle a claim about one desk's permissions into a claim about markets.

**The cases, including the one that bounds the claim.** Where a reporting-date rule bars a dealer from carrying
a balance sheet across the measurement date, the compensation flows to whoever is both unconstrained and
already present to supply financing over that date; the mechanism is a rule with a calendar and is visible
directly in transaction volumes (Bassi, Behn, Grill, & Waibel, 2024). Where an index rule compels a tracker to
sell a bond an exclusion has disqualified, the dealer who warehouses it is compensated for a hold that clears
slowly, and for exposure to further deterioration in precisely the credit whose deterioration forced the sale;
the authors report that return is "not replicable by other investors in the economy" (Dick-Nielsen & Rossi,
2019). Both are bar-type rules and both pay for capacity.

Bank significant risk transfer is the contrast, and it is what makes the claim conditional rather than
universal. A capital charge makes a junior tranche expensive to keep without barring the bank from keeping it.
The compensated party takes a funded position referencing a defined tranche and supplies no financing,
warehousing or distribution: the European Systemic Risk Board's own account records that synthetic
securitisation does not provide originating banks with funding, since the loans, the servicing and the customer
relationship all stay put. That is a durable premium whose compensated function is risk-bearing, and it is
therefore occupiable. A price-type rule is where an allocation should look.

A fourth mechanism belongs here and points the other way about durability. Dealers who buy volatility from
clients through yield-enhancing structured products hedge that book contrarian, buying as the underlying falls
and selling as it rises, which mechanically dampens both realised and implied volatility (BIS, 2024). The
compelled action is a hedging obligation with a direction, which is the same shape as the index-exclusion case
even though no rule bars anyone. Section 5 takes up what it implies, because a flow that suppresses volatility
is a support for a short-convexity position and the same crowding that produces it is what compresses the
premium.

**What this section does not establish.** Few entries in the register reach the second test at all: most fail
the convexity clause or the durability question first, so the criterion rests on a small number of confirmations
and is derived rather than corroborated. The generalisation that constrained capacity is plural and local, drawn
from a single crisis episode, is this paper's extrapolation and not a finding of the study it draws on. And the
binding constraint is directly observable in only one of the venues discussed: for the others it is inferred
from the mechanism's shape rather than measured, which is a research obligation this paper names rather than
discharges.

*Section 3: 1,229 words, budget 1,100. Over by 129; see D19.*

## 4. Fair pricing is the equilibrium, so the engine is justified by its shape

Section 3's derivation has a consequence for this engine specifically. A risk-bearing allocation is confined to
price-type compensation, and price-type compensation is what a third party bears at the lowest capital cost.
Competition among potential bearers therefore pushes it toward the marginal arbitrageur's cost of capital. Fair
pricing is not a disappointing outcome that happened to obtain in the sample available. It is what the role's own
definition permits, derived rather than observed.

That is stated as **sufficiency, not necessity**. The contract in Section 1 needs only fair pricing: being paid
the market price for bearing crash risk already delivers both the ordinary-market return and the loss placement
the Floor requires. An excess return found in some venue is surplus rather than a revision, so the argument does
not forbid alpha; it declines to lean on it. A paper needing the premium to be **excess** would be built on
ground its own citations erode, since a minority crash share, a compressed index variance premium, decayed
catastrophe premia and arriving supply are each bad news for an alpha claim and neutral for a role claim.

**The case that hurts is not excess, though, and the indifference has to be stated over the right pair.** A premium can be fair, or **inadequate**: compensation for a state
whose severity the sample has not displayed can be too small and look generous throughout. Realised returns cannot separate inadequate from
fair any better than they separate fair from excess, because the discriminating observation has not occurred. So
no return series warrants the contract's first clause. The clause is admitted on the ex-ante account of who is
compelled and why, which is checkable without a return series, and it is bounded by a cap on the loss the book
will accept, so that underpayment costs return rather than solvency. That cap is specified in Section 5 as owed
rather than supplied, and the reasoning that makes it necessary rather than prudent is set out there.

**What the evidence does establish is a decay path, not an extinction.** The clearest case is a market where
capacity is supplied by specialist funds whose capital is scarce: the estimated price of that constraint risk has
been positive in every one of sixteen independently re-estimated years, nine of them after a documented
structural break, while declining as capital arrived (Tomunen, 2026). The load-bearing claim is the sign persistence across
independent annual re-estimations, not the cross-sectional fit statistic, which is what Gospodinov and Robotti's
critique of two-pass estimation reaches more directly and which this argument does not use. Nobody has shown that
the critique's misspecification mechanism cannot also produce spuriously persistent sign across years, so the
anchor is narrower and better defended than a fit statistic rather than immune to the objection. Year-by-year
magnitudes are available only in a pre-publication draft and are not quoted here.

Compression is visible in the more heavily capitalised venue too, where traded index-option alpha has fallen
toward zero (Dew-Becker & Giglio, 2025). Three cautions travel with that result, and the architecture paper
attaches all three. The synthetic options carrying it are replicated by daily delta-hedging, which cannot span a
jump by construction, so a jump-tied premium would appear in the wedge between traded and synthetic returns
rather than in the synthetic leg's alpha; the evidence therefore dates a compression rather than establishing
that compensation for discrete losses was never priced. The break date is unsettled, with one alternative
methodology placing it more than half a decade later (Bates, 2022). What survives is the direction, not a date.

Together these describe not a premium disappearing but one behaving as rent on constrained capacity should when
capital arrives: falling toward the cost of the capital that arrived, and stopping there rather than at zero.

**So the engine cannot be justified by its price.** A fairly priced risk premium is available to any allocation
willing to bear the risk, which means it is not a reason to hire a role. Whatever the Floor gains from this half
has to be something the price does not capture, and that leaves the payoff's shape.

**The shape is the inventory, and the inventory is what is actually being sold.** A short-convexity position
earns steadily and pays out in the tail; the negative skew is not a side effect of collecting the premium but the
good delivered in exchange for it. This is also why the inventory cannot be defended on its own compensation.
Stripping the crash exposure from a carry position leaves a strategy that remains significantly profitable,
which means most of what the engine earns is not payment for the crash at all (Jurek, 2014). The share
attributable specifically to skewness is materially larger in provisional estimates that remain unpublished and
are not relied on here.

That minority share is also not one number. Compensation recovered from index option prices is in large part
specifically for discrete jump-driven losses (Bollerslev & Todorov, 2011), which points the other way. The two are
usually read as a venue difference, and they may instead track **payoff shape**: a linear carry position and a
convex variance position are being measured, so the split may follow curvature rather than market. The
distinction matters because it governs whether the minority-share reading transfers to occupants sitting nearer
the convex end, and this paper does not settle it.

What follows is that the inventory has to be justified at the level of the pair rather than the position. It is
the one thing this engine sells that the long pole cannot supply for itself, because the long pole buys convexity
by definition and cannot simultaneously sell it. That is the Floor's actual purchase from this half.

And it sets up the question Section 5 has to answer. If the premium compresses toward the cost of arriving
capital, the compression does not merely reduce what the engine earns. It shortens the period over which the
wait can be paid for in advance.

*Section 4: 993 words, budget 1,000 as corrected.*

## 5. The state where neither covers the other

The Floor's condition can be stated exactly, and it has two halves. The engine's loss in a protracted drawdown
must be **bounded**, and the calm income must have been collected for **long enough to have pre-paid it**. If the loss is unbounded, the responder is asked to cover its own bleed and the engine's loss at once. If the
income arrived too late or too thinly, nothing has accumulated to draw on. The Floor fails if either half is
missing, and the halves fail for different reasons.

**Section 4's result bears directly on the second half, and this is the section's own finding.** A premium
compressing toward the marginal arbitrageur's cost of capital does not merely reduce what the engine earns per
unit of risk. It **lengthens the time required to accumulate any given buffer**, and therefore shortens the
protection the Floor actually has at any moment before the drawdown arrives. Compression is usually read as a return problem, lowering expected performance while leaving structure intact.
Against the Floor's condition it is **structural**: the engine can remain admissible on every clause of
Section 1's contract, be fairly compensated for exactly the risk it bears, and still leave the pairing thinner
than it was, because the runway is a function of the premium's level and not only of its sign.

**The first half is where this paper has less to offer, and the shortfall belongs before the evidence rather
than after it.** As Section 1 stated, only one of the Floor's two coverages is evidenced. Whether the
responder's crisis payoff covers the engine's own loss through a sustained decline is a condition the Floor
must satisfy, and the evidence bearing on it is thin in a specific and reportable way.

Two claims have to be kept apart here, because collapsing them would overstate the case. The first is robust:
**no independent study tests the co-movement of a short-convexity return series and a trend-following one
conditioned on drawdown duration.** The comparison the Floor's condition calls for has not been run, and the one
published study whose method separates crisis magnitude from crisis speed reports its results behind a paywall
this argument has not read, so its finding is unknown here rather than merely unconfirmed. The second claim is
weaker and should not borrow the first's strength: there is *reason to expect* the mechanisms that would widen
the engine's compensation under stress answer to acute episodes rather than sustained ones. Compensation demanded
by protection sellers rises with **sudden** intermediary inventory losses and is magnified in the upper
percentiles of dealer losses (Fournier & Jacobs, 2020), and the price of crash insurance rises as intermediary
capacity shrinks, more so when jump risk is elevated (Chen, Joslin, & Ni, forthcoming). Slow declines appear to
price risk through a different channel, one that registers in the non-jump component of the variance premium and
barely in the jump component at all (Bollerslev, Todorov, & Xu, 2015). But turning that into a claim about the
Floor requires mapping *statistical* jump and dealer-loss percentiles onto the roster's *time-based* fast
segment, and those are not the same object. That mapping is assumed here and not established.

**One result that looks decisive is not, and it cuts both ways depending on the occupant.** Compensation for
variance risk is concentrated almost entirely in the roughly one-month transitory shock, while shocks to expected
variance from one quarter out to fourteen years are priced at essentially zero (Dew-Becker, Giglio, Le, &
Rodriguez, 2017). Read one way this is adverse: an engine bearing risk at horizons the market does not pay for is
uncompensated for precisely the persistence a sustained drawdown has. Read the other way it is favourable: an
occupant that **rolls short-dated exposure** bears the one-month risk repeatedly, which is the risk the same
result says **is** paid, including through the drawdown. Which reading applies is a property of the occupant, not
of the pole. A behaviour compensated for absorbing a reporting-date imbalance is short-horizon and repeated. A
behaviour compensated for warehousing a disqualified credit holds a term position that clears over months. The
result therefore cannot be applied to the role in general, and any occupancy claim has to say which case it is.

**A support exists that the previous paragraphs do not capture, and naming it also names its failure mode.**
Dealers who buy volatility from clients through yield-enhancing structured products hedge that book contrarian,
buying the underlying as it falls, which mechanically dampens realised and implied volatility (BIS, 2024). That
flow is not restricted to jumps; it operates continuously through a decline, and dampened volatility is a real
cushion for a short-convexity position through exactly the grinding episode the paragraphs above leave unguarded.
It is also the same crowding that compresses the premium in Section 4, and supervisors read the combination of
persistently low implied volatility and heavily one-sided short-volatility positioning as a possible
**under-pricing** of risk rather than as protection (ECB, 2024). So the cushion is genuine, it is procyclical,
and it is withdrawn in the state where it would matter most.

**Which is what the cap owed in Section 4 has to be sized against.** A loss budget for this engine cannot lean on
compensation widening, because the widening mechanisms answer to acute episodes. It cannot lean on volatility
being dampened, because the dampening flow is what reverses in the state the budget exists for. The cap must be
denominated in the loss a bad state would produce with **neither** support present, and expressed as a
scenario-loss budget at the level of the role rather than as a limit on position size, since different
constructions lose different multiples of notional in the same state. That is a requirement this paper states and
does not discharge.

**Two further gaps, disclosed rather than resolved.** The responder is late by construction at the **onset** of
any decline, fast or slow, so a window exists at the start of a sustained episode in which both halves can be
losing and which conditioning on duration alone would not isolate. That is a genuine hole in the Floor pairing,
and it is one the roster already anticipates: the tier above exists precisely because the responder's signal must
accumulate before it acts, so the book covers the onset even where the pairing does not. And this section treats
duration only. Trend's crisis performance also degrades when average cross-asset correlation enters an extreme
regime, which is a second and duration-independent way the responder fails; that evidence is corroborating only,
and its presence means the account here is not exhaustive.

**One caution, about an observation that appears to refute all of this.** Implied volatility can rise sharply
through a sustained decline, which is tempting to read as the engine being paid more exactly when it needs to
be. It is not. A rising surface reprices inventory already held **against** its holder; what widens is
compensation on positions taken from that point forward. Rising implied volatility through a grinding decline
is therefore consistent with the engine losing money throughout it.

**Why nothing currently settles it.** The external test does not exist, and the internal one is unavailable:
the paired-book measure prices the joint loss but cannot attribute it between the halves, and attribution
would need a de-smoothed series the corpus does not hold at any frequency. The verdict on the Floor's first
half is therefore **indeterminate, and may remain so rather than pending**, since no protocol available today
distinguishes a bounded protracted loss from an unbounded one for this pairing. The second half is not
indeterminate at all. Compression is documented, and the consequence for the runway follows.

*Section 5: 1,270 words, budget 1,200.*

## 6. The collision with the tier above

The roster does not stop at the Floor, and the tier above it constrains what this engine may sell.

The responder is late by construction: its signal must accumulate before it turns, so a decline that completes in
days is over before its exposure has reversed. The architecture paper places a separate tier above the Floor for
exactly that reason, tasked with the fast and vertical segment the responder cannot reach (Section 4.2), and it
sizes that tier as a budget line: a cost paid continuously, recovered only in stress, and justified against the
alternative of simply de-risking (Section 5.4). The book, in other words, has **already bought** the deep fast
crash, and it is paying a standing premium for it.

That purchase bounds this engine. A behaviour that earns primarily by selling the same deep crash the tier above
holds puts the book on both sides of one exposure. The premium received offsets the premium paid, the two
positions net toward nothing in the state they both reference, and what the book retains is the transaction and
financing cost of having held both. Such a behaviour is therefore **inadmissible for this role regardless of its
standalone return**, and the point is worth stating in that direction: the result is not that income can be
separated from the deep crash, it is that within this roster it **must** be.

The bound is real and it is not a number this paper can supply, for a reason worth being explicit about. How far
an occupant may sell into the crash depends on **which behaviour occupies the role**, because different
behaviours concentrate their losses at different depths, and the architecture paper deliberately never picks
occupants. It can assign the fast-deep segment to a tier; only a study of the role can say what a given occupancy
may therefore sell. What this paper states is the constraint and its derivation. The numeric boundary belongs to
whichever occupant is being assessed, and asserting one here would be inventing a constant to look precise.

**The dependency has to be stated where the bound is asserted, not only in a footnote.** The bound holds
**within this roster**, and it holds because the tier above owns the fast-deep segment and thereby creates the
collision. A book with no equivalent tier has not bought that crash and is not bound by this constraint at all;
its income half would be free to sell into a region this one may not. The claim is therefore conditional on an
architecture, which is the appropriate scope for a study commissioned by that architecture, and it should not be
read as a general result about income sleeves.

**This is also where the structural failure route from Section 1 completes.** The contract fails structurally if
its second and third clauses cannot be satisfied together given this roster. Section 5 examined one way that
could happen, where the inventory's loss arrives while the responder is already bleeding. This section supplies
the other: if the tier above has bought so much of the crash that the region left for the engine to sell contains
no inventory worth carrying, then the second clause is satisfiable only vacuously and the role has been squeezed
out from above rather than defeated from outside. Both routes are proofs about a particular roster. Neither is a
tally of candidates that failed, and the difference matters, because only the structural route can reach a
negative conclusion at all.

*Section 6: 577 words, budget 700.*

## 7. What the contract excludes

A contract earns its keep by rejecting things, and the rejections are more informative than the admissions,
because a criterion that admits everything proposed to it is not doing work. This section takes one behaviour
that satisfies the clause most readers assume is the demanding one and fails on a clause that looks easy.

Consider liquidity provision at short horizons in a narrow cross-section: taking the other side of participants
who need to transact immediately and are willing to pay for immediacy, then unwinding as the imbalance clears.
The payer is identifiable and is acting under something very like compulsion, since the demand for immediacy is
not a view about value. The behaviour carries genuine inventory risk while positions are held. And its losses do
not obviously arrive where the responder's do.

On the third clause it does well. Its exposure is short-lived and its bad states are episodes of disorderly
trading rather than sustained directional declines, so its loss does not naturally coincide with the protracted
drawdown in which the responder is finally paid. A screen built on decorrelation from the responder would pass
it, and might pass it comfortably.

It fails the **first** clause, and it fails it in a way that decorrelation cannot detect. Compensation for
supplying immediacy is largest when immediacy is scarce, which is to say during stress. Its income is therefore
concentrated in the same states where the responder is earning, and thin in exactly the calm and choppy
conditions where the responder is bleeding and the Floor needs the bleed met. As an occupant of this role it
would deliver its income when the Floor least needs it and little when the Floor most does. It does not fund the
wait; it arrives alongside the payoff the wait was for, which duplicates the responder rather than complementing
it.

That is the discrimination the contract exists to perform, and it is why the third clause was stated over states
rather than over correlations in Section 1. Read as decorrelation, the clause admits this behaviour. Read as the
Floor's additive condition, where the engine's income has to meet the responder's bleed while it is being
incurred, the behaviour is excluded on the timing of its income rather than on the placement of its loss.

One thing this case is not, and the distinction matters because Section 1 used a similar word. This is not a
falsifier for the paper's central claim. It is a candidate that fails admission, which demonstrates that the four
clauses discriminate among behaviours that a looser specification would treat as interchangeable. A refutation of
the claim in Section 3 would look entirely different, and is stated there. A behaviour failing the contract tells
us the contract has content. It tells us nothing against the contract.

*Section 7: 464 words, budget 600.*

## 8. What is discharged, what is handed back

The architecture paper commissioned this study to show that the Floor's income role holds on its own terms. That
commission is **half discharged**, and the halves should be named separately rather than averaged.

What holds is an argument, not a measurement. The role can be stated as a contract with four clauses and a
declared failure state. Its payer can be identified more precisely than the parent paper needed to: what a rule
**does** decides whether the compensated function is capacity-provision or risk-bearing, and a risk-bearing
allocation is confined to the price-type cells regardless of who occupies it. Fair pricing therefore becomes a
derivation rather than a disappointment, which in turn means the role cannot be justified by its price and must
be justified by its shape, and the shape is the inventory the long pole cannot supply for itself. Within this
roster the inventory is bounded from above by what the tier above has already bought. Those results stand or fall
on reasoning that a reader can check without a return series, which is the form the parent paper's own method
requires.

What is handed back is a list, and it is not short. The forward cap this argument shows to be necessary has no
numerical content here, and Section 5 establishes that it cannot lean on either of the two supports one might
expect. The first half of the Floor's condition is **indeterminate and may remain so**, because no test that
would settle it exists internally or externally. The binding constraint is directly observable in only one of the
venues discussed. And the admission criterion, though derived rather than counted, is corroborated by few cases,
because most candidates fail an earlier clause before the criterion is reached.

**One result is larger than this study and is returned upward.** The derivation in Section 3 nowhere uses a
property of an income sleeve. It constrains **any** risk-bearing allocation, including the long pole and any
tier the roster may add later, so it is a constraint on the roster rather than on this role. The parent paper
does not currently carry it. It is offered as a finding for the revision that paper already plans, not as a
correction to what it argued.

Two disclosures belong here rather than in a footnote. A substantial share of the point estimates this series
relies on originate with firms that sell the strategies concerned; the argument above was built to survive their
removal, and the results that survive most cleanly are those resting on central bank research, on
non-commercial academic work, and on the derivation itself, which requires no estimate at all. And this study
argues largely against its own predecessors' summaries of the literature rather than against live external
counter-positions, which is the documented method of a paper series built this way and is also a limit on how
adversarial the argument has actually been.

Three questions are seeded rather than answered. First, whether a scenario-loss budget for a short-convexity role
can be specified at the level of the role rather than the construction, which is what the cap requires. Second,
whether the co-movement of the two poles conditioned on drawdown **duration** behaves as the pairing needs, which
is a measurement nobody appears to have made. Third, whether price-type rules are systematically more occupiable
than the small number of cases here suggests, which is the direct empirical form of this study's central claim
and the one a referee should press hardest.

*Section 8: 578 words, budget 550.*
