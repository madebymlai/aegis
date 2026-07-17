# PROTOTYPE — mandated-rebalancing alpha falsification (throwaway)

**This is a throwaway logic prototype, not production strategy code.** No tests,
no persistence beyond a wipeable data cache, no integration with the live
allocator. Delete freely once the question is answered.

## The question

> Does the exact long/short stock–Treasury strategy from Harvey, Mazzoleni and
> Melone still exhibit economically usable mandated-rebalancing alpha in recent
> and post-publication data, after correct timing and realistic costs, and does
> its aligned return stream improve the existing slow non-equity trend strategy
> (Atalanta)?

Designed to prove the alpha dead (falsification ladder: reproduction → recency →
implementable economics → Atalanta pairing → prospective decision). Only a
survivor graduates to a paper-trading phase; nothing here allocates capital.

## Run it

```bash
cd aegis-rd
uv run python tmp/prototype_mandated_rebalancing/data.py fetch   # once (idempotent)
uv run python tmp/prototype_mandated_rebalancing/report.py       # the ladder
```

## Layout

- `engine.py` — pure calculation engine (signals, backtests, regression,
  verdicts). Portable; the only piece worth lifting if the idea survives.
- `data.py` — data fetch/cache. IBKR CONTFUT (repository standard) is attempted
  first; Yahoo continuous futures are the labeled fallback while the IBKR
  historical farm rejects requests. `data_cache/` is disposable.
- `atalanta.py` — bridge to the locked Atalanta stream via
  `scripts/floor_evaluation.py` (production reproduction path + the established
  whole-book measure). No fabricated proxy.
- `report.py` — headless one-shot ladder report (user opted out of the TUI).

## Known data caveats (also printed by the report)

- Yahoo continuous futures are unadjusted front-month splices (~4 roll joints
  per year per leg); ES=F/ZN=F start 2000-09, so the paper's 1997-09 start is
  covered by a labeled index/yield proxy extension only.
- MTN (Micro Ultra 10-year) history is proxied by TN (Ultra 10-year) — synthetic
  before the 2025 launches, cannot establish live liquidity or tracking.
- Atalanta's stream is EUR-base production net returns; the candidate is a USD
  futures excess overlay. Same-dates alignment, not a merged-currency book.
