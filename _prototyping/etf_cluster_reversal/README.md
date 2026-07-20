# PROTOTYPE — ETF residual-correlation reversal

## Question

Does a causal OHLCV state model based on frozen market-residual correlation clusters
produce sensible ETF-relative reversal decisions when confronted with an isolated flow
shock, a common bucket move, duplicate wrappers, relationship instability, convergence,
and horizon expiry?

This is a throwaway logic prototype. Its default interactive mode uses deterministic
synthetic data so difficult states can be forced by hand. Its IB mode qualifies and caches
a narrow UCITS-only universe, then prints a static causal state audit. Its backtest mode
runs the same rule through historical daily bars with next-session execution and explicit
costs. No mode sends orders, alters production strategy code, or by itself establishes
alpha.

Run it from the repository root:

```bash
.venv/bin/python -m _prototyping.etf_cluster_reversal
```

With IB Gateway paper trading on port 4002, audit the UCITS universe through the shared
Aegis catalog path:

```bash
.venv/bin/python -m _prototyping.etf_cluster_reversal --ib
```

Run the five-year walk-forward evaluation with a 10-basis-point one-way execution
haircut and a 1% annualized short-borrow haircut:

```bash
.venv/bin/python -m _prototyping.etf_cluster_reversal \
  --backtest --as-of 2026-07-17 --history-years 5 \
  --cost-bps 10 --annual-short-borrow-bps 100
```

The signal uses only data available at a session close. A changed target executes at the
next session's open and earns the subsequent open-to-open return. All target turnover is
charged, the final book is forcibly liquidated, and distributions are assigned only when
the simulated holding spans their ex-date.

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

The corrected five-year evaluation uses a separate 146-session warm-up, point-in-time
60-session liquidity gates, complete peer-family gates, and peer maps frozen for 21
sessions. Its 2021-07-08 through 2026-07-14 signal window produced 1,236 evaluable sessions
and 52 entries. Gross return was +1.02%, but net return at the default costs was -5.87%.
With the same borrow haircut, net total return was only +0.12% at one basis point and
-0.56% at two basis points of one-way execution cost. The roughly 1.2-basis-point
break-even rejects the exact current rule as buildable alpha; the code remains useful as
a falsification harness.

The pure state model is in `model.py`; `ib_history.py` owns the IB/catalog boundary;
`backtest.py` owns walk-forward target and cost accounting; `universe.py` owns the exact
candidate identities; and `__main__.py` is only the terminal shell. Every synthetic action
redraws the complete state: frozen clusters, duplicate wrappers, cluster stability,
residual scores, eligibility, positions, and normalized peer-hedged targets.

Research note: `aegis-rd/research/vault/notes/causal-correlation-clusters-for-etf-residual-reversal.md`.
