# VectorBT PRO Rust simulator update

**Question.** Should Aegis move its VectorBT PRO pin from
`7801c7849838fdc2ee1b6b441dd93660d6c24f71` to latest `develop`
(`4a2000985a25219698c5ad8a1aa8d324d2074002` on 2026-07-21), and can the new
Rust simulator accelerate the planned continuous Future-in-Past replay?

## Conclusion

The update was accepted after isolated comparison and full regression testing.
Do **not** redesign the replay around the new Rust dynamic simulator yet. It
cannot be selected by Python `Portfolio.from_optimizer`,
`Portfolio.from_signals`, `jitted="rs"`, or AutoBench. Using it would require
moving Aegis's callback and stateful execution policy into a Rust strategy
implementation.

The update may still be worthwhile: the range is 107 commits and changes 202
files, and it contains many Rust, portfolio, rolling-kernel, correctness, and
benchmarking changes. That makes it an upgrade candidate requiring regression
evidence, not a drop-in Rust acceleration of Aegis's current simulation path.
[Upstream comparison](https://github.com/polakowo/vectorbt.pro/compare/7801c7849838fdc2ee1b6b441dd93660d6c24f71...4a2000985a25219698c5ad8a1aa8d324d2074002)

## Measured outcome

- `uv.lock` now resolves `vectorbtpro` and `vectorbtpro-rust` to
  `4a2000985a25219698c5ad8a1aa8d324d2074002` (`2026.6.27`) and pandas to
  `3.0.3`. The Rust extension was built in release mode and is available.
- The exact deterministic Aegis callback workload (1,000 rows, 32 Candidates,
  four symbols) retained 6,272 orders and identical value output. Warm median
  runtime moved from 0.1658 seconds to 0.1629 seconds, an immaterial 1.8%
  improvement.
- The final project environment passed all 1,017 `aegis-rd` tests. Pandas 3
  exposed one real Aegis bug: margin-day offsets interpreted a
  `DatetimeIndex`'s raw storage as nanoseconds. The implementation now converts
  explicitly to calendar-day units and is covered end to end with a
  microsecond-resolution index.
- `benchmarks/cache.json` was regenerated in the new VBT schema for the serial,
  sparse `from_signal_func` and `from_signals` cases. At 1,000 x 100,
  AutoBench has no Rust candidate for dynamic `from_signal_func` and falls back
  to Numba; native `from_signals` selects Rust (1.97 ms versus 2.66 ms,
  approximately 1.35x faster).

## What changed

The previous lock resolved both `vectorbtpro` and `vectorbtpro-rust` to the same
commit and installed version, `2026.4.7`; the inspected source version is
`2026.6.27`. The Rust dynamic simulator arrived on 2026-07-16 and was followed
by order-function parity, flexible-order callbacks, parallel group execution,
hot-path optimization, broader tests, and public API documentation. The latest
commit also adds native allocation/optimization callback engines.
[Initial dynamic-simulator commit](https://github.com/polakowo/vectorbt.pro/commit/0c455d51),
[parallel-group commit](https://github.com/polakowo/vectorbt.pro/commit/cc353a33),
[latest native-pfopt commit](https://github.com/polakowo/vectorbt.pro/commit/4a2000985a25219698c5ad8a1aa8d324d2074002)

The simulator has meaningful upstream test coverage: its test suite compares
dynamic and static outputs across records, accounting state, call sequences,
ranges/continuation, sizing, conflicts, limits, stops, lifecycle behavior, and
serial versus parallel groups. Upstream also ships native simulator benchmark
cases. This is encouraging implementation evidence, but the API landed only
five days before the inspected head and `develop` remains a moving target.
[Simulator tests](https://github.com/polakowo/vectorbt.pro/blob/4a2000985a25219698c5ad8a1aa8d324d2074002/rust/tests/simulator.rs),
[native benchmarks](https://github.com/polakowo/vectorbt.pro/blob/4a2000985a25219698c5ad8a1aa8d324d2074002/rust/benches/simulator.rs)

## Why Aegis cannot use the new dynamic simulator directly

Upstream explicitly defines the dynamic simulator as a **native-Rust-only**
equivalent of the Numba callback simulators. It has no PyO3 wrapper and no
jitting-registry entry. Strategies implement Rust traits or closures; callback
behavior is aligned with Numba but callback signatures are not identical. It
also has no row-wise counterpart and no public step/session API. Parallelism is
only across independent column groups; rows and callbacks within a group stay
sequential.
[Rust dynamic-simulator contract](https://github.com/polakowo/vectorbt.pro/blob/4a2000985a25219698c5ad8a1aa8d324d2074002/rust/README.md#dynamic-portfolio-simulators)

The native allocation/optimization engines have the same boundary: they do not
replace Python `PortfolioOptimizer`, pandas scheduling, parameterization,
record preparation, or portfolio simulation.
[Native pfopt boundary](https://github.com/polakowo/vectorbt.pro/blob/4a2000985a25219698c5ad8a1aa8d324d2074002/rust/README.md#dynamic-portfolio-allocation-and-optimization)

Aegis calls `PFO.from_filled_allocations`, then
`Portfolio.from_optimizer(..., pf_method="from_signals")` with `order_mode`, a
staticized `pre_order_segment_func_nb`, target-allocation state, drift bands,
margin-interest state, dividends, fees, slippage, grouping, and a NoCash
tripwire. See
[`_build_portfolio`](../../research/aegis_research/optimization/window_evaluation/_simulation.py#L354)
and
[`_band_pre_order_segment_nb`](../../research/aegis_research/optimization/window_evaluation/_simulation.py#L175).

Both the pinned VBT MCP source and latest upstream source show that
`from_optimizer(..., pf_method="from_signals")` calls `from_signals` with
`order_mode=True`. VBT's preparer classifies `order_mode`, any callback, or a
`staticized` function as dynamic mode and selects `from_signal_func_nb`.
[Latest `from_optimizer`](https://github.com/polakowo/vectorbt.pro/blob/4a2000985a25219698c5ad8a1aa8d324d2074002/vectorbtpro/portfolio/base.py#L6387-L6527),
[dynamic-mode selection](https://github.com/polakowo/vectorbt.pro/blob/4a2000985a25219698c5ad8a1aa8d324d2074002/vectorbtpro/portfolio/preparing.py#L1585-L1651),
[target selection](https://github.com/polakowo/vectorbt.pro/blob/4a2000985a25219698c5ad8a1aa8d324d2074002/vectorbtpro/portfolio/preparing.py#L2579-L2588)

The static `from_basic_signals_nb` and `from_signals_nb` functions register
Python-facing Rust backends, while dynamic `from_signal_func_nb` registers no
`RustBackendSpec`. Consequently, merely updating both packages or passing
`jitted="rs"` cannot port Aegis's callback route to Rust.
[Static registrations](https://github.com/polakowo/vectorbt.pro/blob/4a2000985a25219698c5ad8a1aa8d324d2074002/vectorbtpro/portfolio/nb/from_signals.py#L1203-L1250),
[dynamic registration](https://github.com/polakowo/vectorbt.pro/blob/4a2000985a25219698c5ad8a1aa8d324d2074002/vectorbtpro/portfolio/nb/from_signals.py#L5519-L5525)

## Upgrade and benchmark gate

Run the comparison in two isolated environments, keeping `vectorbtpro` and
`vectorbtpro-rust` at the same commit/version in each:

1. **Current baseline:** locked commit `7801c784`; installed Rust support is
   available, but this version does not expose its build profile.
2. **Upgrade candidate:** `4a200098`; require a release-profile Rust extension.
   Latest automatic dispatch intentionally ignores development-profile Rust
   builds; explicit Rust still works, but a dev build is not valid speed
   evidence.
   [Build-profile policy](https://github.com/polakowo/vectorbt.pro/commit/631ef7479f9fb7b2a5ddfac3598c2761d44ac444)

Use one deterministic, representative Future-in-Past workload and test these
separately:

- **Aegis end to end:** the exact `PFO -> from_optimizer -> dynamic staticized
  callback` route at realistic rows, symbols, candidate groups, and sparse
  rebalance density. Compare the current and latest commits. This answers
  whether the dependency update is safe and faster; it does not benchmark the
  new native Rust simulator.
- **Python static control:** latest `Portfolio.from_signals` without callbacks
  or `order_mode`, forcing Numba and Rust separately. This proves the Rust wheel
  and dispatch work and measures whether a callback-free future route would
  benefit.
- **Native Rust spike only if warranted:** port a minimal representative drift
  gate/state strategy and compare the crate's serial and parallel-group runners.
  Do this only after the end-to-end profile shows simulation is still a material
  bottleneck and the expected gain justifies owning Rust strategy code.

For parity, compare order and log records, cash, position, debt/free cash,
fees, value and returns paths, terminal liquidation, NoCash rejections, drift
gate decisions, margin-interest accrual, cash dividends/distributions,
`from_ago` fill timing, size granularity, and candidate grouping. Use fixed
inputs/seeds, exclude compilation/build time from warm steady-state timing, and
also record cold-start cost. Do not combine Rust group parallelism with Aegis's
outer candidate/process parallelism.

Latest VBT also provides AutoBench and AutoBenchMixed for registered Python
backends. They require benchmark records; AutoBenchMixed should not be nested
inside an outer executor. These tools can guide supported kernels, but they
cannot select the unregistered native dynamic simulator.
[AutoBench contract](https://github.com/polakowo/vectorbt.pro/blob/4a2000985a25219698c5ad8a1aa8d324d2074002/rust/README.md#autobench),
[AutoBenchMixed nesting warning](https://github.com/polakowo/vectorbt.pro/blob/4a2000985a25219698c5ad8a1aa8d324d2074002/rust/README.md#autobenchmixed)

## Decision rule

Update the pin only if the latest environment passes the existing suite and the
end-to-end parity matrix, with no material semantic drift. Accept the update for
correctness/maintenance or measured Aegis performance independently of the new
native simulator. Open a separate Rust-port experiment only if profiling shows
the dynamic callback simulator dominates replay time and a representative port
demonstrates enough end-to-end gain to pay for the new language and FFI
boundary.
