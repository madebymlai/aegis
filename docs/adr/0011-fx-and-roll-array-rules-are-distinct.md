# FX denomination and roll re-basing are distinct Array rules

Status: accepted (aegis-rd-3ua.5).

## Context

Currency conversion and the continuous-future roll probe both happened to use the
same OHLC allowlist. That agreement is accidental. Conversion asks whether an Array's
values are denominated in an instrument's quote currency. The roll probe asks whether
a roll re-bases a continuous root's values. Keeping one list for both questions would
turn a naming coincidence into shared policy and would add false positives to a
fail-closed safety gate.

A quote-currency-denominated adjacent Array is the concrete divergence case: it must
be converted before Components run, but a roll must never perturb it merely because
it is denominated like a price. Conversely, today's unclassified Custom Data kinds
are provider-fetched records, so the roll probe skips them. That assumption breaks as
soon as a Custom Array is derived from a re-based price.

## Decision

- Currency conversion owns a named quote-currency-denomination rule and a separate
  dimensionless rule. It accepts and returns the canonical `MarketDataBundle`.
- The roll probe owns a separately named rule for Arrays whose continuous-root
  columns a roll re-bases. The two rules cross-reference this record and are never
  merged.
- An unclassified Array containing a leg with a live conversion raises
  `UnclassifiedCurrencyArrayError`. If none of its columns needs conversion, it
  passes unchanged. The roll probe gives the opposite answer for an unclassified
  provider-fetched Array: skip it rather than perturb it.
- Array denomination is a timeless code fact and is not serialized on the Execution
  Bundle wire or copied into Run provenance. Persisting it would allow a stale Bundle
  to override the runtime's current truth about what an Array means.
- When the first currency-denominated adjacent Array is introduced, its defusal is a
  runtime code change: add it to the quote-currency rule with public conversion
  coverage. If a price-derived Custom Array is introduced, classify it independently
  in the roll rule according to its roll algebra.

## Consequences

Unknown Arrays cannot silently escape a conversion that would affect one of their
columns. Existing panels with no convertible columns remain byte-identical. Adding an
Array now requires answering two explicit domain questions instead of inheriting a
single misleading "price Array" classification.

## Alternatives considered

- One shared OHLC/price allowlist: rejected because denomination and roll behavior
  diverge and a shared list creates false roll-sensitivity failures.
- Serialize denomination in the Bundle or Run identity: rejected because stale
  deployment provenance must not override a timeless fact owned by current code.
- Continue skipping unknown Arrays during FX conversion: rejected because a live FX
  leg would then remain silently denominated in the wrong currency.
