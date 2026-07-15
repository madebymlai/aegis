# Nautilus-native equity quantity design

**Date:** 2026-07-15  
**Question:** Should Aegis define whole/fractional-share increments, or should the broker adapter provide them through Nautilus?

## Verdict

The native Nautilus seam is:

`venue metadata -> adapter InstrumentProvider/parser -> Nautilus Instrument -> cache/catalog -> strategy and execution clients`

That makes the adapter the correct place to translate venue-specific metadata, while the resulting Nautilus `Instrument` is the application-visible domain object. Aegis should not expose or interrogate the IB adapter directly.

The proposed design is only partly native today. Nautilus's generic instrument model already owns `size_precision`, `size_increment`, `min_quantity`, and `lot_size`, but Nautilus 1.229.0 deliberately constructs every `Equity` with `size_precision=0` and `size_increment=1`. Its Interactive Brokers equity parser consequently does not map IBKR's `minSize` or `sizeIncrement` for stocks, even though other IB instrument parsers map those fields.

Therefore, fractional equities should be implemented by deepening Nautilus's existing instrument/provider seam—ideally upstream—rather than by introducing a parallel Aegis quantity-rule authority. An Aegis execution bundle may snapshot the resolved native fields for reproducibility, but the snapshot is evidence, not a second source of truth.

## Source findings

1. Nautilus instruments have native quantity metadata. The base instrument interface exposes size precision, size increment, minimum quantity, and lot size, and instruments are expected to enforce their declared precision. [Nautilus instrument concepts](https://nautilustrader.io/docs/latest/concepts/instruments/)

2. Nautilus equities are explicitly whole-unit instruments. The equity documentation states that quantity precision is always zero and orders therefore use whole units; the implementation supplies a size increment of one. [Nautilus Equity documentation](https://github.com/nautechsystems/nautilus_trader/blob/develop/docs/concepts/instruments/equity.md) and [Equity implementation](https://github.com/nautechsystems/nautilus_trader/blob/develop/nautilus_trader/model/instruments/equity.pyx)

3. The Interactive Brokers adapter already follows the provider/parser pattern. Its equity parser builds a Nautilus `Equity`, but does not pass IBKR `minSize` or `sizeIncrement`; parsers for several other instrument classes do derive native Nautilus quantity fields from those contract details. [Nautilus IB instrument parser](https://github.com/nautechsystems/nautilus_trader/blob/develop/nautilus_trader/adapters/interactive_brokers/parsing/instruments.py)

4. IBKR exposes `MinSize`, `SizeIncrement`, and `SuggestedSizeIncrement` as contract details. These describe an order-size grid, but do not alone prove that a given account, route, API version, and order type may trade fractions. [IBKR ContractDetails reference](https://interactivebrokers.github.io/tws-api/classIBApi_1_1ContractDetails.html)

5. IBKR describes fractional-share trading as requiring an account permission and limits it to eligible securities. Therefore `fractional_capable: bool` on a shared instrument would collapse product definition and account/session eligibility into one misleading fact. [IBKR fractional shares lesson](https://ibkrcampus.com/campus/trading-lessons/fractional-shares/)

## Recommended boundary

- The hidden venue adapter translates broker metadata into a native Nautilus instrument.
- The Nautilus instrument remains the authority for the instrument's quantity grid: precision, increment, and minimum.
- If fractional stock submission is supported, extend `Equity` and the IB equity parser to carry that native grid; prefer an upstream Nautilus contribution or a narrowly maintained patch.
- Keep account/session eligibility separate from instrument definition. Expose it, only when a concrete caller needs it, as a broker-neutral execution capability behind the existing trading port—not as an adapter object and not as a field in a shared security master.
- Let Aegis research/trading artifacts record the resolved native quantity fields for reproducibility. Do not create independent rounding logic or another mutable rule source.
- Keep quantity rules out of numerical research arrays; they are instrument/execution metadata.

## Consequence for the current Aegis spec

The current whole-share cleanup and hidden-adapter direction are sound. The spec should be revised before ticketing so it does not make a custom `OrderQuantityRule` the authority, does not infer account eligibility solely from contract size increments, and does not describe fractional `Equity` as already supported by Nautilus. The missing work is primarily a Nautilus model/IB-provider extension plus an explicit decision about how Aegis snapshots native execution metadata.
