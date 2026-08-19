# Market Data

Market Data provides durable, identified market observations for research and portfolio execution.

## Language

### Identity and Observations

**Instrument**:
A tradable or reference market object with an economic identity and venue-specific definition.
_Avoid_: ticker, asset string, security row

**Instrument ID**:
The stable cross-context identity of an Instrument, including the venue needed to distinguish its market definition.
_Avoid_: ticker, symbol, FIGI, provider code

**Instrument Definition**:
The terms required to interpret and trade an Instrument, including its currency, venue, contract size, and lifecycle facts.
_Avoid_: instrument table, broker contract, symbol metadata

**Market Stream**:
One kind of market observation for an Instrument at a declared cadence.
_Avoid_: feed, subscription, timeframe string

**Bar**:
An open, high, low, close, and volume observation for one Market Stream interval.
_Avoid_: candle, row, OHLCV tuple

**Data Window**:
A bounded time interval requested for one or more Market Streams.
_Avoid_: slice, date filter, query range

### History and Coverage

**Catalog**:
The durable collection of identified market observations and Instrument Definitions available to Aegis.
_Avoid_: cache, corpus, archive

**Coverage**:
The portion of a Data Window represented in the Catalog for a specific Market Stream.
_Avoid_: completeness flag, availability marker, coverage ledger

**Data Provider**:
An external source capable of supplying Instrument Definitions or market observations for missing Catalog coverage.
_Avoid_: broker dependency, vendor core, fetch script

### Continuous Futures

**Continuous Future**:
A historical market series that represents successive Dated Contracts for one futures root on a consistent price basis.
_Avoid_: perpetual contract, generic ticker, futures ETF

**Dated Contract**:
A futures Instrument with a specific expiry and delivery cycle.
_Avoid_: leg, month code, front

**Front Contract**:
The Dated Contract currently representing a Continuous Future under its agreed roll sequence.
_Avoid_: nearest expiry, active ticker, generic future

**Roll**:
The transition of a Continuous Future from one Front Contract to the next.
_Avoid_: rollover job, expiry switch, contract replacement

**Roll Agreement**:
The agreed sequence of Dated Contracts and roll dates for one futures root across research and portfolio execution.
_Avoid_: roll calendar file, chain cache, front picker

**Rebasing**:
The price transformation that carries a Continuous Future across a Roll on one consistent historical basis.
_Avoid_: price patch, splice, adjusted close
