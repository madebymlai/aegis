# Aegis Trader

Live and backtest execution for Aegis. It takes strategies promoted by
[Aegis RD](../aegis-rd) and trades them against real venues as one **Commingled
Book**.

Each strategy arrives as an **Execution Bundle** (a baked wheel from
`aerd export`). Aegis Trader installs it as a **Sleeve**, sizes every sleeve with
a risk-budgeting **Allocator**, nets them into one target vector, and executes
the deltas. The same `RebalanceStrategy` drives backtest, paper, and live, so a
book validated in research and one traded live take the identical path.

## How a rebalance flows

```
  Execution Bundles (sleeves)                       Commingled Book
  ┌─────────────────────────┐
  │ Floor    trend    ──►    │  signed target weights
  │ Target   tail     ──►    │       │
  │ Expansion m-neutral ──►  │       ▼
  └─────────────────────────┘   ┌──────────┐   net    ┌───────────┐  size   ┌──────┐
                                │ Allocator│ ───────► │ Rebalancer│ ──────► │ IBKR │
   risk shares + vol target ──► │ (risk-   │  one     │ drift     │ order   │ or   │
   Ledoit-Wolf sleeve cov   ──► │  budget) │  vector  │ bands     │ intents │ back-│
                                └──────────┘          └───────────┘         │ test │
                                                                            └──────┘

  Every sleeve gates through aegis-runtime's Exposure Validation before its
  weights leave the bundle; the Roll Desk keeps continuous futures continuous.
```

## Commands

The operator surface is one entrypoint, `aegis-trader`, with two commands. There
is **no** `--mode`: paper versus live is decided only by the gateway port.

- **`aegis-trader backtest --start <YYYY-MM-DD> --end <YYYY-MM-DD>`** runs the
  book offline, end to end, inside Nautilus' `BacktestEngine` against the shared
  catalog. Optional `--book <path>` and `--catalog-path <dir>`.
- **`aegis-trader trader start`** builds the live `TradingNode` and runs it in the
  **foreground** (supervise it with systemd or tmux). Optional `--book <path>`
  and `--pid-file <file>`.
- **`aegis-trader trader stop`** signals a running trader to shut down gracefully
  (SIGTERM to its pidfile).

## The book spec

The book is declared in a version-controlled `book.toml`: the operator statement
of **what** to run. It selects trusted artifacts and parameters only. It is the
live counterpart of Aegis RD's run config, and it never holds secrets.

```toml
base_currency  = "EUR"
book_vol_target = 0.09    # annualized volatility target for risk-budget scaling

gross_cap    = 1.0        # max sum |w_i|
net_cap      = 0.5        # max |sum w_i|
per_name_cap = 0.1        # max |w_i| per instrument

[[sleeves]]
name           = "trend_lse"
wheel_filename = "trend_lse-abc123.whl"   # content-addressed Execution Bundle
risk_share     = 0.6
group          = "Floor"                  # Floor | Target | Expansion
```

Each **Sleeve** binds a name and a **Risk Group** (Floor, Target, or Expansion)
to one content-addressed bundle wheel, with a **Risk Share** of the book's
volatility budget. Instruments carry their own venue as a Nautilus
`InstrumentId` (`{symbol}.{venue}`), so the book never names a single venue. Caps
are checked at load against each bundle's provenance: the book may only tighten
what research validated, never loosen it. See `book.example.toml` for the full
field reference, including drawdown de-lever, drift bands, the tail-convexity
budget, and backtest cost models.

All sleeves in one backtest must share a single bar timeframe. A mixed-timeframe
book is a closed failure, not an implicit resample.

## Broker connection

Paper and live are the same code path pointed at different IBKR gateway ports.
The connection is environment-specific and account-sensitive, so it is read from
the process environment, never from `book.toml`:

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `IB_PORT` | yes | n/a | Gateway port; **this is the paper/live switch** |
| `IB_ACCOUNT_ID` | yes | n/a | IBKR account (e.g. `DU…` paper, `U…` live) |
| `IB_CLIENT_ID` | no | `1` | Nautilus client id |
| `TRADER_ID` | no | `TRADER-001` | Trader identity for the node |

Both required variables fail closed: the trader refuses to guess a gateway or use
a placeholder account. Live and paper are **IBKR-only**.

## Rolls

Continuous futures stay continuous through the **Roll Desk**, the single
authority for the book's live continuous-future exposure. It detects a roll
causally at bar time, when a newer contract overtakes the current front on
observed volume, and re-bases the back-adjusted series across the seam. There is
no roll calendar, so live and research always pick the same front leg.

## See also

- [`CONTEXT.md`](./CONTEXT.md): the glossary for this context
- [Context Map](../CONTEXT-MAP.md): how Aegis Trader relates to RD, Data, and the runtime
- [`aegis-runtime`](../aegis-runtime): the shared execution kernel and Exposure Validation gate
