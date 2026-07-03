# aegis-runtime

Shared runtime that executes one locked **Candidate** from an **Execution
Bundle** against supplied market data. It owns the minimal execution contract
shared by Aegis RD and the bundle wheel.

## Language

**InstrumentId**:
The native Nautilus `InstrumentId` value object. `DataContract.instrument_ids`
uses `InstrumentId` in memory; bundle JSON serializes each value as its stable
string form. Market-data panels and computed weights are keyed by these values.
_Avoid_: InstrumentRef, ListedRef, FuturesRef, FIGI, ticker, symbol

**Execution Bundle**:
A wheel produced by `aerd export` for one locked Candidate. It carries the
strategy, indicators, locked params, component source hashes, and a
`DataContract` keyed by native `InstrumentId`s. It does not contain RD optimizer
state or candidate-store access.
_Avoid_: research run, optimizer artifact, source config

**MarketDataBundle**:
The eager value object a **Component** reads prices from: a mapping of
materialised **Array** panels with one guarded accessor, `bundle.array(name)`,
that fails loud on a dict miss. Dict membership is the sole guard: an Array is
loaded iff it is a key.
_Avoid_: feature bundle, price dict, MarketDataResult

**Exposure Validation**:
The single fail-closed gate that rejects a signed target-weight frame breaching
its **Exposure Limits**. Both sides of the Execution Bundle seam gate here:
research before simulation (each **Candidate**'s columns gated independently),
the bundle before computed weights leave it.
_Avoid_: broker risk check, portfolio simulation, sizing

**Exposure Limits**:
The validated caps a signed target-weight book must satisfy: the gross cap
(`Σ|wᵢ|`), the net cap (`|Σwᵢ|`, defaulting to the gross cap when unset), and
the admissible direction sign. A constructed value is proof the triple is
legal.
_Avoid_: allocation policy, risk limits, mandate, caps triple
