---
date: 2026-05-21
topic: component-candidate-promotion
github_issue: 32
depends_on_github_issue: 31
---

# Component Candidate Promotion

## Summary

Aegis should persist native optimization candidates, promote selected candidates through explicit locked-parameter references, and make parameterized components the single canonical surface for both exploration and fixed runs. Legacy playbook and candidate-grid paths should be removed after components cover the same workflows.

---

## Problem Frame

Issue #31 moves optimization execution to native VectorBT PRO parameterization, but it intentionally stops before candidate persistence, promotion, and component unification. That leaves a temporary split: optimization evidence is derived from VBT result indexes, while reusable implementation surfaces are still split between fixed-param components and exploratory playbooks.

That split creates manual promotion work. A researcher finds a winning optimized row, then copies params into a fixed component or config by hand. It also keeps two authoring models alive: components for promoted behavior and playbooks for exploratory candidate axes. Once the optimization runner emits stable candidate evidence from native VBT indexes, Aegis can remove that split instead of preserving another abstraction layer.

---

## Evidence Used

- GitHub issue #32: `Persist optimization candidates and unify playbooks into parameterized components`.
- GitHub issue #31: `Move playbook sweeps to native VectorBT parameterization`.
- Prior requirements: `docs/brainstorms/2026-05-21-vbt-native-only-optimization-requirements.md`.
- Current docs already mark legacy playbook/candidate-grid surfaces as deprecated and scheduled for removal under #32 in `docs/playbooks.md` and `docs/vectorbt-scaffold.md`.

---

## Actors

- A1. Research user: Runs optimization jobs, compares candidates, and promotes a selected result into repeatable research runs.
- A2. Component author: Defines reusable strategy or indicator implementations with optional VBT-native param spaces and defaults.
- A3. Aegis run lane: Validates config, resolves components, executes optimization, persists evidence, and records promotion provenance.
- A4. Reviewer or automation agent: Inspects candidate evidence, locked-param references, and run artifacts for reproducibility.
- A5. Future planner or implementer: Uses this document to remove legacy playbook/candidate-grid code without inventing new product behavior.

---

## Key Flows

- F1. Persist optimization candidates
  - **Trigger:** A native VBT optimization run completes with candidate evidence.
  - **Actors:** A1, A3, A4
  - **Steps:** Aegis derives candidate rows from native result-index evidence, stores candidate params, metrics, rank, source identity, data identity, and provenance, then exposes query paths for top candidates and specific candidate lookups.
  - **Outcome:** Optimization results become first-class candidate rows that can be queried and reused without depending on legacy candidate-axis IDs.
  - **Covered by:** R1, R2, R3, R4, R5, R6
- F2. Promote a best candidate through a lock reference
  - **Trigger:** A completed optimization run identifies the best ranked candidate for a component.
  - **Actors:** A1, A3, A4
  - **Steps:** Aegis emits a stable promotion token for the best candidate, persists that token on the winning candidate row, and allows later configs to lock a component against that reference.
  - **Outcome:** Promotion is explicit, stable, shareable, and reproducible without relying on mutable concepts like latest best.
  - **Covered by:** R7, R8, R9, R10, R11, R12
- F3. Pin a non-best candidate explicitly
  - **Trigger:** A researcher wants reproducibility against a candidate that was evaluated but was not the top-ranked row.
  - **Actors:** A1, A3, A4
  - **Steps:** The config references the specific candidate row directly, Aegis resolves its params for the matching component, and evidence records the resolved candidate and params.
  - **Outcome:** Non-rank-1 experiments remain reproducible without overloading best-candidate promotion tokens.
  - **Covered by:** R9, R10, R11, R13
- F4. Compose locked and unlocked components in one run
  - **Trigger:** A config includes a strategy and one or more indicators where some component slots are locked and others remain exploratory.
  - **Actors:** A1, A2, A3
  - **Steps:** Aegis resolves locked component params as constants, reads param spaces from unlocked components, validates component output/consumption compatibility, and runs one composed native VBT optimization grid over the unlocked axes.
  - **Outcome:** Mixed promoted and exploratory components can be tested together without reintroducing playbook sweeps.
  - **Covered by:** R14, R15, R16, R17, R18, R19, R20, R21, R22, R23
- F5. Migrate away from playbooks
  - **Trigger:** Parameterized components support exploration, fixed runs, locked params, and composed optimization.
  - **Actors:** A2, A3, A5
  - **Steps:** Existing tracked playbooks and examples are migrated to components, docs are updated to describe components as canonical, and legacy playbook/candidate-grid execution paths are removed from active contracts.
  - **Outcome:** Aegis has one forward implementation surface and one native optimization model.
  - **Covered by:** R24, R25, R26, R27

---

## Requirements

**Candidate persistence**
- R1. Optimization candidate rows must be persisted as first-class records derived from native VBT result-index evidence.
- R2. Persisted candidate identity must reuse the existing stable candidate key emitted from native candidate evidence; #32 must not introduce a parallel candidate ID scheme based on legacy candidate-axis or composed-candidate identifiers.
- R3. Candidate rows must preserve enough params, metrics, split metrics, rank, component identity, source identity, portfolio policy, data identity, and run provenance to reproduce and audit the result.
- R4. Candidate persistence must support querying the top 1 candidate for a run, top 5 candidates for a run, top N candidates by metric, params by candidate key, params by promotion token, and provenance back to the originating run.
- R5. Persistence may begin as local storage or normalized artifact storage, but it must behave like a durable candidate table rather than a leaderboard-only artifact dump.
- R6. Candidate persistence must preserve the source/data/portfolio identity that makes an otherwise identical param row a distinct candidate.

**Promotion and locked params**
- R7. Every completed optimization run must emit a stable, opaque promotion token for each ranked component's best candidate.
- R8. A promotion token identifies the promotable best candidate for a specific run/component pair; it must not identify a mutable concept such as latest best.
- R9. Each strategy and indicator component entry may lock params by referencing either a best-candidate lock reference (`lock_id`) or a specific candidate-row reference (`candidate_id`), but not both at the same time.
- R10. Promotion-token resolution must validate that the token belongs to a candidate row for the same component named by the config entry.
- R11. Locked components must contribute fixed parameter values to a run, while unlocked components contribute their VBT-native param spaces to the optimization grid.
- R12. Runs that use locked params must record the resolved candidate key and exact resolved params in their evidence, not only the original promotion reference.
- R13. Direct candidate-key pinning must support reproducibility against non-rank-1 candidate rows.

**Parameterized components**
- R14. Components must become the canonical source surface for optimized and fixed research runs.
- R15. A component may expose a fixed callable, optional VBT-native param space, defaults for non-optimized runs, and locked params resolved from config.
- R16. Optimized component runs must support `strategy.source: component` as the forward path and must no longer reject component sources solely because optimization is present.
- R17. Components without a param space may still participate in fixed runs, but they must not be treated as sweepable optimization sources.
- R18. Indicator entries and the strategy entry must jointly drive the composed optimization grid when they are present in the same config.
- R19. Strategy components must declare the indicator outputs they require, indicator components must declare the outputs they produce, and validation must fail when the configured set cannot satisfy the strategy's declared needs.

**Composition behavior**
- R20. Mixed locked and unlocked component entries must be supported in one native VBT optimization run.
- R21. When multiple components contribute unlocked axes, Aegis must compose those axes into one native optimization grid rather than running separate playbook sweeps.
- R22. Aegis must pass indicator outputs into strategy execution through an explicit named-output contract, not by implicit ordering or hidden coupling.
- R23. The schema for indicator entries must support per-component locking clearly; any batched shorthand that conflicts with per-entry locking must be removed or restricted to non-locking convenience.

**Playbook removal and migration**
- R24. Existing tracked RSI/MA playbooks and the #31-era optimization playbook example must migrate to component form before the active playbook optimization contract is removed.
- R25. Docs and examples must describe components as the only canonical implementation surface after migration; playbook docs/examples must be removed or converted rather than left as deprecated forward guidance.
- R26. Playbook-specific optimization contracts, candidate-grid fields, top-level split fields for legacy sweeps, and candidate-axis execution paths must be removed from active run contracts after component parity exists.
- R27. Legacy read/reporting compatibility for historical artifacts may exist only if planning identifies a concrete persisted-data or external-consumer requirement; it must not preserve playbooks as an indefinite active authoring path.

---

## Acceptance Examples

- AE1. **Covers R1, R2, R3, R4.** Given a completed native optimization run, when a user asks for the top 5 candidates for that run, Aegis returns persisted candidate rows keyed by native candidate keys with params, metrics, rank, and provenance.
- AE2. **Covers R7, R8, R10, R12.** Given a completed run with a ranked strategy component, when a later config locks that strategy by promotion token, Aegis resolves the token to the run/component's best candidate, records the resolved candidate key and params, and executes with those params fixed.
- AE3. **Covers R9, R13.** Given a researcher wants to reproduce the third-ranked row from a run, when the config pins the candidate key directly, Aegis resolves that exact row without treating it as the promoted best result.
- AE4. **Covers R11, R18, R20, R21.** Given a config with one locked indicator, one unlocked indicator, and an unlocked strategy, when optimization runs, only unlocked axes form the VBT parameter grid while the locked indicator's params remain constant.
- AE5. **Covers R14, R15, R16, R17.** Given a component with a callable and VBT-native param space, when a config uses that component with optimization, validation accepts it as the forward optimization source; given a fixed-only component, validation does not treat it as sweepable.
- AE6. **Covers R19, R22.** Given a strategy declares it consumes an RSI output, when the configured indicators do not produce that output, validation fails before execution.
- AE7. **Covers R23.** Given an indicator entry wants its own lock reference, when the config uses a batched multi-ID shorthand that cannot express per-entry locking, validation rejects or disallows that shorthand for the locking case.
- AE8. **Covers R24, R25, R26, R27.** Given parameterized components cover the RSI/MA examples, when docs and active contracts are inspected, playbook optimization docs and candidate-grid run paths are no longer presented as forward behavior.

---

## Success Criteria

- A research user can run native optimization, query persisted candidates, and promote a chosen component candidate without copying params by hand.
- Promotion is explicit and reproducible: every locked-param run records the exact candidate and params it resolved.
- Components become the only forward authoring surface for both exploratory and fixed strategy/indicator behavior.
- Mixed locked and exploratory component runs work without reintroducing custom candidate-grid semantics.
- Legacy playbook and candidate-axis concepts are removed from active run contracts after migration.
- Downstream planning can implement #32 without inventing candidate identity, promotion semantics, component-vs-playbook boundaries, or success criteria.

---

## Scope Boundaries

- Do not implement #32 before #31's native optimization runner and native candidate evidence are available.
- Do not persist the current custom candidate-axis or composed-candidate model as the new durable candidate schema.
- Do not add hidden latest-best behavior or any mutable promotion reference.
- Do not preserve playbooks indefinitely as an alternate canonical authoring path without a concrete external-consumer requirement.
- Do not store only top candidates without enough provenance to reproduce the run.
- Do not introduce a new optimizer engine, a new custom search path, or an adapter that feeds native VBT params back into legacy candidate composition.
- Do not require partial locking to ship unless planning explicitly decides it is worth the added contract surface.
- Do not let docs keep deprecated playbook examples as if they are still the recommended path.

---

## Key Decisions

- Components become canonical: The long-term implementation surface should be components with optional param spaces, not a component/playbook split.
- Candidate keys remain native-evidence derived: The row identity from #31's VBT result-index evidence is the candidate identity #32 should persist and reuse.
- Promotion is per component: Locking belongs on each strategy or indicator component entry so mixed promoted/exploratory runs remain natural.
- Promotion tokens are stable and opaque: They are shareable handles for a run/component's best candidate, not mutable aliases.
- Direct candidate pinning is separate from promotion: Non-best reproducibility uses the candidate key directly instead of overloading best-candidate locks.
- Composition is config-driven: The configured strategy plus configured indicators together define the joint optimization space.
- Legacy deletion waits for parity: Playbook/candidate-grid paths should be removed after parameterized components cover existing tracked examples and workflows.

---

## Dependencies / Assumptions

- #31 provides native optimization execution, native result-index candidate evidence, deterministic serialization, failure diagnostics, preflight resource gates, and held-out leaderboard evidence.
- #32 should extend #31's native optimization runner, candidate evidence, leaderboard, preflight, source validation, and strategy-run wiring rather than redesigning those surfaces.
- Existing candidate keys emitted from native candidate evidence are stable enough to become persisted row IDs.
- Current docs already identify playbook/candidate-grid contracts as deprecated for #32, so removing them is aligned with the forward direction.
- Whole-component locking is the required #32 behavior; partial locking remains optional unless explicitly chosen during planning.
- Historical artifact compatibility is not an implicit requirement. Planning must identify concrete persisted-data or external-consumer needs before adding compatibility surface.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R5][Technical] Should the first persistence implementation be local SQLite, normalized artifact tables, or another durable store that satisfies the query requirements?
- [Affects R7, R8][Technical] What exact promotion-token format should be used to remain stable, opaque, human-shareable, and component-scoped?
- [Affects R12][Technical] Where should locked-param resolution evidence live so future runs remain reproducible even if the original optimization artifact moves?
- [Affects R19, R22][Technical] What exact component metadata and runtime shape should represent produced indicator outputs and strategy consumption?
- [Affects R23][Technical] Should batched indicator shorthand be removed entirely, or retained only when no per-entry locking is present?
- [Affects R24, R25, R26][Technical] Which legacy playbook docs, examples, tests, and run paths can be deleted immediately after component migration, and which require transitional read/reporting support?
- [Affects R20, R21][Product/technical] Should partial locking of a subset of component params ship in #32, or should #32 require whole-component locking only and defer subsets?
