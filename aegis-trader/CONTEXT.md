# Portfolio Execution

Portfolio Execution combines locked strategy sleeves into one risk-budgeted book and converts portfolio intent into orders.

## Language

### Portfolio Structure

**Commingled Book**:
The single portfolio whose positions and cash reflect the combined targets of every Sleeve.
_Avoid_: fund of funds, subaccount collection, strategy portfolio

**Book Config**:
The declaration of a Commingled Book, including its Sleeves, risk budgets, base currency, exposure limits, and portfolio controls.
_Avoid_: manifest, roster file, broker config

**Sleeve**:
A named strategy allocation within the Commingled Book backed by one Execution Bundle.
_Avoid_: fund, account, strategy process

**Risk Group**:
The Sleeve's role in the portfolio risk budget: Floor, Target, or Expansion.
_Avoid_: asset class, sector, strategy type

**Risk Share**:
The share of the Book's volatility budget assigned to a Sleeve.
_Avoid_: capital weight, target weight, cash allocation

**Book Volatility Target**:
The annualized risk level used to scale the combined Sleeve allocation.
_Avoid_: return target, leverage target, risk limit

**Tail Convexity Budget**:
A slow-reviewed Target-group budget that assigns risk according to stress coverage, carry, and capacity.
_Avoid_: crash signal, tail timing rule, option premium pool

### Allocation and State

**Allocator**:
The domain service that converts Risk Shares and observed Sleeve behavior into scaled Sleeve targets.
_Avoid_: optimizer, strategy, rebalancer

**Allocation**:
The scaled Sleeve targets and multipliers produced by the Allocator for one portfolio decision.
_Avoid_: order plan, book config, risk shares

**Book Observation**:
A timestamped view of Book value, realized weights, Sleeve targets, and market marks.
_Avoid_: snapshot file, account poll, performance row

**Sleeve Ledger**:
The chronological record of Book Observations used for Sleeve risk estimates, attribution, drawdown, and portfolio analytics.
_Avoid_: trade log, candidate store, account statement

**Net Asset Value**:
The current total equity of the Commingled Book and the reference value for portfolio weights.
_Avoid_: cash balance, buying power, gross assets

**Attribution**:
The decomposition of Book profit and loss across Sleeves over a defined period.
_Avoid_: ranking, metric table, account report

### Portfolio Decisions

**Rebalance**:
A portfolio decision that moves realized Book weights toward the latest allocated targets under the Book's controls.
_Avoid_: strategy run, rescale, synchronization

**Drift**:
The distance between realized Book weights and their allocated targets.
_Avoid_: tracking error, slippage, volatility

**Rebalance Plan**:
The approved weight changes and applied Sleeve multipliers for one Rebalance.
_Avoid_: order batch, target book, execution report

**Order Intent**:
A requested buy or sell change for one Instrument derived from a Rebalance Plan.
_Avoid_: fill, position, target weight

**Drawdown Delever Curve**:
The schedule that reduces Book exposure as drawdown deepens.
_Avoid_: stop loss, kill switch, volatility target

**Financing Cost**:
The carrying cost of borrowed cash or borrowed Instruments attributable to the Book.
_Avoid_: transaction cost, management fee, slippage

**Distribution**:
Cash paid by an Instrument to the Book, including dividends and comparable income events.
_Avoid_: price return, realized gain, financing rebate
