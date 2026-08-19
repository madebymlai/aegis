# Strategy Runtime

Strategy Runtime applies a locked strategy contract to market data and produces exposure-validated target weights.

## Language

### Locked Strategy Contract

**Execution Bundle**:
A portable strategy contract containing one locked Strategy, its parameters, its Data Contract, and its Exposure Limits.
_Avoid_: research run, strategy source, configuration archive

**Locked Execution Plan**:
The fixed Component composition and parameters selected by the Lock behind an Execution Bundle.
_Avoid_: optimizer state, candidate search, dynamic plan

**Data Contract**:
The instruments, Market Arrays, currencies, cadence, lookback, and continuous-futures facts required by an Execution Bundle.
_Avoid_: data config, provider request, schema payload

**Market Data Bundle**:
A coherent set of aligned Market Arrays that satisfies a Data Contract for a requested window.
_Avoid_: price dictionary, feature frame, data response

### Portfolio Intent

**Target Weight**:
The signed fraction of capital a Strategy assigns to one Instrument.
_Avoid_: order size, position quantity, signal

**Target Book**:
The complete set of Target Weights produced by one Execution Bundle at a decision time.
_Avoid_: portfolio, order list, allocation frame

**Direction**:
The admissible sign of Target Weights, expressed as long-only, short-only, or both.
_Avoid_: bias, side, stance

**Gross Exposure**:
The sum of absolute Target Weights in a Target Book.
_Avoid_: leverage cap, invested capital, notional

**Net Exposure**:
The signed sum of Target Weights in a Target Book.
_Avoid_: beta, market tilt, directional risk

**Exposure Limits**:
The Direction, Gross Exposure cap, and Net Exposure cap that bound a Target Book.
_Avoid_: mandate, allocator policy, broker limits

**Drift Band**:
The tolerated distance between a realized weight and its Target Weight, together with the destination reached after the band is crossed.
_Avoid_: threshold, rebalance frequency, buffer

**Currency Conversion**:
The coherent expression of market values and Target Weights in the Book's base currency.
_Avoid_: FX hedge, exchange trade, currency overlay
