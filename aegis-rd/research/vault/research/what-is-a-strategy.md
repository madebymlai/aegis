---
title: What Is a Strategy
date: 2026-07-17
topic: strategy-definition
distilled-into:
aliases:
  - strategy
  - trading strategy
  - strategy vs holding
tags:
  - article
---

# What Is a Strategy

> [!abstract] One-line takeaway
> A strategy is a falsifiable claim on a payer, written down completely: a **state** that says when to act, an **action**, an **exit**, a named **payer**, and a **failure** state that would kill it. A holding is an asset exposure; it answers none of those questions and earns only whatever premium the asset pays for being held through bad times. The line between them is specification, not trading frequency - the same instrument, held constantly, can be either.

The roster keeps needing this word. Sleeves are admitted, paired, and killed on the claim that each one "is a strategy" ([[the-tiered-strategy-roster]]), yet the word is loose enough that "hold investment trusts" and "trade approved liquidations with a pre-registered failure state" can both wear it. The distinction was first forced in [[public-filings-special-situations-as-atalantas-pair]], where the investable claim survived only after everything holding-shaped was cut away. This article generalizes that answer so other notes can point at it.

## The formal definition is too permissive to be the test

Mathematical finance has owned the term "trading strategy" since Harrison and Kreps: a predictable stochastic process of portfolio holdings, usually required to be self-financing - value changes only through the assets held, no money in or out.[^kenyon] Lecture-note treatments state it plainly: the definition "is just a formalization of what one typically imagines under a rule-based strategy for allocating money into financial markets", a process chosen without using future information.[^mff] Under this definition buy-and-hold is not merely admitted; it is the elementary building block - the "simple" strategies from which the theory constructs all others are literally buy-and-hold portfolios over finitely many dates.[^biagini]

That definition is exactly right for its job, which is pricing and no-arbitrage, and exactly wrong as a research admission test, because it grades bookkeeping rather than knowledge. Every portfolio anyone has ever held passes it. When a roster debate calls a static exposure "a strategy", the formal usage supplies the cover. The rest of this article is about what more has to be true before the word earns a roster seat.

## A rule a machine could run

The first requirement is completeness of specification. Carver's test is the sharpest: anyone who claims to trade systematically but could not, in principle, write a computer program that would replace them is doing something else.[^carverttu] His framework splits the work into trading rules that produce forecasts and a position-management layer that turns forecasts into positions, stops, and trades - and both halves are part of the strategy, because a forecast without sizing, exits, and risk handling is not yet a decision procedure.[^carvercxo] Practitioner decompositions of the same idea enumerate the parts: the market state that makes a trade eligible, the trigger, the execution, the invalidation level, the profit-taking rule, and the size - "a trading strategy isn't just an entry setup".[^anatomy] A specification with a hole in it is not a strategy with a detail missing; it is a discretionary process wearing a costume, because the hole is where judgment will be exercised after seeing the data.

Completeness is what makes the other properties possible at all. An under-specified rule cannot be backtested honestly, cannot be handed to another operator, and cannot fail cleanly - there is always a degree of freedom left to explain the loss away.

## A named payer

Specification says how the rule acts; it says nothing about why acting should pay. Sharpe's arithmetic sets the constraint: before costs, the average actively managed dollar earns exactly the average passively managed dollar, so active gains net to zero among active participants - one active investor's win is another's loss.[^sharpe] Pedersen's refinement weakens the equality (indexes reconstitute, shares are issued and repurchased, so even "passive" investors must trade) but the correction itself names a payer: mandated, price-insensitive flows that someone else gets paid to accommodate.[^pedersen] Either way, a return above the exposure itself needs a counterparty story. The practitioner form of the question: every dollar of trading profit comes from someone - who is paying you, why are they willing to keep paying, and why do you, of all participants, get to take the other side?[^longmore]

The payer clause is what separates the two economic species that the word "strategy" conflates:

- **Compensation for risk.** The asset pays a premium because it loses exactly when losses hurt most; the central result of modern asset pricing is that required returns follow bad-times performance, not volatility.[^ilmanencaia] Nobody on the other side is making a mistake - the premium is an insurance receipt, and its price is the bad times. This return is available to a holding, with no rule at all.[^ilmanen]
- **Someone else's systematic behavior.** A mandated rebalancer selling whatever ran up, a leveraged trader paying funding for leverage they value more than the cost, an institution prorated in a tender while odd lots exit in full. Ilmanen's summary: in a world that permits some irrationality, you can also be paid for someone else's systematic mistakes.[^ilmanen] This return requires acting at the right state, so only a rule can collect it.

A holding can only ever collect the first kind. That is not a defect - most long-run wealth is exactly this - but then the honest name is *exposure*, the honest benchmark is the asset itself, and the honest risk statement is "I eat the bad times". Carver, from the practitioner side, says the same about his own rules: they capitalize on well-known risk factors, and "you don't get return without risk".[^carverblog] A sleeve whose payer clause reads only "the risk premium" should be priced as a holding, whatever its label says ([[what-makes-a-convergent-sleeve-an-income-engine]] applies this to the income pole).

## A hypothesis that is probably false

The base rates make falsifiability a load-bearing part of the definition rather than scientific hygiene. López de Prado states it without hedging: "Most investment strategies uncovered by practitioners and academics are false."[^falsestrat] Harvey, Liu and Zhu reach the same verdict for the academic cross-section of expected returns - under any reasonable multiple-testing correction, most claimed findings are likely false.[^harvey] Bailey, Borwein, López de Prado and Zhu prove the mechanism: high backtested performance is easily achieved by searching a modest number of configurations, so a backtest reported without its trial count is close to worthless.[^pseudomath]

A candidate strategy is therefore a hypothesis whose prior is against it. The definitional consequence: the failure state - the observation that would kill the idea - must be written into the strategy before the data is seen, the same way run diaries pre-register keep/kill criteria before results exist. A rule with no stated failure condition is not a strategy; it is a belief with an order-entry workflow. And this is the second place the holding fails: a holding cannot fail, it can only lose. There is no observation that makes its owner say "the thesis is dead", which means there is nothing to test.

## The five-part test

Putting the three requirements together yields the test the vault already uses in embryo. A strategy is a written rule that answers five questions:

1. **State** - what observable condition makes action eligible now, rather than always?
2. **Action** - what exactly is done, at what size?
3. **Exit** - how does the position end, on both the good path and the bad one?
4. **Payer** - who is on the other side, and why do they keep paying?
5. **Failure** - what observation kills the rule, declared before the data is seen?

A holding fails at least four of the five: it has no state (it is always on), no exit, no payer beyond the generic premium for bearing the asset's bad times, and no failure condition.

The subtle case proves the line is specification, not activity. Carver runs a constant-forecast rule he calls the "no rule" rule - permanently short volatility futures, inside vol-scaled sizing, justified by a named payer (investors overpay for crash insurance, so implied volatility sits above realized on average).[^carverblog] The exposure is constant, yet it passes the test: the payer is named, the sizing and risk handling are specified, and the premium's existence is a falsifiable claim. The same instrument bought and forgotten would be a holding. Nothing about the asset changed; the five written answers are the difference. This is also why cash between eligible events is not a strategy: it is unallocated capacity, exactly as the special-situations note concluded.[^seed]

## Limitations

The payer clause is the honest weak point of the test. For value and momentum, forty years of literature has not settled whether the premium is compensation for risk, a behavioral mispricing, or a mixture, and Ilmanen and Kizer note the premia may persist either way.[^ilmanenkizer] The test therefore requires naming the best-supported payer and the evidence that would distinguish it, not certainty - a sleeve with a contested payer is admissible; a sleeve with no payer story is not.

The definition defended here is an engineering admission standard, not the field's usage. Mathematical finance will keep calling buy-and-hold a trading strategy, and it is right to within its own purposes. The claim is narrower: a roster seat, a run diary, and a capital allocation should be reserved for things that pass the five-part test, because everything the research process does - backtesting, pre-registration, kill decisions, pairing by mechanism - assumes the five answers exist.

Single-source flags: the "no rule" construction is one practitioner's example, and the strategy-anatomy decomposition rests on practitioner blogs rather than peer-reviewed work (its substance is corroborated by Carver's framework).

## Strategy hypotheses this could seed

- [ ] Holdings-in-costume audit: residualize each live sleeve's returns against a static buy-and-hold of its own traded instruments; a sleeve whose residual after costs is indistinguishable from zero is collecting only the exposure premium - reprice its roster seat as a holding.
- [ ] Payer-clause survival test: pre-register the payer for every new run-diary candidate, then measure whether candidates with no named payer die into [[graveyard]] at a higher rate than payer-named ones.
- [ ] Specification-value probe: run a constant-forecast exposure (short-vol or carry) bare versus inside the full sizing/exit framework on identical dates, to measure how much of a sleeve's value is specification rather than signal.

## Sources

[^kenyon]: Kenyon, C. and Green, A., "Self-Financing Trading and the Ito-Doeblin Lemma", arXiv:1501.02750, 2015. Recounts the Harrison-Kreps (1979) / Harrison-Pliska (1981) origin of the self-financing trading strategy. https://arxiv.org/pdf/1501.02750

[^mff]: Stefanik, M., "Mathematical Foundations for Finance", exercise slides, ETH Zurich, 2020; and Acciaio, B., lecture notes, Chapter I, ETH Zurich, 2021. Formal definition: an adapted/predictable holdings process. https://metaphor.ethz.ch/x/2020/hs/401-3913-01L/ex/mff20-es2-slides.pdf

[^biagini]: Biagini, S. and Cerny, A., "Admissible Strategies in Semimartingale Portfolio Selection", SIAM Journal on Control and Optimization, 2011. Simple strategies are "buy-and-hold strategies over finitely many dates". https://arxiv.org/abs/0910.3936

[^carverttu]: Carver, R., interview, "Making a Simple System and Sticking To It", Top Traders Unplugged, 2015. "Anyone who says they are trading systematically but then couldn't in theory write a computer program that would essentially replace them isn't really trading systematically." https://www.toptradersunplugged.com/podcast/making-a-simple-system-and-sticking-to-it-robert-carver-author-trader/

[^carvercxo]: Carver, R., "Systematic Trading", Harriman House, 2015, quoted in CXO Advisory, "A Few Notes on Systematic Trading". "Trading rules are the engine of the system... a position risk management framework wrapped around your trading rules... translates forecasts into the actual positions." https://www.cxoadvisory.com/big-ideas/a-few-notes-on-systematic-trading/

[^anatomy]: Villahermosa, R., "Anatomy of a Trading Strategy: The 6 Essential Components", 2026. Setup, trigger, entry, stop, target, sizing; practitioner blog. https://algostrategyanalyzer.com/en/blog/trading-strategy-anatomy/

[^sharpe]: Sharpe, W., "The Arithmetic of Active Management", Financial Analysts Journal 47(1), 1991. Before costs, the average active dollar equals the average passive dollar.

[^pedersen]: Pedersen, L.H., "Sharpening the Arithmetic of Active Management", Financial Analysts Journal 74(1), 2018. The market portfolio changes, so even passive investors must trade. https://www.tandfonline.com/doi/full/10.2469/faj.v74.n1.4

[^longmore]: Longmore, K., "For The Love of The Game", Edge Alchemy (Robot Wealth), 2026. "Who's paying you, and why are they willing to keep doing it?" - with the mandated-rebalancer and perp-funding examples. https://edgealchemy.robotwealth.com/p/for-the-love-of-the-game

[^ilmanencaia]: Ilmanen, A., "Understanding Expected Returns", CFA Institute Conference Proceedings Quarterly, 2012. "Investments should earn a positive risk premium if they perform poorly in bad times." https://www.caia.org/sites/default/files/membersonly/Understanding_Expected_Returns.pdf

[^ilmanen]: Ilmanen, A., "Expected Returns: An Investor's Guide to Harvesting Market Rewards", Wiley, 2011. Two sources of expected return: bearing risk others do not want (beta), and someone else's systematic mistakes (alpha). https://onlinelibrary.wiley.com/doi/book/10.1002/9781118467190

[^carverblog]: Carver, R., "Some more trading rules", Investment Idiocy, 2017. "You don't get return without risk"; the constant-forecast "no rule" short-volatility rule with a named premium. https://qoppac.blogspot.com/2017/06/some-more-trading-rules.html

[^falsestrat]: Lopez de Prado, M., "Detection of False Investment Strategies Using Unsupervised Learning Methods", SSRN 3167017, 2018. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3167017

[^harvey]: Harvey, C., Liu, Y. and Zhu, H., "...and the Cross-Section of Expected Returns", Review of Financial Studies 29(1), 2016. Most claimed research findings in financial economics are likely false under multiple-testing corrections.

[^pseudomath]: Bailey, D., Borwein, J., Lopez de Prado, M. and Zhu, Q.J., "Pseudo-Mathematics and Financial Charlatanism: The Effects of Backtest Overfitting on Out-of-Sample Performance", Notices of the AMS 61(5), 2014. https://www.davidhbailey.com/dhbpapers/backtest-pseudo.pdf

[^ilmanenkizer]: Ilmanen, A. and Kizer, J., "The Death of Diversification Has Been Greatly Exaggerated", Journal of Portfolio Management, 2012. Premia may persist whether risk-based or behavioral; limits to arbitrage protect them. https://r.jordan.im/download/investing/ilmanen2012.pdf

[^seed]: [[public-filings-special-situations-as-atalantas-pair]] - the roster decision this definition was first cut for: "the correct unit is an event, not an asset; cash between events is unallocated capacity, not a fourth strategy."
