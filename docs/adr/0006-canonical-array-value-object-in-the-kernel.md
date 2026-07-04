# The Array value object (`MarketDataBundle`) is canonical in the kernel

Status: accepted (as built). Finishes aegis-rd ADR-0020's "one Array interface" intent
across the research↔execution seam.

`MarketDataBundle` — the eager **Array** value object a **Component** reads prices from
(`bundle.array(name)`, fail-loud on a dict miss) — was defined **twice**: once in the shared
kernel (`aegis_runtime/bundle.py`) and once in research (`aegis_research/market_data/contracts.py`).
The two were structurally identical — one `arrays` mapping, one guarded accessor, fail-loud on a
dict miss — differing only in the error string and the field's static type. aegis-rd ADR-0020 had
declared `MarketDataBundle` "the single Component-facing Array interface", but that single-ness only
held *inside* research; the kernel copy is the part that escaped it.

The duplication forced a hand-written conversion at the seam. A **Component** authored in research
was exercised against the research type, but when the same Component runs through an **Execution
Bundle** (live or backtest) it receives the *kernel* type — two nominal types for one concept, kept
compatible only by duck typing, with the export fidelity test rewrapping the research bundle into
the kernel type purely to cross the gap.

We collapse the two into one type, **owned by the kernel**:

- **The kernel's `aegis_runtime.bundle.MarketDataBundle` is the single canonical Array value
  object; research's copy is deleted.** The home is forced by the dependency arrow
  `aegis-rd → aegis-runtime`: the kernel imports nothing from research, so the shared type must live
  kernel-side and research must depend up onto it.
- **Research re-exports it through the `aegis_research.data` facade** (kept in `__all__`), sourced
  from `aegis_runtime`. Component-author-facing imports and the indicator/strategy guides are
  unchanged — only the duplicate *definition* dies. Internal `market_data` modules (`panels.py`,
  `currency.py`) import the type **directly from `aegis_runtime`** to avoid a `data.py ↔ panels.py`
  import cycle.
- **The kernel's neutral fail-loud wording is kept** — `"market data array {name!r} was not
  supplied"` — because it fits research-load, backtest, *and* live, where research's
  "...not loaded for this run" is meaningless. Research's invariant docstring is ported onto the
  kernel class so *"dict membership is the sole guard — an array is loaded iff it is a key"*
  survives the move.

## Considered options

- **Keep one canonical type in research and have the kernel import it**: rejected — it inverts the
  dependency arrow. `aegis-runtime` is the shared kernel both Aegis RD and every Execution Bundle
  net against; it cannot depend up into `research`.
- **Leave the two types and keep duck-typing them at the seam**: rejected. The conversion is
  invisible coupling — the two definitions must change together but nothing enforces it, and the
  export test had to rewrap one into the other to prove fidelity. ADR-0020's "one Array interface"
  is only true once the kernel copy is gone.
- **Pick research's `"...not loaded for this run"` message**: rejected. "this run" is a
  research-load concept; the same accessor fails in a live Execution Bundle where there is no Run.
  The context-neutral "was not supplied" is correct everywhere the one type is used.

## Consequences

- **There is exactly one `MarketDataBundle` definition in the repo** (`aegis_runtime/bundle.py`).
  `from research.aegis_research.data import MarketDataBundle` still resolves — now to the kernel type
  — and the name stays in `aegis_research.data.__all__`, so the facade surface is byte-stable.
- **The export fidelity seam no longer rewraps to cross a type gap.**
  `test_execution_bundle_export.py` drops its `RuntimeMarketDataBundle` alias and constructs the one
  `MarketDataBundle` directly. The provider-ticker → **InstrumentId** relabel it still performs is a
  *label-space* bridge (the Execution Bundle speaks `InstrumentId`; research's synthetic prices are
  authored in provider-ticker space), unrelated to the now-dissolved type gap.
- **The research↔execution kernel seam now has one Array vocabulary.** A Component sees the same
  `MarketDataBundle` whether it runs under a research **Run** or inside an Execution Bundle.
- The bundle remains a plain frozen `@dataclass` carrying DataFrames; it is never serialised through
  pydantic, so the move has no wire/identity impact and no golden-bytes movement. ADR-0020's typed
  `market_data.v3` metadata and the Result→Bundle builder are untouched.
