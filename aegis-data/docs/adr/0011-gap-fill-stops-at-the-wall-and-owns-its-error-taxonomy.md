# The gap fill stops at the no-data wall and owns its error taxonomy

Status: accepted

Reinforces ADR-0006/0008. Fixes GH #75.

## Context

A lazy fill whose window reached past an instrument's available history hung in
production (GH #75: TLT pre-2016, SPTL pre-2017). The vendor client splits a
wide window into backward segments and burns a full request timeout on *every*
pre-listing segment — a decade of missing history is a serial chain of dead
120-second waits, and the vendor stack also contains genuinely unbounded awaits
(connect, shared-request futures, qualification of an instrument that cannot
resolve to one asset). The reliable operator workaround was bounding the fetch
window by hand and pre-seeding the catalog.

Separately, a provider fault during Ensure Coverage crossed the port as a
vendor type (`IbkrRequestError`), so consumers could not handle environmental
failure without importing the IBKR adapter — against the port's DIP promise.

## Decision

- **The provider owns the backward walk and stops at the wall.** The IBKR
  provider fetches a window newest-first in ≤365-day chunks through one
  session; the first empty chunk is the no-data wall and ends the walk — each
  earlier chunk could only burn another timeout to learn the same thing. Bars
  already pulled are returned and written, so even a failed fill leaves the
  Historical Store warmer (the pre-seeding workaround, institutionalised).

- **The provider's answer is `ServedBars` (bars + `served_from`).** `served_from`
  is the requested start when the whole window was walked, or the oldest
  data-bearing chunk's start when the wall stopped the walk. The port claims
  catalog coverage only from `served_from`: an empty head inside a walked
  window (weekend, holiday) stays covered, a pre-wall head stays missing.
  This is the one bit that distinguishes "no bars because nothing traded"
  from "no bars because history ends" — and only the provider has it.

- **The coverage gate stays the sole unsatisfiability judge.** After the fill,
  remaining missing intervals raise `CatalogCoverageGapError` naming exactly
  which intervals cannot be served. There is no dedicated wall error and no
  new timeout machinery in the port.

- **Every vendor await is deadline-bounded.** The provider wraps each session
  await (connect, chunk fetch, instrument fetch) in `call_deadline`
  (default 600s): a call that makes no progress is dead, not slow, and
  surfaces as `IbkrRequestError` with the cause chained instead of hanging.

- **The port owns the environmental error taxonomy.** Provider faults during
  Ensure Coverage — the bar fill, the definition seeding, the adjusted-last
  distribution fetch — are translated at the port into `GapFillProviderError`
  with the original chained as cause. Together with `CatalogCoverageGapError`
  these are the only errors a consumer sees for environmental causes; no
  vendor type crosses the port contract. Authoring-level port errors
  (`ContinuousRootLegsNotFoundError`, `ContinuousRootVenueMismatchError`)
  are unchanged.

## Consequences

- A window reaching pre-listing history terminates in bounded time: the wall
  chunk costs at most one request timeout, and the run gets a judged
  coverage-gap verdict with exact intervals (verified live: TLT 2014→2017 in
  ~121s, partial history persisted).
- The pre-wall head is never claimed as covered, so a run that keeps
  requesting a too-wide window re-checks that head once per fill attempt —
  one bounded empty request each time. Unavailability stays a judged verdict,
  not a cached fact.
- **The wall's precision is one chunk (≤365 days).** ``served_from`` is the
  oldest *data-bearing chunk's* start, not the first bar: that whole span was
  queried and the source answered with everything it has, so the claim is
  honest in the verified-against-source sense — the same semantics that keep
  holiday/weekend heads covered. The cost: a window starting inside the wall
  chunk but before the first bar is served short without a gap verdict (the
  Run's coverage facet still records the actual span). Claiming from the
  first bar instead would raise false gap verdicts for non-trading-day heads
  at the wall chunk — rejected.
- Consumers (aegis-rd's market-data loader) can wrap exactly two port errors
  to build their failure contract (aegis-rd-1gef.3) without importing any
  vendor module.

## Alternatives considered

- **A dedicated wall error from the provider.** Rejected: it makes the
  provider a second unsatisfiability judge, and the partial bars would have to
  ride inside the exception for the port to persist them. The `served_from`
  fact gets the same effect through the normal return path.
- **Keep claiming the whole requested interval as covered.** Rejected: a
  wall-truncated fill would silently serve a short window forever, and the
  unavailability verdict would have to move into RD's quality judge —
  rewriting the settled failure-contract story.
- **Let `IbkrRequestError` cross the port.** Rejected: consumers would depend
  on the vendor adapter (DIP violation), and the error names a mechanism, not
  the port-level fact ("the gap fill failed environmentally").
