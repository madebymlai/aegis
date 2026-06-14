---
date: 2026-05-20
topic: strategy-playbook-central-execution
---

# Strategy Playbook Central Execution Contract

## Summary

Aegis run leaderboards should have one authoritative execution and metric source. Playbooks and components may both produce strategy ideas, candidate params, and signals, but any row ranked by `aerd run` must be evaluated through the same Aegis-owned VBT portfolio execution contract.

---

## Problem Frame

The current research workflow separates promoted strategy components from exploratory strategy playbooks, but the comparison boundary is not strict enough. Promoted strategy components produce signals that flow through Aegis-owned portfolio execution, while strategy playbooks can currently emit precomputed metrics that the leaderboard treats as ranked evidence.

That creates a fairness problem. A playbook row can appear beside a component row even though the metrics may have been computed with different fees, slippage, sizing, direction, execution timing, cash sharing, or metric calculation choices. Source labels help readers audit provenance, but they do not make the ranked comparison meaningful when metric ownership differs.

---

## Actors

- A1. Researcher: Explores strategy ideas and parameter sweeps before deciding what is worth promoting.
- A2. Strategy component author: Promotes a winning idea into reviewed, reusable component code.
- A3. Strategy run reviewer: Reads run leaderboards and expects ranked rows to be comparable under one execution contract.
- A4. Automation agent: Runs configs, validates playbook output, and needs unambiguous success/failure rules for comparable ranked evidence.

---

## Key Flows

- F1. Ranked strategy playbook candidate
  - **Trigger:** A researcher selects a strategy playbook in a run config.
  - **Actors:** A1, A3, A4
  - **Steps:** The playbook produces one or more strategy candidates with reproducible params and aligned signal outputs. Aegis applies the central portfolio execution contract to each candidate, computes metrics, and ranks the resulting rows.
  - **Outcome:** Playbook-backed rows use the same execution and metric source as component-backed strategy runs, while this contract keeps one selected strategy source per run config.
  - **Covered by:** R1, R2, R3, R4, R5
- F2. Invalid playbook metric source
  - **Trigger:** A strategy playbook tries to provide its own ranked metrics instead of letting Aegis compute them.
  - **Actors:** A1, A3, A4
  - **Steps:** Aegis validates the playbook output before accepting rows into the run leaderboard and rejects output that would make the playbook the metric source.
  - **Outcome:** The run fails visibly instead of publishing a mixed-authority leaderboard.
  - **Covered by:** R2, R5, R6
- F3. Promotion from playbook winner to component
  - **Trigger:** A centrally ranked playbook candidate performs well enough to promote.
  - **Actors:** A1, A2, A3
  - **Steps:** The winner's params identify how to reproduce the signal idea. The promoted component implements the signal logic, and future component-backed runs use the same central execution path.
  - **Outcome:** Promotion changes the source of signal logic, not the source of portfolio execution or ranked metrics.
  - **Covered by:** R1, R3, R4, R7

---

## Requirements

**Authoritative execution**
- R1. Any row that appears in the Aegis run leaderboard must use Aegis-owned portfolio execution for authoritative metrics and ranking.
- R2. Playbook-computed metrics must not be accepted as authoritative leaderboard metrics for ranked run rows.
- R3. Strategy playbooks and strategy components must share the same portfolio execution assumptions for their ranked rows, even though a run config selects one strategy source.

**Playbook candidate output**
- R4. Strategy playbooks must provide candidate params and signal outputs sufficient for Aegis to execute and score each ranked candidate centrally.
- R5. Aegis must reject strategy playbook candidates that cannot be centrally executed under the shared strategy-run contract.
- R6. Aegis must reject playbook output that attempts to make playbook-computed metrics the source of ranked results.

**Promotion and reproducibility**
- R7. Each ranked playbook candidate must preserve enough params and source identity to reproduce the signal idea and promote a winner into a strategy component without relying on hidden local state.
- R8. Run artifacts must preserve source identity so reviewers can distinguish playbook-backed signal ideas from component-backed signal ideas while trusting the same execution and metric source for both.

---

## Acceptance Examples

- AE1. **Covers R1, R3, R4.** Given a run config selecting a strategy playbook, when the playbook produces candidates with aligned signals, Aegis computes portfolio metrics through the same execution contract used by component-backed strategy runs and ranks the playbook candidates without accepting playbook-computed metrics.
- AE2. **Covers R2, R6.** Given a strategy playbook candidate that includes playbook-computed ranked metrics, when Aegis validates the candidate for the run leaderboard, it rejects the candidate instead of trusting those metrics.
- AE3. **Covers R5.** Given a strategy playbook candidate with missing or misaligned signals, when Aegis tries to accept it into a ranked run, it fails visibly before publishing a leaderboard row.
- AE4. **Covers R7, R8.** Given a winning strategy playbook candidate, when a reviewer inspects the run artifact, the row identifies the playbook source and the params needed to reproduce or promote the signal idea.

---

## Success Criteria

- A reviewer can trust that every ranked row in a run leaderboard was scored under one Aegis-owned execution contract.
- A playbook-backed candidate and a component-backed candidate can be compared across equivalent single-source runs or future aggregation surfaces without hidden differences in fees, slippage, sizing, timing, direction, cash sharing, or metric ownership.
- A winning playbook row carries enough params to guide manual promotion into a reviewed strategy component.
- A downstream planner does not need to invent whether playbooks own metrics, whether mixed metric sources are allowed, or how playbook-backed rows differ from component-backed rows in ranked comparison.

---

## Scope Boundaries

- No playbook-owned authoritative metrics for rows that appear in the run leaderboard.
- No mixed-authority leaderboard where some rows are scored by Aegis and others by playbook-local metric code.
- No same-run multi-strategy comparison in this contract; a run config selects one strategy source.
- No `.ipynb` files as registered playbook sources; playbooks are Jupytext-compatible Python percent-cell scripts.
- No automatic promotion from playbook winner to component.
- No expansion of the baseline portfolio execution model in this requirement; alternate execution models need a separate contract.
- No requirement that freeform notebook exploration outside `aerd run` stop computing local metrics; the restriction applies to Aegis-ranked run evidence.

---

## Key Decisions

- One source of truth: Aegis owns portfolio execution and ranked metrics for run leaderboards.
- Playbook source form: Registered playbooks are Python `.py` files using `# %%` percent cells, so the same file is reviewable source and interactive playground in Jupytext-compatible tools.
- Playbooks as candidate producers: Strategy playbooks may remain exploratory, but Aegis-consumed ranked output must provide candidates that can be centrally executed.
- Source-neutral comparison: The leaderboard may distinguish playbook and component sources, but metric computation must not differ by source kind.
- Promotion preserves execution semantics: Promoting a playbook winner to a component changes where signal logic lives, not how portfolio execution or ranking works.

---

## Dependencies / Assumptions

- `docs/brainstorms/2026-05-18-research-playbook-component-workflow-requirements.md` establishes playbook and component source selection, manual promotion, and config-owned portfolio assumptions.
- `docs/brainstorms/2026-05-18-portfolio-simulation-contract-requirements.md` establishes the baseline central portfolio execution contract.
- `docs/brainstorms/2026-05-17-signal-generation-conflict-semantics-requirements.md` establishes signal semantics and VBT `Portfolio.from_signals` constraints that central execution should preserve.

---

## Outstanding Questions

### Deferred to Planning

- [Affects R4, R5][Technical] What Python callable boundary should strategy playbooks use to return signal candidates safely and portably to Aegis for central execution?
- [Affects R5, R6][Technical] How should Aegis classify and report invalid strategy playbook output so researchers can repair Python percent-cell playbooks quickly?
- [Affects R1, R8][Technical] How should existing playbook examples and tests migrate from precomputed metric records to centrally executed strategy candidates?
