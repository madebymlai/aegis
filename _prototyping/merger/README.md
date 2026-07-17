# Cash-merger convergence prototype

This directory contains all cash-merger experimental work. It is deliberately outside
`aegis-rd`, `aegis-trader`, and their normal test suites.

`historical/` retains the successive Massive-backed experiments and their reports.
`legacy_aegis_rd/` retains the earlier retired Aegis RD component/config attempt and its
generated runs; its old checks are under `_prototyping/tests/legacy_aegis_rd` and are evidence,
not an active suite. `shadow/` is the forward evidence collector for the surviving frozen `q70` control. The
control is **not promoted alpha**: the gate remains closed until the prospective ledger has
at least 100 resolved events and 10 adverse resolutions.

## Prospective run

Copy `shadow.example.yaml` to a local config, add only IBKR-qualified InstrumentIds, and run
from the repository root:

```bash
aegis-rd/.venv/bin/python -m _prototyping.merger.run_shadow \
  --config /path/to/local-shadow.yaml
```

Each run:

1. resumes after the latest covered filing date, or starts on the last completed UTC date
   when empty (the current partial filing day is collected by the next run);
2. resolves every configured InstrumentId to its SEC CIK through EdgarTools;
3. fetches and locally caches company filings and complete submissions through EdgarTools;
4. rejects filings outside the configured CIK universe before creating an event;
5. appends content-addressed event observations without rewriting history;
6. fetches the latest public FRED `DTB3` cash rate with an immutable offline cache;
7. prices active configured targets through Aegis's catalog-backed IBKR path;
8. forms the unchanged monthly whole-share `q70` decision and reports terminal exits; and
9. writes immutable evidence under the runtime state directory.

The configured InstrumentIds are authoritative. A filing cannot create a tradeable instrument,
and the prototype does not guess a venue, submit an order, or alter a production schema. EdgarTools
owns SEC access, ticker/CIK reference data, fair-access throttling, and its standard `~/.edgar`
cache; the prototype owns merger extraction, lifecycle state, and evidence.

## Behavior checks

The checks intentionally remain outside normal Pytest discovery:

```bash
aegis-rd/.venv/bin/python -m pytest _prototyping/tests/shadow -q
```
