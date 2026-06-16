# Backtest costs are modeled in Nautilus; IBKR modes are broker-reported

Status: accepted (`aegis-rd-fuu` backtest cost and financing path implemented; IBKR DU/live wiring remains separate HITL work)

Aegis Trader treats transaction costs as a **backtest simulation concern**. The backtest venue is a local Nautilus simulated exchange, so commissions, slippage, and financing carry must be injected into that exchange. IBKR paper/live modes are real broker connections (`Environment.LIVE`, including DU paper accounts); they do not inject modeled costs because fills, commissions, and cash movements are broker-reported.

## Decision

- **Mode boundary:** modeled costs apply to backtests only. IBKR DU/paper and live use broker-reported execution economics.
- **Book Config owns inert cost parameters.** `BookConfig.costs` is a Nautilus-free domain value loaded from optional `[costs]`, `[costs.margin_interest]`, and `[costs.borrow]` tables in `book.toml`. Omitted tables mean zero modeled cost for that component.
- **Nautilus layer owns executable models.** `trader.costs` builds the per-share commission and seeded fill/slippage models; `trader.financing` builds the financing `SimulationModule`. Domain config remains Nautilus-free per ADR-0003.
- **Commission:** each equity fill pays `max(min_commission_per_order, per_share_commission × shares)`, capped by `max_commission_pct × notional` when the cap is positive. Commission is currency-agnostic and charged in the instrument currency.
- **Slippage:** `slippage_probability` maps to Nautilus one-tick adverse slippage; `slippage_seed` pins deterministic fill paths.
- **Multi-currency account:** the backtest venue uses `base_currency=None`; `book.base_currency` is reporting/NAV currency, not the account currency. Long foreign buys create native-currency cash debits instead of auto-converting from base cash.
- **Financing carry:** one end-of-day `FinancingModule` accrues both:
  - debit interest on negative cash balances using `[costs.margin_interest]` annual per-currency rates; and
  - short borrow fees on open short positions using `[costs.borrow].rate`, charged as `short market value × rate / 360` in the short instrument currency.
- **Retired FX fee fold:** there is no per-trade `fx_conversion_cost`. FX/long carry is modeled as daily debit interest on the native-currency loan. A per-trade fold mismodels buy-and-hold overlays by charging conversion on entry instead of charging the financing cost that grows with holding period.

Together: buy-sell churn pays commission and slippage; long foreign/leverage carry pays margin-loan interest; short carry pays borrow fees.

## Deliberate simplifications

- **Short-sale proceeds credit interest is not modeled.** Omitting it is conservative at this account size.
- **Borrow is flat general-collateral.** `[costs.borrow].rate` is one annual rate. Per-instrument hard-to-borrow overrides and historical borrow-rate feeds are deferred until a real HTB short needs them.

## Determinism

The backtest cost path remains deterministic: same book, market data, FX data, and seeds produce the same fills and the same financing accruals. Financing accrues once per UTC date after venue settlement, reads only end-of-day account balances/positions/marks, and mutates the account through Nautilus `exchange.adjust_account(...)` like Nautilus's built-in rollover module.

## Consequences

- Backtest `run_book_backtest` wires fee/fill models and the financing module from one `CostModelConfig`.
- Zero-cost configs are no-ops: omitted `[costs]`, `[costs.margin_interest]`, and `[costs.borrow]` leave fills and carry cost-free.
- Costed fills surface as Nautilus commissions; financing surfaces as account cash adjustments and performance impact, without a parallel Trader ledger.
- Short-capable backtest bundles require Nautilus margin account semantics for short execution; long-only multi-currency books use cash-with-borrowing semantics to expose native-currency debit balances for interest accrual.
