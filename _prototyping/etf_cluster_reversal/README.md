# PROTOTYPE — ETF residual-correlation reversal

## Question

Does a causal OHLCV state model based on frozen market-residual correlation clusters
produce sensible ETF-relative reversal decisions when confronted with an isolated flow
shock, a common bucket move, duplicate wrappers, relationship instability, convergence,
and horizon expiry?

This is a throwaway logic prototype. Its default interactive mode uses deterministic
synthetic data so difficult states can be forced by hand. Its IB mode qualifies and caches
a narrow UCITS-only universe, then prints a static causal state audit. Neither mode
backtests returns, establishes alpha, sends orders, or alters production strategy code.

Run it from the repository root:

```bash
.venv/bin/python -m _prototyping.etf_cluster_reversal
```

With IB Gateway paper trading on port 4002, audit the UCITS universe through the shared
Aegis catalog path:

```bash
.venv/bin/python -m _prototyping.etf_cluster_reversal --ib
```

The real-data universe is intentionally homogeneous at the listing boundary: London Stock
Exchange USD lines of UCITS funds only. CSPX is a non-traded market benchmark; three funds
with different issuers/index constructions represent each of U.S. technology, health care,
and financials. U.S.-listed ETFs, leveraged/inverse funds, ETCs, duplicate currency lines,
and duplicate share classes are absent. UCITS status is curated from official issuer
documents because IB does not supply a reliable UCITS field. Every audit performs fresh
IB qualification even when bars are already cached, then applies account eligibility,
minimum history, a $250,000 median daily dollar-volume floor, and a three-liquid-fund
family gate. The floor is appropriate only to a modest prototype account; historical
spread and depth remain part of later local validation.

The pure state model is in `model.py`; `ib_history.py` owns the IB/catalog boundary;
`universe.py` owns the exact candidate identities; and `__main__.py` is only the terminal
shell. Every synthetic action redraws the complete state: frozen clusters, duplicate
wrappers, cluster stability, residual scores, eligibility, positions, and normalized
peer-hedged targets.

Research note: `aegis-rd/research/vault/notes/causal-correlation-clusters-for-etf-residual-reversal.md`.
