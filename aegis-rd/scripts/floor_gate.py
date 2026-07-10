"""Floor gate check: does the carry pole earn its pairing with the trend pole?

On-demand port of the P1/P2 scratchpad harness (research/vault/runs/demeter/2026-07-04.md,
sections P1 "monthly gate" and P2 "floor re-verification"). Builds both poles' full-window
daily return streams through the REAL component pipeline (load_run_config ->
load_market_data_result -> currency conversion -> indicators -> strategy ->
simulate_single_book), then reports the recalibrated gate at the floor's horizon.

Semantics settled by those sessions (do not "fix" without re-reading the diary):

- The gate is measured MONTHLY: daily MPPM over-penalizes the single fast-crash day that
  is the tail tier's job, not the floor's. Monthly Theta replicates the allocator metric
  with pp=12 and leg vol = book_vol/sqrt(12) (unit-vol each leg -> scale to book vol ->
  blend (1-w)/w -> NO renormalization of the blend).
- delta_theta is the carry-candidate RANKER, not the floor arbiter. The floor is judged
  on blend-vs-trend-alone Sharpe/maxDD plus full-window correlation (P2 gate
  recalibration). Both views are printed; read them accordingly.
- The full-window monthly delta_theta is fast-crash-limited (the three COVID months flip
  its sign); --exclude-month reproduces that decomposition on demand.
- The carry cell comes from the config's PINNED strategy.params (the re-pinned champion),
  never from a hardcoded cell; vol_target is overridden to the 0.10 mandate because this
  offline path reads manifest defaults, not the collapsed param_space. Extra
  --carry-param overrides let alternative cells be scored (delta_theta ranking on demand).

Run from the aegis-rd repo root:  uv run python scripts/floor_gate.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import pandas as pd
from nautilus_trader.model.identifiers import InstrumentId

from research.aegis_research.component_registry.contracts import ComponentSelection
from research.aegis_research.configuration.resolution import load_run_config
from research.aegis_research.data import load_market_data_result, market_data_bundle
from research.aegis_research.drift_bands import resolve_instrument_bands
from research.aegis_research.metrics.custom.carry import (
    _to_unit_vol,
    composite_allocator_utility,
)
from research.aegis_research.portfolios import fx_adjusted_fees, simulate_single_book
from research.aegis_research.run_pipeline import _to_base_currency

DEFAULT_TREND_CONFIG = REPO_ROOT / "research/configs/atalanta/trend_floor.yaml"
DEFAULT_CARRY_CONFIG = REPO_ROOT / "research/configs/demeter/carry_floor.yaml"
MONTHS_PER_YEAR = 12.0
CORR_GATE = 0.10


class _StrategyInputs:
    """Minimal stand-in for the framework's strategy `inputs` object."""

    def __init__(self, data, indicators, n_candidates, n_symbols):
        self.data = data
        self.indicators = indicators
        self.n_candidates = n_candidates
        self.n_symbols = n_symbols
        self.metadata: dict = {}


def build_pole_returns(config_path: Path, *, strategy_param_overrides: dict | None = None) -> pd.Series:
    """One pole's daily return stream through the real component pipeline."""
    resolved = load_run_config(config_path)
    config = resolved.config
    registry = resolved.component_registry
    assert registry is not None

    data_result = load_market_data_result(config.data)
    data_result.assert_usable()
    bundle = _to_base_currency(data_result, data_bundle=market_data_bundle(data_result))
    close = bundle.array("Close")
    symbols = list(close.columns)
    n_symbols = len(symbols)

    indicator_outputs: dict[str, np.ndarray] = {}
    for ind_cfg in config.indicators:
        definition = registry.get(ComponentSelection("indicators", ind_cfg.id))
        run_fn = definition.load_callable()
        params = definition.default_params()
        params.update(ind_cfg.params)
        out = run_fn(bundle, n_candidates=1, **{k: [v] for k, v in params.items()})
        for name, arr in out.items():
            arr = np.asarray(arr)
            if arr.shape != (len(close), n_symbols):
                raise ValueError(
                    f"indicator {ind_cfg.id} output {name!r} shape {arr.shape} != {(len(close), n_symbols)}"
                )
            indicator_outputs[name] = arr

    strategy_def = registry.get(ComponentSelection("strategies", config.strategy.id))
    strategy_params = strategy_def.default_params()
    strategy_params.update(config.strategy.params)
    if strategy_param_overrides:
        strategy_params.update(strategy_param_overrides)
    inputs = _StrategyInputs(
        data=bundle, indicators=indicator_outputs, n_candidates=1, n_symbols=n_symbols
    )
    weights = np.asarray(
        strategy_def.load_callable()(
            inputs, n_candidates=1, **{k: [v] for k, v in strategy_params.items()}
        )
    )
    if weights.shape != (len(close), n_symbols):
        raise ValueError(
            f"strategy {config.strategy.id} output shape {weights.shape} != {(len(close), n_symbols)}"
        )
    allocations = pd.DataFrame(weights, index=close.index, columns=symbols)

    instrument_ids = tuple(InstrumentId.from_str(v) for v in config.data.instruments)
    currency_conversion = data_result.currency_conversion
    currency_by_instrument_id = (
        currency_conversion.currency_by_instrument_id
        if currency_conversion is not None
        else dict.fromkeys(instrument_ids, config.portfolio.base_currency)
    )
    fees_by_symbol = fx_adjusted_fees(
        instrument_ids,
        currency_by_instrument_id,
        config.portfolio.base_currency,
        base_fee=config.portfolio.fees,
        fx_conversion_cost=config.portfolio.fx_conversion_cost,
    )
    pf = simulate_single_book(
        close,
        allocations,
        config.portfolio,
        market_index=close.index,
        periods_per_year=252,
        fees_by_symbol=fees_by_symbol,
        instrument_bands=resolve_instrument_bands(config),
        distributions=data_result.distributions,
        currency_conversion=currency_conversion,
    )
    value = pf.get_value()
    if isinstance(value, pd.DataFrame):
        value = value.iloc[:, 0]
    returns = value.pct_change().dropna()
    returns.index = pd.DatetimeIndex(returns.index).tz_localize(None).normalize()
    return returns


# ── the monthly allocator metric (P1 replication: pp=12, no blend renormalize) ──────


def theta(x: np.ndarray, *, pp: float, rho: float) -> float:
    growth = 1.0 + x
    if np.any(growth <= 0):
        return float("-inf")
    return pp / (1.0 - rho) * float(np.log(np.mean(growth ** (1.0 - rho))))


def blend(carry: np.ndarray, trend: np.ndarray, *, pp: float, w: float, book_vol: float) -> np.ndarray:
    leg_vol = book_vol / np.sqrt(pp)
    return (1.0 - w) * (_to_unit_vol(trend) * leg_vol) + w * (_to_unit_vol(carry) * leg_vol)


def delta_theta(carry: np.ndarray, trend: np.ndarray, *, pp: float, w: float, rho: float, book_vol: float) -> float:
    trend_alone = _to_unit_vol(trend) * (book_vol / np.sqrt(pp))
    return theta(blend(carry, trend, pp=pp, w=w, book_vol=book_vol), pp=pp, rho=rho) - theta(
        trend_alone, pp=pp, rho=rho
    )


def perf(x: np.ndarray, pp: float) -> str:
    ann_ret = (1.0 + x).prod() ** (pp / len(x)) - 1.0
    ann_vol = x.std() * np.sqrt(pp)
    equity = (1.0 + x).cumprod()
    mdd = (equity / np.maximum.accumulate(equity) - 1.0).min()
    sh = ann_ret / ann_vol if ann_vol else np.nan
    return f"ann_ret {ann_ret:+.2%}  vol {ann_vol:.2%}  Sharpe {sh:+.2f}  maxDD {mdd:+.2%}"


def monthly(returns: pd.Series) -> pd.Series:
    return (1.0 + returns).resample("ME").prod() - 1.0


def parse_overrides(pairs: list[str]) -> dict:
    overrides = {}
    for pair in pairs:
        key, _, raw = pair.partition("=")
        if not _:
            raise SystemExit(f"--carry-param needs key=value, got {pair!r}")
        try:
            overrides[key] = float(raw)
        except ValueError:
            overrides[key] = raw
    return overrides


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trend-config", type=Path, default=DEFAULT_TREND_CONFIG)
    parser.add_argument("--carry-config", type=Path, default=DEFAULT_CARRY_CONFIG)
    parser.add_argument(
        "--carry-param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="strategy param override for the carry pole (repeatable); "
        "vol_target=0.10 is always applied first (the mandate)",
    )
    parser.add_argument("--weight", type=float, default=0.40, help="carry blend weight w (default 0.40)")
    parser.add_argument("--rho", type=float, default=3.0, help="CRRA risk aversion (default 3)")
    parser.add_argument("--book-vol", type=float, default=0.10, help="per-leg annual vol pin (default 0.10)")
    parser.add_argument(
        "--exclude-month",
        action="append",
        default=[],
        metavar="YYYY-MM",
        help="drop these months from a second gate read (repeatable); "
        "e.g. 2020-02 2020-03 2020-04 reproduces the P1 fast-crash decomposition",
    )
    args = parser.parse_args()

    carry_overrides = {"vol_target": 0.10}
    carry_overrides.update(parse_overrides(args.carry_param))

    print(f"building trend pole: {args.trend_config.relative_to(REPO_ROOT)}")
    trend = build_pole_returns(args.trend_config)
    print(f"building carry pole: {args.carry_config.relative_to(REPO_ROOT)}  overrides={carry_overrides}")
    carry = build_pole_returns(args.carry_config, strategy_param_overrides=carry_overrides)

    idx = trend.index.intersection(carry.index)
    trend_daily, carry_daily = trend.reindex(idx), carry.reindex(idx)
    trend_monthly, carry_monthly = monthly(trend_daily), monthly(carry_daily)
    month_idx = trend_monthly.index.intersection(carry_monthly.index)
    trend_monthly, carry_monthly = trend_monthly.reindex(month_idx), carry_monthly.reindex(month_idx)
    print(f"aligned: {idx.min().date()} .. {idx.max().date()}  ({len(idx)} days, {len(month_idx)} months)\n")

    kwargs = dict(w=args.weight, rho=args.rho, book_vol=args.book_vol)
    dt_monthly = delta_theta(carry_monthly.to_numpy(), trend_monthly.to_numpy(), pp=MONTHS_PER_YEAR, **kwargs)
    corr_monthly = float(np.corrcoef(carry_monthly, trend_monthly)[0, 1])
    dt_daily = composite_allocator_utility(
        carry_daily.to_numpy(), trend_daily.to_numpy(),
        carry_weight=args.weight, rho=args.rho, book_vol_annual=args.book_vol,
    )

    print(f"=== the gate at the floor's horizon (monthly, w={args.weight}, rho={args.rho}) ===")
    print(f"monthly delta_theta {dt_monthly:+.4f}   ({'PASS' if dt_monthly > 0 else 'FAIL'})")
    print(f"monthly |corr|      {abs(corr_monthly):.4f}    ({'PASS' if abs(corr_monthly) < CORR_GATE else 'FAIL'} vs < {CORR_GATE})")
    print(f"daily delta_theta   {dt_daily:+.4f}   (reference; over-penalizes the fast crash)")

    if args.exclude_month:
        keep = ~month_idx.strftime("%Y-%m").isin(args.exclude_month)
        dt_ex = delta_theta(
            carry_monthly[keep].to_numpy(), trend_monthly[keep].to_numpy(), pp=MONTHS_PER_YEAR, **kwargs
        )
        corr_ex = float(np.corrcoef(carry_monthly[keep], trend_monthly[keep])[0, 1])
        print(f"\n=== excluding {sorted(args.exclude_month)} ({int((~keep).sum())} months dropped) ===")
        print(f"monthly delta_theta {dt_ex:+.4f}   monthly |corr| {abs(corr_ex):.4f}")

    print(f"\n=== the floor arbiter: blend vs trend-alone (P2 recalibration; daily, legs at {args.book_vol:.0%} vol) ===")
    trend_leg = _to_unit_vol(trend_daily.to_numpy()) * (args.book_vol / np.sqrt(252.0))
    book = blend(carry_daily.to_numpy(), trend_daily.to_numpy(), pp=252.0, w=args.weight, book_vol=args.book_vol)
    print(f"trend-alone:  {perf(trend_leg, 252.0)}")
    print(f"trend+carry:  {perf(book, 252.0)}")
    print("\nRead: delta_theta RANKS carry candidates; the floor is judged on the arbiter block")
    print("plus full-window correlation. See runs/demeter/2026-07-04 (P1/P2) for the calibration.")


if __name__ == "__main__":
    main()
