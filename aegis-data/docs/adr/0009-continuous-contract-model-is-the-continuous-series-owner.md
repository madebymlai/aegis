# ContinuousContractModel owns the continuous series lifecycle

Status: accepted

## Context

The catalog request path already owns the back-adjusted continuous series, but
live rebuilt the same lifecycle in `aegis-trader`: it materialised the frame,
found the current front leg, appended offset-0 bars, detected rolls, and carried
the last re-basing through a trader-owned continuous feed.

That split made live/research parity depend on two implementations staying in
lock-step. Worse, a single materialisation could derive the front leg twice:
once from the liquidity-timed roll schedule that builds the series, and once
from the causal Liquid Cycle picker used by live execution routing.

## Decision

The continuous series is one stateful deep object in `aegis-data`:
`ContinuousContractModel`.

The model is constructed from the catalog read port, a bare continuous root, the
history start, and the bar timeframe. It hides the contract calendar, volume
probe, roll table, materialisation engine, offset-0 append projection, and
re-basing details behind one small interface:

- `materialize(end)` rebuilds the back-adjusted frame over `[start, end]`.
- `frame` exposes the adjusted OHLCV frame keyed by the synthetic continuous
  root.
- `front_leg` exposes the current execution leg.
- `front_leg_as_of(as_of)` answers the same front rule used by materialisation.
- `on_bar(bar)` appends a closed front-leg bar at offset 0, or re-materialises
  across a roll.
- `last_rebasing` exposes the re-basing recorded at the most recent roll.
- `continuous_id` exposes the synthetic root id, for example `ES.XCME`.

The model holds `ContinuousFuture` as an internal pure value object. The roll
transition table remains pure and does not grow I/O or frame ownership.

The model derives the front leg from the liquidity-timed roll schedule. The
causal Liquid Cycle front-picker is retained only as a proof fixture until the
live path no longer needs it. A dedicated agreement test proves the causal
front and the schedule-derived front name the same leg at representative
as-ofs, including early liquidity migration.

Live must not resolve continuous identity. The live Roll Desk verifies the
model's `continuous_id` against the declaration at the existing continuous
venue parity gate, then drives the model. Research constructs the same model and
reads its frame.

## Consequences

- Live/research parity becomes one implementation with two adapters, not two
  implementations that happen to agree.
- The continuous front leg has one authority: the liquidity-timed roll schedule
  that also builds the adjusted frame.
- `continuous_catalog` can shrink to the cheap continuous-root identity
  resolver after research and live both construct the model directly.
- `aegis-trader` stops importing catalog internals for continuous-series
  lifecycle work; those decisions stay in `aegis-data`.

## Relationship to earlier decisions

- Extends ADR-0001 by using the Liquid Cycle as the roll-timing input to a
  single continuous-series owner.
- Extends ADR-0003's deep-module direction: lifecycle state moves behind one
  object rather than a bag of free composers.
- Consistent with root ADR-0007: the declared Nautilus `InstrumentId` is the
  identity, and live validates it rather than deriving a competing one.
