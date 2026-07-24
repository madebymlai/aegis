# Budgeting Convexity: Diversification as an Order of Operations over Failure Modes

madebymlai \
*Aegis*

## Abstract

A multi-strategy book is usually assembled by counting mechanisms, with carry, global macro,
statistical arbitrage, and managed futures each admitted for its low average correlation to the
others. This paper argues that the count is the wrong organizing principle. Stress co-movement is
governed by the sign of a strategy's convexity to the common shock rather than by its mechanism label,
so a book diversified by mechanism can still be a single short-gamma position that comes due in the one
regime where every seller of protection is repriced at once. We develop diversification as an order of
operations over failure modes on the convexity axis. Convexity defines the two poles a book must span
and the net-convex property it must hold as a whole, the economic job each sleeve performs builds a
tiered roster, and allocation budgets risk rather than skew. The claim the argument rests on is that
skew classifies but cannot budget. Its sign is fixed in advance by the mechanism that produces it, but its
magnitude is a tail-dominated, horizon-unstable, asset-class-specific statistic that cannot anchor a
stable target. Net-convexity is therefore sourced structurally and verified by observation rather than
solved as a live constraint. We show that return-timing of convexity fails out of sample while
risk-conditioning survives, and we scope the resulting construction against its strongest published
counter-evidence. The paper is integrative: it frames three role-specific studies that test each
sleeve on its own terms.

**Keywords:** portfolio construction, convexity, tail risk, risk budgeting, trend-following,
diversification.

---

## 1. Introduction

An allocator who diversifies by mechanism ends with a book that looks varied and is secretly one
position. Carry, global macro, statistical arbitrage, and managed futures carry different names,
different desks, and different stories, and across ordinary months they earn their keep as a set of
low-correlated return streams. The correlations that justify holding them together, however, are
conditional. They are estimated over samples dominated by calm, and they collapse in the single
regime that decides survival, the sharp and correlated drawdown in which liquidity withdraws and
every seller of protection is repriced at once. In that regime the mechanism labels stop mattering
and a common exposure surfaces. The book that looked most diversified turns out to be the most
exposed, because most of its sleeves were short the same convexity to the same shock.

The field's standard question makes this outcome likely rather than accidental. The question is
usually posed as how many low-correlated premia an investor should harvest, and it is answered by
counting mechanisms and inspecting an average correlation matrix. Counting is the wrong verb because
average correlation is precisely the statistic that conditional co-movement defeats. A book selected
to minimize average pairwise correlation will accumulate sleeves that are independent in calm and
identical in crisis, since the estimator that governs selection is blind to the state in which the
sleeves converge. The selection procedure and the failure mode are therefore aligned in the wrong
direction: the more diligently the book is diversified by the usual metric, the more reliably it
concentrates the exposure that matters. Correlation counting does not merely miss the risk; it
recruits for it.

Where the literature does reach past correlation toward the shape of the payoff, it reaches for
skewness, and it makes a second error. It treats skew as a lever to balance, a quantity to be set to
some target across the book, rather than as a property to be read. The move is understandable, since
skew is the natural summary of the asymmetry the book is trying to control, and setting it to a
target looks like the disciplined thing to do. The move is also mistaken, for reasons this paper
develops at length: the quantity a book would need to budget against is not estimable stably enough
to serve as a target, even though the property it names is knowable. Reaching for skew as a lever
imports all the estimation fragility of the third moment into the one decision the construction
cannot afford to get wrong.

We argue instead that diversification is an order of operations over failure modes, organized on the
convexity axis, and three commitments follow. First, convexity, the sign of a strategy's payoff
curvature with respect to the common shock, defines the two poles a book must span and the net-convex
property it must hold as a whole. Second, the economic job each sleeve performs, rather than its
mechanism, builds the roster, and the roster is tiered so that each tier fixes a failure the tier
below it cannot. Third, allocation budgets risk, sources convexity structurally, and observes skew without
ever budgeting it. Together these commitments replace a problem of selection by count with a sequence
of role decisions on a single axis.

The thesis the reader should hold leaving this section is compact. Diversification is an order of
operations over failure modes on the convexity axis: budget risk across the roster, source convexity
structurally, and treat skew as a classifier you observe, not a budget you solve. The remainder of
the paper earns each clause in turn. Section 2 establishes the convexity axis and shows that each of
its poles is backed by a payer with a structural reason to keep paying. Section 3 is the pivot, and it
shows that skew can label a pole but cannot anchor a budget. Section 4 builds the tiered roster as an
order of operations. Section 5 realizes the roster in construction, budgeting risk and sourcing
convexity structurally while observing skew. Section 6 states what this integrative paper asserts now
and what it defers to the three role-specific studies that follow it.

## 2. The convexity axis and its two poles

The axis that organizes the book is neither the mechanism nor the average volatility. It is the sign
of convexity to the common shock. The task of this section is to show that the axis is real, that it
is recovered by independent methods rather than resting on any single research program, and that each
of its poles is anchored by a payer whose incentive to keep paying is structural. If any of these
three claims failed, the axis would be a description rather than a foundation, and the roster built on
it in Section 4 would inherit the weakness.

### 2.1 Reward lines up with the sign of convexity

Across liquid strategies, the cross-section of risk-adjusted return aligns with negative skewness
rather than with volatility. Lempérière, Deremble, Nguyen, Seager, Potters, and Bouchaud (2017) show
that strategies earning a premium are, as a class, short convexity: they collect a steady carry and
pay out in the tail, and their Sharpe ratios scale with how negatively skewed they are rather than
with how volatile they are. Trend following is the clean outlier on the other side, a positive-skew
strategy that pays in the tail and bleeds in calm, and a companion study places it on the same line
extended out of sample to option strangles (Dao et al., 2017). The finding matters for
construction because it identifies the compensated quantity. What an investor is paid for is not
variance, which the volatility target will manage, but the sign and size of the payoff's curvature in
the shock, which the roster must deliberately span. Because both studies come from a firm that runs
these strategies, the conflict of interest is disclosed and the axis is not permitted to rest on them
alone.

Two independent methods with no product interest recover the same axis by different routes. Lettau,
Maggiori, and Weber (2014) build a downside-beta conditional CAPM in which a single price of downside
risk jointly prices equities, currencies, commodities, sovereign bonds, and options, explaining on
the order of three-quarters of the cross-section where the unconditional CAPM explains essentially
none. Their downside beta is a direct measure of convexity to the common shock, since it captures how
much an asset loses precisely when the market falls hardest, and the assets that lose most in that
state earn the most on average. Bollerslev and Todorov (2011) reach the axis from option prices,
decomposing the compensation for diffusive variance from the compensation for jumps and showing that
the fear of discrete crashes accounts for roughly two-thirds of the equity premium and more than half
of the variance risk premium. Three methods, an anomaly cross-section, a downside-beta asset-pricing
model, and an option-implied jump decomposition, converge on one conclusion: the reward is
compensation for the sign and size of convexity to the shock. Convergence across independent methods
is what turns a stylized fact into an axis a book can be built on.

### 2.2 The short pole and its payer

The short-convexity pole is the seller of insurance, and its payer is structural insurance demand.
Variance sellers earn a premium because they absorb crash risk that other participants will pay to
shed. Carr and Wu (2009) document a large and systematically negative variance risk premium across
equity indices, and Bollerslev, Tauchen, and Zhou (2009) show that the same premium forecasts returns,
a predictability their equilibrium model traces to time-varying uncertainty about future volatility.
That the compensation is in large part specifically for discrete, jump-driven losses is the separate
finding of Bollerslev and Todorov (2011), recovered from option prices in Section 2.1. Ilmanen (2012) restates
the relationship in its cross-asset form, showing that buying insurance, whether through options, safe
bonds, or low-beta equities, is poorly rewarded on average across markets. The demand on the other
side of this trade is not a mispricing that a clever arbitrage competes away. It is the
price-insensitive need of hedgers, mandate-constrained institutions, and lottery-seeking buyers to
hold protection, and that need does not go on sale when the premium widens. Inelastic demand is
necessary, however, and not sufficient. A price-insensitive buyer facing abundant sellers pays little,
so the premium depends on the capacity of the side selling protection as much as on the urgency of the
side buying it. Gârleanu, Pedersen, and Poteshman (2009) make the dependence concrete, showing that
option prices move with end-user net demand because market makers cannot hedge perfectly and must be
paid to absorb the imbalance, which is why index options, where end users are net buyers, carry the
premium while single-stock options, where end users are net suppliers, do not. The short pole is paid
for bearing unhedgeable risk where the intermediary's capacity binds, and the size of that payment
tracks the constraint rather than a fixed preference. Identifying the payer this concretely, and
identifying what governs the price it pays, is what lets the roster treat the short pole as an income
source with a stated condition rather than a temporary edge, a distinction the argument leans on
when Section 4 assigns it the Floor's income role. The premium's durability is what earns that
assignment, because a Floor funded by a transient edge would leave the responder unfunded in the first
regime that closed the edge, which is the regime the responder exists to survive.

### 2.3 The long pole and its payer

The long-convexity pole is trend following, and its convexity is structural rather than incidental to
any particular signal. Fung and Hsieh (2001) show that a trend follower's return profile replicates a
portfolio of lookback straddles, which makes it long gamma with respect to sustained moves by the
mathematics of the payoff rather than by the cleverness of the rule. Capital Fund Management (2018)
makes the mechanism explicit, writing a trend program's profit as one-half the difference between the
squared cumulative move and the summed squared daily moves, a quantity that is convex in the size of
the realized trend but truncated by the position sizing that keeps risk bounded. That truncation is
worth naming now, because it is the tension Section 5 must manage: the same risk control that makes
the sleeve investable also caps the convexity it is held to deliver. The payer on this pole is the
hedger. Moskowitz, Ooi, and Pedersen (2012) document time-series momentum across dozens of markets
and attribute its return to speculators being compensated for absorbing the flow of hedgers who trade
against the trend. Kang, Rouwenhorst, and Tang (2020) read the same relationship as an insurance
premium that hedgers pay to speculators at longer horizons. Their reading disciplines any temptation
to label trend returns as pure alpha, since a return with an identifiable counterparty and a
risk-premium interpretation persists for a reason the roster can rely on, whereas skill does not carry
the same guarantee. The risk-premium reading is adopted deliberately, because it is what the persistence
argument of Section 2.4 requires; the same literature also offers an under-reaction and
slow-information-diffusion account of time-series momentum (Moskowitz, Ooi, and Pedersen, 2012), which
is compatible with a hedger-paid premium and which the argument here does not need to adjudicate.

### 2.4 Why the payers stay

Both poles rest on the same persistence argument, which is stated once here and reused wherever a
later claim depends on it. A premium survives not because it is hidden but because arbitrage against
it is bounded. Shleifer and Vishny (1997) show that arbitrageurs are least able to correct a
mispricing exactly when it is largest, because that is when their capital is most impaired and their
backers most likely to withdraw, so the very episodes that would discipline the short-convexity seller
are the episodes in which the disciplining capital has already left. De Long, Shleifer, Summers, and
Waldmann (1990) add that unpredictable sentiment is itself a priced risk, which deters arbitrage even
in the absence of fundamental risk and keeps prices away from fundamental value. Gromb and Vayanos
(2010) survey the full menu of constraints, from short-sale and leverage limits to margin calls and
equity-capital frictions, that keep a payer from leaving the trade. McLean and Pontiff (2016) supply
the guard the whole research stance requires, showing that predictability decays after publication, by
roughly a quarter out of sample and by more than half once a strategy is documented. The two poles
qualify against this guard because their payers are structural rather than informational. Insurance
demand and hedging pressure are not corrected by the publication of a paper, so the premiums they fund
are not the kind that a citation closes.

Publication is not the only way a premium dies, however, and a taxonomy with only these two categories
is incomplete. A third decay mode sits between them: a premium immune to publication but not to
capital, sustained by the constrained capacity of the specialists who bear the risk rather than by any
secret about its existence. It decays when capital enters the specialist's balance sheet, which no
journal triggers and no disclosure prevents. The short pole is of this third kind, and two unrelated
markets show the mode operating. Dew-Becker and Giglio (2025) document that the S&P 500 variance risk
premium, large and negative for decades, has earned approximately zero since around 2010, dating the
break to the point at which dealer net index gamma stopped being reliably negative. Tomunen (2026)
finds the same pattern in catastrophe bonds: the premium is proportional to the intermediary's capital
constraint, it fell sharply after the financial crisis as institutional money flowed into the specialist
funds, and it has since become less responsive to disasters, barely reacting even to the record insured
losses of 2017. One mechanism, two markets, one decay path.

Two cautions keep this from being read as more than it is. The synthetic options carrying Dew-Becker
and Giglio's century-long result are replicated by daily delta-hedging, which cannot span a jump by
construction, and the authors note that a jump-tied premium would appear in the wedge between traded
and synthetic returns rather than in the synthetic leg's alpha, so their evidence dates a compression
rather than establishing that compensation for discrete losses was never priced. The break date is also
unsettled, with Bates (2022) placing it at 2017 rather than 2010 on separate methodology. What survives
is the direction, not a date.

The consequence is a change in the form of the claim rather than its content, and the conditional form
is the more durable. The short pole pays while the specialists' capacity to supply protection is
constrained and compresses as that capacity grows, a condition that can be watched through intermediary
positioning and through specialist capital measured against the risk on offer, and watched before a
drawdown rather than only after one. A book that treats the premium as a constant will be surprised by
the state that removes it, and a book that treats it as constrained-capacity rent will not. The axis, then, is not a stylized fact of one dataset but a
structure recovered by three independent methods and anchored by two payers whose incentives rest on
constraint. This invites an obvious next step, to budget the book by the sign of skew that defines the
poles, and Section 3 shows why that step fails.

## 3. Why convexity classifies but cannot budget

The organizing property of the axis is the sign of convexity, and it is tempting to promote that
property from a label into a lever, to set a target for the book's net skewness and allocate to hit
it. This section is the pivot of the paper, and its claim is that the promotion is illegitimate. The
sign of skew is knowable in advance, but its magnitude is not estimable stably enough to anchor a
budget, so skew can classify a pole and cannot size one. The argument runs from a property of the
statistic, through the evidence that confirms it, to the construction consequence that closes the
naive route.

### 3.1 The third moment is tail-dominated

The argument is fixed before any data by the arithmetic of the statistic. Skewness is an average of
cubed deviations, and cubing hands almost all of the weight to the few largest observations, so a
sample estimate is dominated by a handful of tail prints and can flip on the arrival or omission of a
single crisis. This is a property of the estimator rather than a finding about markets, which is why
it can be asserted in advance of any test. It has an immediate and asymmetric consequence for use. The
sign of skewness, meaning which tail is fat, is identifiable from the mechanism that produces it and
is stable across samples, whereas the magnitude is a high-variance estimate of a quantity that one
event can rewrite. Classifying a pole requires only the sign, and the sign is available. Budgeting a
book requires the magnitude, and the magnitude is not. The rest of the section shows that the evidence
behaves exactly as this asymmetry predicts, which is the sense in which a backtest here estimates a
property already known rather than discovering one.

### 3.2 Sign stable, magnitude unstable

The evidence estimates precisely what the arithmetic predicts. Harvey and Siddique (2000) established
that systematic coskewness is priced, at roughly three to four percent per year, and thereby gave the
classifier its empirical origin. Revisiting the premium over the following two and a half decades out
of sample, Harvey and Siddique (2023) find that its sign is remarkably durable, staying positive
across periods in which value and momentum reverse, while its estimated magnitude swings across a wide
range, from roughly two to four percent in their headline estimates and considerably wider across their
robustness specifications depending on research choices, and they
remark directly on how challenging higher moments are to measure. Anghel, Caraiani, Roșu, and Roșu
(2023) replicate the premium but report that the standard proxy is very noisy and that the pricing
evidence is inconclusive, failing significance at conventional thresholds. None of this contradicts
the existence of the premium. It confirms the paper's claim about its use, because the feature that
survives across samples is the sign while the number a budget would require is the one that will not
hold still. A construction that leans on the durable feature is on firm ground, and a construction
that leans on the fragile one is not.

### 3.3 Skew is asset-class-specific, not universal

The second reason skew cannot anchor a book-level budget is that it is not a uniform property of a
strategy family. Koijen, Moskowitz, Pedersen, and Vrugt (2018), with the AQR affiliation behind the
carry research disclosed, decompose carry across asset classes and find that its skewness is a fact
about where carry is run rather than about carry as such. Currency and option carry are strongly
negatively skewed, equity, Treasury, and credit carry are positively skewed, and a diversified global
carry factor has negligible skewness. The sign is fixed by mechanism, which is what makes it knowable
in advance. Brunnermeier, Nagel, and Pedersen (2008) identify that mechanism for the negatively skewed
case, showing that currency carry's crash risk arises from the funding-liquidity unwind of crowded,
leveraged positions, a channel that is present in FX and absent where funding pressure does not apply.
The question of whether a given carry sleeve is concave is therefore answered by asking whether the
funding-unwind mechanism operates in it, rather than by estimating a third moment from its returns. A property
that changes sign across the members of a single family cannot be the variable an entire book is
budgeted against, because the budget would be sizing a quantity whose meaning is not even constant
across the sleeves it is meant to weigh.

### 3.4 You cannot budget on skew directly

Attempts to optimize directly on higher moments are revealing precisely because they can be made to
work only under demanding conditions. Martellini and Ziemann (2010) show that portfolio selection with
higher moments dominates mean-variance analysis out of sample only once substantially improved, more
robust estimators of coskewness and cokurtosis are used; with ordinary estimates the advantage is
absent. Lassance and Vrins (2023) reach a related result from a different direction, showing that
improving a portfolio's higher moments requires deliberately moving off the mean-variance-efficient
frontier and accepting a higher variance in exchange, and that the gain is available only through a
carefully constructed distance-minimizing objective rather than through direct optimization on
estimated skewness. The common lesson is that higher-moment optimization becomes viable only with
estimation machinery far more elaborate than a raw third-moment target, and even then it buys a modest,
method-dependent edge. A book cannot be sized on a net-skew target, which is the construction-side
counterpart of the statistical property in Section 3.1: the sign is knowable, but the magnitude is not
robust enough to optimize against directly.

### 3.5 Skew still ranks, even where it cannot budget

The claim must be stated precisely, because there is genuine evidence on the other side and
overstating the point would be false. Baltas and Salinas (2022) show that realized skewness is a
pervasive cross-sectional predictor, so that sorting assets within commodities, bonds, equities, and
currencies on their recent realized skew produces a robust long-short premium, with a cross-asset skew
strategy earning a Sharpe ratio near three-quarters that holds up across measurement choices. Le et
al. (2023) show that option-implied skew forecasts realized skew well enough, explaining up to about a
third of its variation, to improve portfolio choice. Both results are real and neither is dismissed.
What they establish is that skew ranks assets against one another, which is a relative and repeatedly
sampled comparison, and that option-implied skew is a usable forward signal. What they do not
establish, and what this paper denies, is that a book's net skewness is a stable enough quantity to
serve as an allocation target. The operative distinction is between cross-sectional skew ranking and
option-implied skew, which are tradeable signals, and book-level net-skew budgeting, which is not. The
difference is between an ordinal, repeatedly resampled comparison and a cardinal, point-estimate target:
a cross-sectional rank only has to order assets correctly on average across many rebalances, which the
noisy third moment can manage, whereas a book-level budget needs the magnitude of a single net figure to
hold still, which it cannot. Skew is a classifier and, cross-sectionally, a signal, and it is never a
passive label. Pyun (2019)
adds the closing observation from the timing side, showing that the predictive coefficients on the
variance risk premium are themselves unstable out of sample, so any attempt to time the book's
convexity through a skew or variance-premium signal inherits that instability. If skew classifies but
cannot budget, the organizing variable of the book cannot be a moment at all. It must be the economic
job each sleeve performs, and Section 4 builds the roster from those jobs.

## 4. The roster

With skew demoted from lever to classifier, the book is organized by what each sleeve is for. The
organizing idea is an order of operations, in which roles are added in a sequence such that each tier
fixes a failure the tier below it cannot, and the sequence exists specifically to avoid the failure
that counting mechanisms produces. The roster has three tiers, a Floor, a Target, and an Expansion,
and the order among them carries the argument. A book that admitted the same sleeves in a different
order, or admitted them for their labels rather than for the failures they repair, would not be the
same book even if its holdings coincided on an average day.

### 4.1 The Floor: one sleeve funds, one responds

The Floor spans both poles of the convexity axis with two sleeves of opposite sign, a convergent
income engine that sells convexity and earns the calm-market carry, and a persistent-crisis responder
that buys convexity and pays in protracted drawdowns. The pairing is chosen because the two are
mutually diversifying in exactly the states that decide the book. Bhansali, Davis, Dorsten, and
Rennison (2015), with the PIMCO affiliation disclosed, show that carry and trend are complementary
across roughly twenty markets over half a century, with the diversification concentrated in the
extremes rather than the middle, which is where a book most needs it. Olszewski and Zhou (2013)
demonstrate the effect concretely in currencies, where an equal combination of momentum and carry
lifts the Sharpe ratio above either component and improves the Calmar ratio substantially. The
responder half of the Floor is trend, which Hurst, Ooi, and Pedersen (2017), again with the AQR
affiliation disclosed, show to have been positive in every decade since 1880 and strongest in
low-correlation environments, the substrate condition it requires to work. Its crisis behavior is a
dynamic de-risking rather than a static hedge, and Asif, Frömmel, and Mende (2022), writing from
outside the managed-futures industry, confirm that trend's crisis alpha comes from its ability to cut
exposure to the crisis market quickly, in under fifteen days for the composite indices they study. The two halves compose into a Floor in which one
sleeve funds the wait and the other pays for it once the drawdown lasts, which is a more robust
arrangement than either sleeve alone because neither is asked to do the other's job. The pairing also
does specific work against the conditional-correlation trap described in Section 1. Two sleeves chosen
for low average correlation can still be short the same convexity to the common shock, whereas two
sleeves chosen for opposite convexity are constructed to diverge in precisely the state where average
correlation misleads. The Floor is therefore diversified on the axis that governs stress rather than
on the axis that governs calm, which is the difference between a pairing that survives the drawdown
and one that merely looks balanced before it arrives.

### 4.2 The Target: closing the responder's speed gap

The Floor's responder has a structural weakness, and the Target exists to repair it. Trend is late by
construction, because its signal must accumulate before it turns, so a fast and vertical crash that
completes in days is over before the responder has reversed its exposure. Noguer i Alonso and
Al-Fallouji (2026) formalize this separation analytically, showing that a put option reprices on the jump
the instant it occurs while a trend signal must cross zero before it acts, so the two instruments
cover different segments of the same drawdown. The Target tier is the immediate defense that covers
the fast segment, and its benchmark is set by two results that also fix its size. AQR (2020a), with its
affiliation disclosed, contrasts puts and trend and finds that puts pay in fast crashes while trend
pays in protracted bears, and, crucially for sizing, that slow drawdowns inflict more cumulative
damage than fast ones. That asymmetry is why trend is the workhorse of the defense and the tail is the
supplement rather than the reverse. Baltussen, Martens, and van der Linden (2026) show across two
centuries that a defensive-factor sleeve arrives with negative beta at the onset of a dislocation
while trend improves as the dislocation persists, so the two defenses are complementary in time rather
than redundant. The Target is defined by the segment of the drawdown it must cover and is not a timer
that tries to predict when the crash will arrive. Keeping it a role rather than a forecast is the
discipline Section 5 has to enforce, because the temptation to convert a defensive sleeve into a
market-timing bet is exactly where construction usually fails. Sizing follows from the same asymmetry
the AQR evidence identifies. Because the slow drawdown does the greater cumulative damage and the
trend responder already covers it, the Target is sized as the smaller and faster supplement that buys
only the days the responder cannot reach. Oversizing it would pay a large continuous premium to cover
the segment of the drawdown that inflicts the least cumulative loss, which inverts the cost-benefit the
evidence describes. The tier's size is therefore set by the speed gap it closes rather than by the
severity of the crash an investor happens to fear.

### 4.3 The Expansion: breadth, gated and last

The Expansion tier holds off-axis, market-neutral sleeves whose contribution is neither income nor
defense but breadth, and it is admitted last and only under a gate. The value of breadth is stated by
Grinold's (1989) fundamental law of active management, in which the information ratio scales with the
information coefficient times the square root of breadth, where breadth counts independent bets rather
than positions held. Meucci (2009) makes the count operational as the effective number of bets, the
exponential of the entropy of the uncorrelated risk contributions, and Choueifaty and Coignard (2008),
whose diversification-ratio metric underpins a fund marketed by the first author's firm TOBAM, give the
closely related diversification ratio, whose square is commonly read as the number of independent risk
factors in the book. Breadth belongs in a paper about tail behavior, and not only in a paper about Sharpe
ratios, because its payoff concentrates in stress. Carli, Deguest, and Martellini (2014) show that the
effective number of bets predicts performance specifically in bear markets, which means genuine
orthogonality is a defense in its own right and not merely an efficiency in calm. The raw material for
the tier is available, since Baltussen, Swinkels, and van Vliet (2021) document two dozen factor and
asset-class premiums that survive multiple-testing controls over two centuries. The gate is the point
of the tier. An Expansion sleeve is admitted only when it adds an independent bet to the book, never
for its mechanism label, because a sleeve that is orthogonal in calm and correlated in crisis adds a
name and not a bet, and the whole roster exists to keep names from being mistaken for bets. The gate
also explains why the tier comes last rather than first. Breadth is valuable only once the Floor and
Target have already spanned the convexity axis, because an off-axis sleeve added to a book that is
still unbalanced improves the average statistics while leaving the crisis exposure untouched. Admitting
Expansion early would let orthogonality in calm stand in for a defense the book does not yet possess,
which is the precise substitution the order of operations is built to prevent. Breadth earns its place
only after the failures beneath it have been repaired. The gate metric matters as much as the gate
itself. Counting positions would readmit the very error the roster was built to reject, because a book
can hold a great many positions that all load on a single factor, whereas counting independent bets in
the sense of Meucci (2009) measures the quantity that actually diversifies a drawdown rather than the
quantity that pads a holdings list. An Expansion sleeve that raises the effective number of bets has,
by construction, added risk the existing tiers do not already carry, which is the only kind of addition
the tier is permitted to make. A sleeve that leaves the number unchanged is redundant however novel its
mechanism sounds.

### 4.4 The failure the order avoids

The order of operations is not an aesthetic preference but the antidote to a documented failure.
Brown, Gregoriou, and Pascalau (2012) show that beyond roughly twenty funds, adding more sleeves to a
fund of hedge funds raises left-tail risk and lowers returns, which is the opposite of what naive
diversification promises. The mechanism is the one the paper opened with. Sleeves selected for low
average correlation accumulate a common short-convexity exposure, and past a threshold the marginal
sleeve adds crisis correlation faster than it adds independent return, so the book's tail gets worse as its roster gets longer. This is the count-diverse book collapsing into a single short-gamma
position, now documented rather than asserted. The roster's order is the defense against it, because
each tier is admitted to repair a named failure the tier below it cannot, and no tier is admitted for
its label. Income cannot respond to a crisis, so a responder is added. The responder is late, so a
tail is added. The book is still exposed on one axis, so gated breadth is added. Order is what keeps
the book from becoming the very thing it was assembled to avoid, and it is the sequence, not the
inventory, that does the work. The contrast with correlation counting is exact. Where the count treats
every sleeve as interchangeable evidence of diversification, the order treats each sleeve as the answer
to a specific prior deficiency, so the book cannot accumulate redundant short-convexity exposure under
the appearance of adding variety. A roster assembled this way has a natural stopping point, because a
sleeve that repairs no remaining failure is simply not admitted, whereas a book assembled by count has
no principled reason to stop before it reaches the overdiversification that Brown, Gregoriou, and
Pascalau (2012) measure. This much the evidence compels: fewer and more purposeful sleeves beat
counting, and each tier here is forced by a named, documented failure the tier below it cannot repair.
What the evidence does not compel is that this particular sequence is the only defensible one. The order
defended here is non-arbitrary rather than unique or provably optimal, and a different author could
narrate an alternative ordering from the same failure-mode logic. Showing that the ordered roster does
real work beyond an unordered, equal-risk-contribution blend of the same sleeves, and that each role
holds on its own terms, is the task of the seat papers rather than a claim settled here. The roster
names the roles and fixes their order, and what remains is to realize them by sizing and holding the
sleeves without budgeting skew and without timing returns.

## 5. The construction

Realizing the roster raises one question at each sleeve, which is how much to hold and how to hold it.
The answer this paper defends is that the book budgets risk rather than returns, sources its
net-convexity structurally rather than solving for it, observes skew rather than constraining it, and
sizes the tail as a monetized cost budget. The section closes by scoping the construction against its
strongest counter-evidence, which concerns regime-conditional allocation. Throughout, the
architecture decisions and allocator of the system that motivated this work appear only as a labeled
illustration of one implementation and never as evidence for a claim, in keeping with the standard
that market behavior and ex-ante rationale carry the argument.

### 5.1 Budget risk, not returns

The construction budgets risk because the alternative does not survive contact with estimation error.
DeMiguel, Garlappi, and Uppal (2009) show that across a range of optimizing models, none consistently
beats the naive equal-weight portfolio out of sample, because the sample length required to estimate
the mean-return inputs reliably is far longer than any available history. The implication is not that
optimization is unsophisticated but that the return inputs are the problem, so a construction that
never estimates them sidesteps the failure at its source. Risk-based allocation does exactly this.
Maillard, Roncalli, and Teiletche (2010) give the equal-risk-contribution portfolio, which sizes each
sleeve so that all contribute equally to book risk and which generalizes cleanly to unequal risk
budgets when the roster intends a deliberate tilt. Lopez de Prado (2016) adds the hierarchical seam,
clustering correlated sleeves and allocating top-down so that a correlated group cannot dominate the
book, a structure that matches the roster's own grouping into Floor, Target, and Expansion. An honest
caveat travels with these methods and is stated plainly. The robustness that matters is generic to the
risk-based family and is not special to any one member of it, because recent evidence finds that
hierarchical risk parity does not reliably beat other risk-based methods or a Ledoit-Wolf-shrunk
minimum-variance portfolio out of sample (Trucíos, 2026). The claim the construction rests
on is to budget risk and not optimize returns, and it is not the narrower claim that a particular
risk-based method is superior to its siblings.

### 5.2 Conditioning the vol target

Sizing to a risk budget requires a risk target, and how the target is applied matters more than the
level it is set to. Bongaerts, Kang, and van Dijk (2020) show that conventional volatility targeting,
which scales exposure continuously and symmetrically by inverse realized volatility, fails to
consistently improve performance across global equity markets and can deepen drawdowns while
generating high leverage and turnover. Their conditional strategy adjusts risk only in extreme
volatility states, reducing exposure when volatility is high and raising it, subject to a capped
maximum leverage, when volatility is low, while holding exposure unscaled in between. It improves
Sharpe ratios and cuts drawdowns with materially lower turnover and leverage, and the gains are
concentrated in the high-volatility states, where volatility clustering is strongest and the
correlation between realized volatility and future return is most negative. The lesson the
construction takes is that a risk target should be conditioned on volatility state and bounded in
leverage rather than applied as a continuous symmetric peg.

### 5.3 Net-convexity by construction, not by solve

The book must remain net-convex as a whole, and the question is whether to enforce that property by
solving for it live or by building it in. This paper argues for building it in, and the argument is
ex ante before it is empirical. Holding a net-skewness target through time means running a live
optimization whose inputs are the very third moments Section 3 showed to be unstable, so the solve is
liable to swing its allocations on one crisis print and, at the boundary, to become infeasible and
halt the book. The alternative fixes the net-convex property by construction, through a stable
conviction tilt toward the structurally convex sleeves together with a convexity-premium tail, and
then observes the realized skew as a recorded diagnostic rather than a binding constraint. The market
evidence favors the structural route decisively. Cederburg, O'Doherty, Wang, and Yan (2020) show that
volatility-managed portfolios, which scale exposure by a conditioning signal, do not systematically
outperform out of sample, and that their in-sample gains are artifacts of structural instability in
the spanning regressions used to measure them. A broader study reaches the same verdict, finding that
once estimation risk and honest recursive implementation are imposed, volatility management and factor
optimization do not beat simple diversification (Feng, 2026). A signal
that scales convexity through time is a timing bet, and timing bets on this axis do not survive
out-of-sample scrutiny.

### 5.4 The tail as a convexity-premium budget

The Target tier is where budgeting convexity becomes literal, because a tail sleeve is a cost paid
continuously and recovered only in stress, so it must be sized as a budget and actively monetized
rather than held by default. Israelov and Nielsen (2015) and Israelov (2019) show that a standing
protective-put program delivers worse drawdown-per-unit-of-return than simply holding less risk, in
every environment except the sudden gap it is uniquely suited to, which means an always-on put is
usually the wrong default and the tail's cost must be justified against the alternative of de-risking.
The budget is made productive by monetization, and here the evidence must be read with care because it
comes largely from firms that sell the products in question. The one peer-reviewed anchor for the
specific claim that active monetization beats passive holding is Bhansali, Chang, Holdom, and Rappaport
(2020), published in this journal but authored at LongTail Alpha, which runs tail-hedging mandates of
the kind it studies. Two practitioner pieces corroborate it from firms with the same commercial
interest, and are cited as illustration rather than independent evidence: One River (2024), whose firm
sells convex-overlay strategies, finds that any disciplined rebalancing of a convex sleeve beats holding
it statically, with calendar rebalancing reducing path dependency; and Man Group (2022), whose firm
sells trend and overlay products, finds that a systematic overlay can reach a put-like convexity profile
at a positive rather than negative average return. Read conservatively, what the peer-reviewed record
firmly establishes is the narrower Israelov result, that a standing, unmanaged put is usually dominated
by simply holding less risk. The stronger monetization claim rests on evidence that is real but
conflicted, so the paper advances it as a design lean rather than as a settled finding. Schwalbach and Auret (2025) close
the loop, combining slow trend with an option tail as a portable-alpha overlay and improving outcomes
in all but one of the nine crisis episodes they study, which realizes as a construction the
slow-plus-fast complementarity that Section 4.2 argued for on structural grounds. The tail is therefore a budget
line, sized against the cost of simply de-risking and designed to be earned back through monetization rather than
through holding to the next crash, though the size of that monetization edge is the design lean advanced here rather than a settled result.

### 5.5 Reject return-timing; concede risk-conditioning

The construction rejects one thing sharply and concedes another precisely, and the boundary between
them is the paper's most contested line. What it rejects is return-timing of protection. AQR's tail
work states the case bluntly (Asvanunt, Nielsen, & Villalon, 2015): direct hedging adds value only for an investor who can both
time short-term crashes and unwind those hedges very shortly after, an ability the same work openly
doubts. The ex-ante
reason is the one the whole paper rests on. A crash signal computable from public prices is priced
into options before it fires, so by the limits-to-arbitrage logic of Section 2.4 its edge should not
persist out of sample, and Section 5.3's evidence confirms that scaled-signal timing does not. What
the construction concedes is that regime-conditional allocation genuinely beats static allocation out
of sample, and this evidence cannot be dismissed. Costa and Kwon (2019) show that a regime-switching
risk-parity portfolio consistently outperforms its nominal counterpart, Uysal and Mulvey (2021) show
that a machine-learning regime overlay improves risk-adjusted returns over nominal risk parity, and
Fleming, Kirby, and Ostdiek (2001) show that volatility timing carries real economic value that
survives transaction costs. The reconciliation is the risk-versus-return distinction that governs the
entire book. These results do not all sit on the same side of that line, and the difference is worth
drawing precisely. Fleming, Kirby, and Ostdiek (2001) condition on volatility alone, and their weights
ignore any time variation in expected returns. Costa and Kwon (2019) condition on a regime's covariance
and end in a risk-parity allocation. Uysal and Mulvey (2021) go further, driving their overlay from a
supervised estimate of the probability of an upcoming recession or market contraction, which is a
forecast of the crash and therefore falls on the far side of the line drawn here. We read that study as
evidence that regime-conditional allocation can beat static allocation, not as support for the
risk-conditioning distinction itself, and the construction proposed here does not adopt its forecasting
layer. Risk-conditioning survives the arbitrage argument that kills return-timing because realized risk is
comparatively stationary and estimable, whereas a return forecast is not. This distinction has to
survive an obvious objection. Realized volatility and forward returns are empirically entangled through
the leverage effect, since volatility spikes tend to coincide with falling prices, so a rule that cuts
exposure when realized volatility rises will often cut it into a declining market, which resembles a
lagging return-timing rule. The reply is that the two rules differ in what they must get right to add
value. A risk-conditioning rule reduces variance and tail exposure whether or not the market has
mispriced anything, and it is indifferent to the sign of the next return; it does not need a forecast to
be correct. A return-timing rule earns its keep only if it forecasts that next return, which is the
forecast that limits-to-arbitrage prices away. The leverage effect makes the two move exposure in the
same direction much of the time, but only the timing rule requires the move to be predictive, and it is
that requirement, not the direction of the trade, that the arbitrage argument defeats. The construction
therefore takes the permitted side of the line. Convexity must not be return-timed or crash-timed, it must be
sourced structurally and sized by risk-conditioning, and regime-conditional risk sizing is treated as
a defensible but contested refinement rather than as settled practice or as rejected error. Whether a
given role earns its slot is, correspondingly, a tail-aware verification question that this integrative
paper states as a principle and hands to the studies that follow.

## 6. Conclusion

This paper has argued that diversification is an order of operations over failure modes on the
convexity axis. The axis is real and recovered by three independent methods, and each of its poles is
backed by a payer whose incentive rests on constraint rather than on information, which is what allows a book
to be organized on it rather than on the shifting sands of average correlation. The property that
defines the poles, the sign of convexity, classifies them but cannot budget them, because the third
moment's sign is fixed in advance by mechanism while its magnitude is a tail-dominated,
horizon-unstable, asset-class-specific statistic that no book can be sized against. Organized instead
by economic job, the roster is tiered so that each tier repairs a failure the tier below it cannot,
and the order exists to avoid the documented failure of the count-diverse book, which is a single
short-convexity position wearing many names. Realized in construction, the book budgets risk rather
than returns, sources its net-convexity structurally rather than solving for it, observes skew rather
than constraining it, and sizes its tail as a monetized cost budget, rejecting return-timing while
conceding risk-conditioning on the permitted side of a clearly drawn line.

The contribution is a reordering of the construction problem rather than a new estimator. It moves the
hard decision off the third moment, where estimation error defeats it, and onto the sequence of roles
and the risk budget, where the inputs are stable enough to act on. The convexity axis supplies the
classifier that tells the roster what each pole is for, and the risk budget supplies the lever that
sizes them, so that skew is asked to do only the one job it can do reliably, which is to name a sign.
Read this way, the three commitments of the introduction are not three separate rules but one rule
seen from three sides: the book is organized on the axis that governs stress, assembled in the order
that repairs failure, and sized by the quantity that estimation can support.

The limits are those of an integrative paper and are stated without hedging. The roles here are
asserted and reconciled once, at the level of the roster, whereas the per-role economic proofs, the
specific ex-ante rationale and out-of-sample behavior of each sleeve, are the subject of the studies
that follow and are not established here. A revision of this paper is expected once those studies
deepen, and its claims should be read as the scaffold they will test rather than as their conclusion.
Two scope boundaries deserve restating. Regime-conditional risk sizing is left genuinely contested
rather than resolved, and no out-of-sample superiority is claimed for hierarchical risk parity over
inverse-volatility or shrinkage methods, only that budgeting risk beats forecasting returns. The
framework is falsifiable at its seams, which is where an integrative argument should invite attack. If
a role the roster asserts to be structurally convex were shown to earn its crisis payoff only when a
price-based timing signal was applied, or if book-level net-skew budgeting were shown to add stable
out-of-sample value after honest estimation, the order of operations defended here would have to be
rebuilt. Naming those failure conditions in advance is the same discipline the paper asks of every
sleeve it admits.

Two practical limits sit outside the argument but bear on whether it travels from the page to an
investment committee. First, most policy statements allocate by asset class or manager type rather than
by convexity role, so adopting this roster means re-underwriting the mandate and educating a board on an
unfamiliar taxonomy, and that organizational switching cost, not the statistics, is often the binding
constraint on adoption. Second, the actively monetized Target sleeve is costly to run and demands the
discipline to hold a line item that loses money through long calm stretches, a discipline the paper's
own persistence logic (Shleifer and Vishny, 1997) applies as readily to the allocator's own seat as to
the market's payers. A reflexive question deserves a direct answer rather than a dodge: could publishing
this framework shrink the very payers it relies on? Not through the channel the question usually
imagines. Insurance demand and hedging pressure do not read the journals, which is exactly the property
that separates them from a published return-timing signal that gets arbitraged away. The threat runs
through the other side of the trade instead. The short pole's premium is rent on constrained
risk-bearing capacity, and capacity responds to capital rather than to publication, so anything drawing
capital toward selling protection compresses the premium whether or not a paper is written. The
framework is exposed to a supply-side erosion it cannot talk its way out of, and the answer is not to
claim immunity but to state the condition and watch it.

Three role-specific studies follow this one and discharge its deferrals. A crisis-responder study
takes up the Floor's persistent-defense role, a convergent-engine study takes up the Floor's income
role, and a v-crash-defense study takes up the Target's fast-crash role. The Expansion tier has no
dedicated study yet and is left as a future family, to be admitted only under the breadth gate this
paper specified. Each study inherits from this paper a fixed job description and a payer to verify, and
each returns either a confirmed role or a revision to the roster's order. That exchange, a scaffold
offered here and tested there, is the reason the integrative paper and its seats are written as a set
rather than as a single document. Together the three studies will test whether the order of operations
defended here holds when each role is examined on its own terms, which is the examination this paper
has framed but deliberately not attempted.

---

## References

Anghel, D. G., Caraiani, P., Roșu, A., & Roșu, I. (2023). Asset pricing with systematic skewness: Two
decades later. *Critical Finance Review, 12*(1-4), 309-354.

AQR. (2020a). *Tail risk hedging: Contrasting put and trend strategies.* AQR Capital Management white
paper (also published in *Journal of Systematic Investing, 1*(1), 2021).

Asif, R., Frömmel, M., & Mende, A. (2022). The crisis alpha of managed futures: Myth or reality?
*International Review of Financial Analysis, 80,* 102045. https://doi.org/10.1016/j.irfa.2022.102045

Asvanunt, A., Nielsen, L. N., & Villalon, D. (2015). Working your tail off: Active strategies versus
direct hedging. *The Journal of Investing, 24*(2), 134-145. https://doi.org/10.3905/joi.2015.24.2.134
[COI: AQR]

Baltas, N., & Salinas, G. (2022). Cross-asset skew. *The Journal of Portfolio Management, 48*(4),
194-219. https://doi.org/10.3905/jpm.2022.1.335

Baltussen, G., Martens, M., & van der Linden, L. (2026). The best defensive strategies: Two centuries
of evidence. *Financial Analysts Journal, 82*(1), 6-34. https://doi.org/10.1080/0015198X.2025.2602270

Baltussen, G., Swinkels, L., & van Vliet, P. (2021). Global factor premiums. *Journal of Financial
Economics, 142*(3), 1128-1154. https://doi.org/10.1016/j.jfineco.2021.06.030

Bates, D. S. (2022). Empirical option pricing models. *Annual Review of Financial Economics, 14*,
369-389. https://doi.org/10.1146/annurev-financial-111720-091255

Bhansali, V., Chang, L., Holdom, J., & Rappaport, M. (2020). Monetization matters: Active tail risk
management and the great virus crisis. *The Journal of Portfolio Management, 47*(1).
https://doi.org/10.3905/jpm.2020.1.181 [COI: LongTail Alpha; peer-reviewed]

Bhansali, V., Davis, J., Dorsten, M. P., & Rennison, G. (2015). Carry and trend in lots of places.
*The Journal of Portfolio Management, 41*(4), 82-90. https://doi.org/10.3905/jpm.2015.41.4.082 [COI: PIMCO]

Bollerslev, T., Tauchen, G., & Zhou, H. (2009). Expected stock returns and variance risk premia.
*The Review of Financial Studies, 22*(11), 4463-4492.

Bollerslev, T., & Todorov, V. (2011). Tails, fears, and risk premia. *The Journal of Finance, 66*(6),
2165-2211.

Bongaerts, D., Kang, X., & van Dijk, M. (2020). Conditional volatility targeting. *Financial Analysts
Journal, 76*(4), 54-71. https://doi.org/10.1080/0015198X.2020.1790853

Brown, S. J., Gregoriou, G. N., & Pascalau, R. (2012). Diversification in funds of hedge funds: Is it
possible to overdiversify? *Review of Asset Pricing Studies, 2*(1), 89-110.
https://doi.org/10.1093/rapstu/rar003

Brunnermeier, M. K., Nagel, S., & Pedersen, L. H. (2008). Carry trades and currency crashes. *NBER
Macroeconomics Annual, 23*, 313-347.

Capital Fund Management. (2018). *The convexity of trend following* (White Paper No. 266). CFM. [COI: CFM]

Carli, T., Deguest, R., & Martellini, L. (2014). *Improved risk reporting with factor-based
diversification measures.* EDHEC-Risk Institute.

Carr, P., & Wu, L. (2009). Variance risk premiums. *The Review of Financial Studies, 22*(3),
1311-1341.

Cederburg, S., O'Doherty, M. S., Wang, F., & Yan, X. S. (2020). On the performance of
volatility-managed portfolios. *Journal of Financial Economics, 138*(1), 95-117.
https://doi.org/10.1016/j.jfineco.2020.04.015

Choueifaty, Y., & Coignard, Y. (2008). Toward maximum diversification. *The Journal of Portfolio
Management, 35*(1), 40-51. [COI: TOBAM markets a fund built on the diversification-ratio metric]

Costa, G., & Kwon, R. H. (2019). Risk parity portfolio optimization under a Markov regime-switching
framework. *Quantitative Finance, 19*(3), 453-471. https://doi.org/10.1080/14697688.2018.1486036

Dao, T.-L., Hoehener, D., Lempérière, Y., Nguyen, T.-T., Seager, P., & Bouchaud, J.-P. (2017). Trends
and risk premia: Update and additional plots. *arXiv:1708.07637.* [preprint; COI: CFM]

De Long, J. B., Shleifer, A., Summers, L. H., & Waldmann, R. J. (1990). Noise trader risk in financial
markets. *Journal of Political Economy, 98*(4), 703-738.

DeMiguel, V., Garlappi, L., & Uppal, R. (2009). Optimal versus naive diversification: How inefficient
is the 1/N portfolio strategy? *The Review of Financial Studies, 22*(5), 1915-1953.

Dew-Becker, I., & Giglio, S. (2025). *The decline of the variance risk premium: Evidence from traded
and synthetic options* (Working Paper No. 2025-17). Federal Reserve Bank of Chicago.
https://doi.org/10.21033/wp-2025-17 [Federal Reserve working paper, not peer-reviewed. Earlier version: NBER Working Paper No. 31833, https://doi.org/10.3386/w31833]

Feng, X. (2026). When simplicity beats optimization: Evidence from factor timing, volatility
management, and the 1/N benchmark. *Financial Markets and Portfolio Management.*
https://doi.org/10.1007/s11408-026-00499-8

Fleming, J., Kirby, C., & Ostdiek, B. (2001). The economic value of volatility timing. *The Journal of
Finance, 56*(1), 329-352.

Fung, W., & Hsieh, D. A. (2001). The risk in hedge fund strategies: Theory and evidence from trend
followers. *The Review of Financial Studies, 14*(2), 313-341.

Gârleanu, N., Pedersen, L. H., & Poteshman, A. M. (2009). Demand-based option pricing. *The Review of
Financial Studies, 22*(10), 4259-4299. https://doi.org/10.1093/rfs/hhp005

Grinold, R. C. (1989). The fundamental law of active management. *The Journal of Portfolio
Management, 15*(3), 30-37.

Gromb, D., & Vayanos, D. (2010). Limits of arbitrage. *Annual Review of Financial Economics, 2*,
251-275.

Harvey, C. R., & Siddique, A. (2000). Conditional skewness in asset pricing tests. *The Journal of
Finance, 55*(3), 1263-1295.

Harvey, C. R., & Siddique, A. (2023). Conditional skewness in asset pricing: 25 years of
out-of-sample evidence. *Critical Finance Review, 12*(1-4), 355-366.
https://doi.org/10.1561/104.00000134

Hurst, B., Ooi, Y. H., & Pedersen, L. H. (2017). A century of evidence on trend-following investing.
*The Journal of Portfolio Management, 44*(1), 15-29. [COI: AQR]

Ilmanen, A. (2012). Do financial markets reward buying or selling insurance and lottery tickets?
*Financial Analysts Journal, 68*(5), 26-36. [COI: AQR]

Israelov, R. (2019). Pathetic protection: The elusive benefits of protective puts. *The Journal of
Alternative Investments, 21*(3), 6-33. https://doi.org/10.3905/jai.2018.1.066 [COI: AQR]

Israelov, R., & Nielsen, L. N. (2015). Still not cheap: Portfolio protection in calm markets. *The
Journal of Portfolio Management, 41*(4), 108-120. https://doi.org/10.3905/jpm.2015.41.4.108 [COI: AQR]

Kang, J., Rouwenhorst, K. G., & Tang, K. (2020). A tale of two premiums: The role of hedgers and
speculators in commodity futures markets. *The Journal of Finance, 75*(1), 377-417.

Koijen, R. S. J., Moskowitz, T. J., Pedersen, L. H., & Vrugt, E. B. (2018). Carry. *Journal of
Financial Economics, 127*(2), 197-225. [COI: AQR]

Lassance, N., & Vrins, F. (2023). Portfolio selection: A target-distribution approach. *European
Journal of Operational Research, 310*(1), 302-314. https://doi.org/10.1016/j.ejor.2023.02.014

Le, T. H., Kourtis, A., & Markellos, R. N. (2023). Modeling skewness in portfolio choice. *Journal of
Futures Markets, 43*(6), 734-770. https://doi.org/10.1002/fut.22408

Lempérière, Y., Deremble, C., Nguyen, T.-T., Seager, P., Potters, M., & Bouchaud, J.-P. (2017). Risk
premia: Asymmetric tail risks and excess returns. *Quantitative Finance, 17*(1), 1-14. [COI: CFM]

Lettau, M., Maggiori, M., & Weber, M. (2014). Conditional risk premia in currency markets and other
asset classes. *Journal of Financial Economics, 114*(2), 197-225.

Lopez de Prado, M. (2016). Building diversified portfolios that outperform out of sample. *The Journal
of Portfolio Management, 42*(4), 59-69.

Maillard, S., Roncalli, T., & Teiletche, J. (2010). The properties of equally weighted risk
contribution portfolios. *The Journal of Portfolio Management, 36*(4), 60-70.

Man Group. (2022). *Creating portfolio convexity: Trend versus options.* Man Group / Man Institute.
[COI: practitioner, Man sells trend/overlay products]

Martellini, L., & Ziemann, V. (2010). Improved estimates of higher-order comoments and implications
for portfolio selection. *The Review of Financial Studies, 23*(4), 1467-1502.

McLean, R. D., & Pontiff, J. (2016). Does academic research destroy stock return predictability? *The
Journal of Finance, 71*(1), 5-32.

Meucci, A. (2009). Managing diversification. *Risk, 22*(5), 74-79.

Moskowitz, T. J., Ooi, Y. H., & Pedersen, L. H. (2012). Time series momentum. *Journal of Financial
Economics, 104*(2), 228-250. [COI: AQR]

Noguer i Alonso, M., & Al-Fallouji, A. (2026). *Tail risk management with puts and trend following: A
CVaR framework for crashes and drawdowns.* arXiv:2607.00883. [preprint]

Olszewski, F., & Zhou, G. (2013). Strategy diversification: Combining momentum and carry strategies
within a foreign exchange portfolio. *Journal of Derivatives & Hedge Funds, 19*(4), 311-320.
https://doi.org/10.1057/jdhf.2013.16 [publisher byline spells "Olszweski"]

One River. (2024). *The convexity (re)balancing act.* One River Asset Management (P. Kazley & S. Wang).
[COI: practitioner, One River sells convex-overlay strategies]

Pyun, S. (2019). Variance risk in aggregate stock returns and time-varying return predictability.
*Journal of Financial Economics, 132*(1), 150-174.

Schwalbach, B., & Auret, C. (2025). Enhancing global equity returns with trend-following and tail risk
hedging overlays. *Investment Analysts Journal, 54*(3), 364-386.
https://doi.org/10.1080/10293523.2025.2553254

Shleifer, A., & Vishny, R. W. (1997). The limits of arbitrage. *The Journal of Finance, 52*(1),
35-55.

Tomunen, T. (2026). Failure to share natural disaster risk. *The Review of Financial Studies, 39*(3),
661-701. https://doi.org/10.1093/rfs/hhaf055

Trucíos, C. (2026). Hierarchical risk clustering versus traditional risk-based portfolios: An
empirical out-of-sample comparison. *Empirical Economics, 70*(3), Article 58.
https://doi.org/10.1007/s00181-026-02900-x

Uysal, A. S., & Mulvey, J. M. (2021). A machine learning approach in regime-switching risk parity
portfolios. *The Journal of Financial Data Science, 3*(2), 87-108.
https://doi.org/10.3905/jfds.2021.1.057

