# Continuous-futures adjustment mode is a recorded Run fact and a DataContract fact

Status: accepted (implemented, aegis-rd-tkj5). **Refines ADR-0007**: futures
continuity stays live and data-layer-owned — the Roll Desk still drives
`aegis-data`'s `ContinuousContractModel` (volume-led front selection) — but the
*re-basing algebra* is no longer a hard-coded data-layer default. The mode is a
historical fact of the Run that materialised the frames, declared on the
Execution Bundle's `DataContract`, and threaded explicitly everywhere the shared
research/live path touches a continuous series.

## Decision

The effective `ContinuousFutureAdjustmentType` (`BACKWARD_RATIO` or
`BACKWARD_SPREAD`; forward modes are unsupported) is:

1. **Selected once per Run.** Research resolves the effective mode when it
   materialises a Run's continuous frames and passes that exact enum into
   `ContinuousContractModel` — whose `adjustment_mode` keyword is required, with
   no default on the shared path.
2. **Recorded as Run evidence and Candidate identity.** The applied mode is
   persisted in `candidate_data_identity.v3` (present iff futures were
   materialised), so otherwise-identical ratio and spread Runs have different
   Candidate keys; Candidate Store provenance carries the same identity.
3. **Lock-resolved, never defaulted at export.** `ResolvedLockRun.adjustment_mode`
   is the single persisted-provenance read. Export writes that fact into
   `DataContract.adjustment_mode` (`execution_bundle.v4`; a v3 payload is
   rejected by schema version — Forward-First, no legacy decoder). A
   futures-declaring export whose locked Run recorded no mode fails loudly with
   re-run/re-lock guidance; there is no fallback to `DEFAULT_ADJUSTMENT_MODE`.
4. **Contract-enforced.** `DataContract` requires the mode iff `futures`
   declares roots, accepts only the two backward members as the native Nautilus
   enum, and keeps the mode independent of `exchange` — ratio and spread are
   both valid with or without FX conversion legs.
5. **Probed at the native-price boundary.** The data layer owns materialisation
   and continuous re-basing upstream. `ExecutionBundle.compute_weights` guards,
   rather than executes, the invariant operation order

   `native contracts -> continuous re-base -> native continuous root -> FX conversion -> indicators -> Strategy`

   while its decision callback executes FX conversion, contract validation,
   indicators, Strategy, and Exposure Validation in that order. The runtime
   roll-sensitivity check perturbs each declared root
   *independently* in native units under the declared mode, recomputing through
   the same currency-conversion/Component composition. Under moving FX a spread
   probe is therefore `(price + shift) * FX(t)`, never a constant base-currency
   shift. The check is a deterministic **metamorphic check** — passing means the
   allocation survived the configured probes; it proves nothing about arbitrary
   Strategy code.
6. **Live materialisation is declaration-driven.** Book startup unions every
   Sleeve contract into one `ContinuousRootDeclaration` (synthetic id + mode)
   per bare root; an incoherent root halts with the typed
   `StartupGate.CONTINUOUS_DECLARATION` before Roll Desk starts. Roll Desk
   materialises each root under its declaration's mode, and the model's
   `ContinuousFuture` derives the matching roll carry — multiplicative for
   ratio, additive for spread — so the emitted `Rebasing` follows the declared
   algebra automatically.

## Considered and rejected

- **Export-time default reads** (reconstructing the historical mode from the
  current `DEFAULT_ADJUSTMENT_MODE`): rejected — a code-default change between
  Run and export would silently change what a deployed bundle declares.
- **A parallel Aegis mode enum or parallel `ids_by_root`/`modes_by_root` maps**:
  rejected — the native Nautilus enum is the one vocabulary, and one declaration
  value object per root is the one shape (Law of Demeter, no primitive
  obsession).
- **Post-FX uniform spread probes** (shifting the already converted panel):
  rejected — `convert(price + shift)` is not `convert(price) + shift` under
  time-varying FX; the probe must ride the native side of the conversion.
- **Move continuous re-basing into the execution kernel**: rejected — it would
  contradict this decision's data-layer ownership, duplicate the live
  materialisation algebra, and make the kernel responsible for catalog history.
- **Rejecting `BACKWARD_SPREAD` when `exchange` is declared**: rejected — mode
  and FX are independent facts, and the coupling would not repair the lost
  representation anyway.
- **Validate-only live defaults** (model defaults silently, live merely checks):
  rejected — the shared research/live path must not be able to materialise under
  an unnamed algebra.

## Consequences

- A default change between Run and export cannot change an exported mode.
- Old runtimes reject v4 bundles by schema version; the generated wheel requires
  `aegis-runtime>=0.2.0`.
- ETF-only contracts declare no mode and pay no probe cost.
- ADR-0007's "`BACKWARD_RATIO`" and "data-layer-owned ratio re-basing" phrasing
  is amended in place to reference this ADR.
