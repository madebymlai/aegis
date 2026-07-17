"""PROTOTYPE (throwaway) — pure calculation engine for the mandated-rebalancing
falsification test.

QUESTION UNDER TEST: Does the exact long/short stock-Treasury strategy from
Harvey, Mazzoleni and Melone ("The Unintended Consequences of Rebalancing",
SSRN 5122748) still exhibit economically usable mandated-rebalancing alpha in
recent and post-publication data, after correct timing and realistic costs, and
does its aligned return stream improve the existing slow non-equity trend
strategy (Atalanta)?

Pure module: plain numpy/pandas in, plain dataclasses out. No I/O, no terminal
code. The TUI and data loaders import this; nothing flows the other way.

Signal construction (paper via Daniel discussion slides + the QuantReturns /
Quantitativo replications):
  * Threshold signal_t = mean over delta in {0.0%,0.1%,...,2.5%} of
    (w_t^delta - 60%), where w tracks a 60/40 stock/bond portfolio and resets
    to 60% whenever |w - 60%| >= delta.
  * Calendar signal_t = (w_t - 60%) where w resets to 60% at the close of the
    last business day of each month.
  * Modified threshold = -threshold / 0.012  (invert: front-run the flow;
    0.012 is the replication's fixed normalization constant, not fitted here).
  * Modified calendar: on the 4 sessions before the month's last session,
    -sign(calendar); on the last session, +sign(calendar at the window start)
    (the documented month-end reversal capture); 0 elsewhere.
  * Combined = mean of the two modified signals.
  * Strategy return over t -> t+1 = w_t * (R_stock_{t+1} - R_bond_{t+1}).
    Weight uses information through close t ONLY (look-ahead guarded).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252.0
THRESHOLD_DELTAS = np.arange(0.0, 0.0251, 0.001)
THRESHOLD_NORMALIZATION = 0.012
CALENDAR_WINDOW = 5  # sessions: 4 pressure days + last-day reversal
WEIGHT_CAP = 2.0


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


def tracked_weight(
    stock: np.ndarray, bond: np.ndarray, reset: np.ndarray | float
) -> np.ndarray:
    """Evolve a 60/40 stock weight through daily returns.

    ``reset`` is either a boolean mask (reset AFTER the close of day t) or a
    float drift threshold (reset when |w - 60%| >= threshold, checked after
    each update). Returns the weight observed at each close, before any reset
    applies to the next day.
    """
    w = np.empty(len(stock))
    current = 0.60
    threshold = reset if isinstance(reset, float) else None
    mask = reset if isinstance(reset, np.ndarray) else None
    for t in range(len(stock)):
        grown_stock = current * (1.0 + stock[t])
        grown_total = grown_stock + (1.0 - current) * (1.0 + bond[t])
        current = 0.60 if grown_total <= 0 else grown_stock / grown_total
        w[t] = current
        if threshold is not None and abs(current - 0.60) >= threshold:
            current = 0.60
        elif mask is not None and mask[t]:
            current = 0.60
    return w


def threshold_signal(stock: np.ndarray, bond: np.ndarray) -> np.ndarray:
    """Mean 60/40 drift across the paper's delta grid (0 .. 2.5% by 0.1%)."""
    drifts = [
        tracked_weight(stock, bond, float(delta)) - 0.60 for delta in THRESHOLD_DELTAS
    ]
    return np.mean(drifts, axis=0)


def month_end_mask(dates: pd.DatetimeIndex) -> np.ndarray:
    """True on each month's last trading session in the sample."""
    period = dates.to_period("M")
    mask = np.zeros(len(dates), dtype=bool)
    mask[:-1] = period[:-1] != period[1:]
    mask[-1] = True
    return mask


def calendar_signal(
    dates: pd.DatetimeIndex, stock: np.ndarray, bond: np.ndarray
) -> np.ndarray:
    """60/40 drift since the previous month-end close."""
    return tracked_weight(stock, bond, month_end_mask(dates)) - 0.60


def sessions_to_month_end(dates: pd.DatetimeIndex) -> np.ndarray:
    """0 on the month's last session, 1 the session before, etc."""
    period = dates.to_period("M")
    out = np.zeros(len(dates), dtype=int)
    count = 0
    for t in range(len(dates) - 2, -1, -1):
        count = 0 if period[t] != period[t + 1] else count + 1
        out[t] = count
    return out


def modified_calendar(
    dates: pd.DatetimeIndex, cal_signal: np.ndarray
) -> np.ndarray:
    """+-1 pressure position in the pre-month-end window, reversed on the last day."""
    to_end = sessions_to_month_end(dates)
    out = np.zeros(len(cal_signal))
    pressure = (to_end >= 1) & (to_end <= CALENDAR_WINDOW - 1)
    out[pressure] = -np.sign(cal_signal[pressure])
    window_start = to_end == CALENDAR_WINDOW - 1
    start_value = pd.Series(np.where(window_start, out, np.nan)).ffill().to_numpy()
    last = to_end == 0
    out[last] = -start_value[last]
    return np.nan_to_num(out)


@dataclass(frozen=True)
class SignalSet:
    threshold: np.ndarray  # raw drift, for regressions
    calendar: np.ndarray  # raw drift, for regressions
    weight_threshold: np.ndarray  # modified (tradeable) weights
    weight_calendar: np.ndarray
    weight_combined: np.ndarray


def build_signals(
    dates: pd.DatetimeIndex, stock: np.ndarray, bond: np.ndarray
) -> SignalSet:
    thr = threshold_signal(stock, bond)
    cal = calendar_signal(dates, stock, bond)
    w_thr = np.clip(-thr / THRESHOLD_NORMALIZATION, -WEIGHT_CAP, WEIGHT_CAP)
    w_cal = modified_calendar(dates, cal)
    return SignalSet(
        threshold=thr,
        calendar=cal,
        weight_threshold=w_thr,
        weight_calendar=w_cal,
        weight_combined=0.5 * (w_thr + w_cal),
    )


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CostModel:
    """Per-leg one-way cost in bp of traded notional, plus annual financing drag
    applied to gross exposure (0 for self-financing futures spreads)."""

    label: str
    stock_bp: float
    bond_bp: float
    financing_annual: float = 0.0


GROSS = CostModel(label="gross", stock_bp=0.0, bond_bp=0.0)
# ES half-spread ~0.2bp + commission ~0.2bp; ZN half-spread ~0.7bp + commission.
FUTURES_REALISTIC = CostModel(label="futures realistic", stock_bp=0.5, bond_bp=1.0)
# Micro/spot-quoted contracts: wider effective spread + relatively larger fees.
MICRO_REALISTIC = CostModel(label="micro realistic", stock_bp=1.5, bond_bp=2.0)


@dataclass(frozen=True)
class BacktestResult:
    dates: pd.DatetimeIndex  # dates of realized daily strategy returns
    returns: np.ndarray  # net daily strategy returns
    gross_returns: np.ndarray
    weights: np.ndarray  # weight in force for each realized return
    observations: int
    cagr: float
    volatility: float
    sharpe: float
    skew: float
    max_drawdown: float
    annual_turnover: float  # sum(|dw|)*2 legs, annualized, in spread notional
    annual_cost_drag: float

    def series(self) -> pd.Series:
        return pd.Series(self.returns, index=self.dates)


def run_backtest(
    dates: pd.DatetimeIndex,
    stock: np.ndarray,
    bond: np.ndarray,
    weights: np.ndarray,
    costs: CostModel,
    delay: int = 0,
) -> BacktestResult:
    """Weight from close t earns the t->t+1 spread return (delay adds sessions).

    The shift is the look-ahead guard: ``held[k]`` for the return realized on
    day k uses information through close k-1-delay only.
    """
    spread = stock - bond
    lag = 1 + delay
    held = np.concatenate([np.zeros(lag), weights[: len(weights) - lag]])
    gross = held * spread
    traded = np.abs(np.diff(np.concatenate([[0.0], held])))
    cost = traded * (costs.stock_bp + costs.bond_bp) / 10_000.0
    cost = cost + np.abs(held) * costs.financing_annual / TRADING_DAYS
    net = gross - cost
    # First `lag` observations carry no position; keep them (zero return) so
    # window boundaries stay aligned across delay settings.
    equity = np.cumprod(1.0 + net)
    drawdown = equity / np.maximum.accumulate(equity) - 1.0
    volatility = float(np.std(net, ddof=1) * math.sqrt(TRADING_DAYS))
    mean = float(np.mean(net))
    years = len(net) / TRADING_DAYS
    return BacktestResult(
        dates=dates,
        returns=net,
        gross_returns=gross,
        weights=held,
        observations=len(net),
        cagr=float(equity[-1] ** (1.0 / years) - 1.0) if years > 0 else 0.0,
        volatility=volatility,
        sharpe=float(mean / np.std(net, ddof=1) * math.sqrt(TRADING_DAYS))
        if np.std(net, ddof=1) > 0
        else 0.0,
        skew=float(pd.Series(net).skew()),
        max_drawdown=float(np.min(drawdown)),
        annual_turnover=float(np.sum(traded) * 2.0 / years) if years > 0 else 0.0,
        annual_cost_drag=float(np.sum(cost) / years) if years > 0 else 0.0,
    )


def long_only_control_weights(
    dates: pd.DatetimeIndex, stock: np.ndarray, bond: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """The practitioner long-only negative control (Valuelytica-style rule).

    At each close in the pre-month-end window, long ONLY the month-to-date
    loser of the pair; flat otherwise. No short leg, no reversal capture.
    """
    to_end = sessions_to_month_end(dates)
    period = dates.to_period("M")
    month_start = np.concatenate([[True], (period[1:] != period[:-1])])
    stock_mtd = np.empty(len(stock))
    bond_mtd = np.empty(len(bond))
    growth_stock = 1.0
    growth_bond = 1.0
    for t in range(len(stock)):
        if month_start[t]:
            growth_stock = 1.0
            growth_bond = 1.0
        growth_stock *= 1.0 + stock[t]
        growth_bond *= 1.0 + bond[t]
        stock_mtd[t] = growth_stock
        bond_mtd[t] = growth_bond
    active = (to_end >= 1) & (to_end <= CALENDAR_WINDOW - 1)
    w_stock = np.where(active & (stock_mtd < bond_mtd), 1.0, 0.0)
    w_bond = np.where(active & (bond_mtd <= stock_mtd), 1.0, 0.0)
    return w_stock, w_bond


def run_two_leg_backtest(
    dates: pd.DatetimeIndex,
    stock: np.ndarray,
    bond: np.ndarray,
    stock_weights: np.ndarray,
    bond_weights: np.ndarray,
    costs: CostModel,
    delay: int = 0,
) -> BacktestResult:
    """Per-leg weights (both signed long) with the same look-ahead guard."""
    lag = 1 + delay
    held_stock = np.concatenate([np.zeros(lag), stock_weights[: len(stock_weights) - lag]])
    held_bond = np.concatenate([np.zeros(lag), bond_weights[: len(bond_weights) - lag]])
    gross = held_stock * stock + held_bond * bond
    traded_stock = np.abs(np.diff(np.concatenate([[0.0], held_stock])))
    traded_bond = np.abs(np.diff(np.concatenate([[0.0], held_bond])))
    cost = (traded_stock * costs.stock_bp + traded_bond * costs.bond_bp) / 10_000.0
    net = gross - cost
    equity = np.cumprod(1.0 + net)
    drawdown = equity / np.maximum.accumulate(equity) - 1.0
    years = len(net) / TRADING_DAYS
    return BacktestResult(
        dates=dates,
        returns=net,
        gross_returns=gross,
        weights=held_stock - held_bond,
        observations=len(net),
        cagr=float(equity[-1] ** (1.0 / years) - 1.0) if years > 0 else 0.0,
        volatility=float(np.std(net, ddof=1) * math.sqrt(TRADING_DAYS)),
        sharpe=float(np.mean(net) / np.std(net, ddof=1) * math.sqrt(TRADING_DAYS))
        if np.std(net, ddof=1) > 0
        else 0.0,
        skew=float(pd.Series(net).skew()),
        max_drawdown=float(np.min(drawdown)),
        annual_turnover=float(np.sum(traded_stock + traded_bond) / years)
        if years > 0
        else 0.0,
        annual_cost_drag=float(np.sum(cost) / years) if years > 0 else 0.0,
    )


@dataclass(frozen=True)
class IntegerContractResult:
    backtest: BacktestResult
    mean_stock_contracts: float
    mean_bond_contracts: float
    max_gross_leverage: float
    tracking_error_vs_spread: float  # ann. vol of (integer - research) returns


def run_integer_contract_backtest(
    dates: pd.DatetimeIndex,
    stock: np.ndarray,
    bond: np.ndarray,
    weights: np.ndarray,
    stock_notional: np.ndarray,
    bond_notional: np.ndarray,
    sleeve_usd: float,
    commission_per_contract: float = 1.0,
    costs: CostModel = MICRO_REALISTIC,
    delay: int = 0,
) -> IntegerContractResult:
    """Integer QSPX / MTN contracts targeting +-w * sleeve notional per leg.

    Margin is NOT treated as exposure: leg weights are contract notional over
    sleeve equity, so leverage and quantization error are explicit.
    """
    lag = 1 + delay
    held = np.concatenate([np.zeros(lag), weights[: len(weights) - lag]])
    stock_px = np.concatenate([stock_notional[:lag], stock_notional[: len(held) - lag]])
    bond_px = np.concatenate([bond_notional[:lag], bond_notional[: len(held) - lag]])
    stock_contracts = np.round(held * sleeve_usd / stock_px)
    bond_contracts = np.round(held * sleeve_usd / bond_px)
    stock_weight = stock_contracts * stock_px / sleeve_usd
    bond_weight = bond_contracts * bond_px / sleeve_usd
    gross = stock_weight * stock - bond_weight * bond
    traded_stock = np.abs(np.diff(np.concatenate([[0.0], stock_contracts])))
    traded_bond = np.abs(np.diff(np.concatenate([[0.0], bond_contracts])))
    commission = (traded_stock + traded_bond) * commission_per_contract / sleeve_usd
    spread_cost = (
        traded_stock * stock_px * costs.stock_bp
        + traded_bond * bond_px * costs.bond_bp
    ) / 10_000.0 / sleeve_usd
    net = gross - commission - spread_cost
    equity = np.cumprod(1.0 + net)
    drawdown = equity / np.maximum.accumulate(equity) - 1.0
    years = len(net) / TRADING_DAYS
    research = held * (stock - bond)
    backtest = BacktestResult(
        dates=dates,
        returns=net,
        gross_returns=gross,
        weights=stock_weight,
        observations=len(net),
        cagr=float(equity[-1] ** (1.0 / years) - 1.0) if years > 0 else 0.0,
        volatility=float(np.std(net, ddof=1) * math.sqrt(TRADING_DAYS)),
        sharpe=float(np.mean(net) / np.std(net, ddof=1) * math.sqrt(TRADING_DAYS))
        if np.std(net, ddof=1) > 0
        else 0.0,
        skew=float(pd.Series(net).skew()),
        max_drawdown=float(np.min(drawdown)),
        annual_turnover=float(
            np.sum(traded_stock * stock_px + traded_bond * bond_px)
            / sleeve_usd
            / years
        )
        if years > 0
        else 0.0,
        annual_cost_drag=float(np.sum(commission + spread_cost) / years)
        if years > 0
        else 0.0,
    )
    return IntegerContractResult(
        backtest=backtest,
        mean_stock_contracts=float(np.mean(np.abs(stock_contracts))),
        mean_bond_contracts=float(np.mean(np.abs(bond_contracts))),
        max_gross_leverage=float(np.max(np.abs(stock_weight) + np.abs(bond_weight))),
        tracking_error_vs_spread=float(
            np.std(net - research, ddof=1) * math.sqrt(TRADING_DAYS)
        ),
    )


# ---------------------------------------------------------------------------
# Predictive regression (the paper's correctness object)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegressionResult:
    observations: int
    beta: float  # raw OLS slope
    bp_per_sd: float  # next-day spread move per 1-sd signal, in bp
    t_stat: float  # Newey-West (5 lags)
    signal_sd: float


def predictive_regression(
    signal: np.ndarray, spread_next: np.ndarray, lags: int = 5
) -> RegressionResult:
    """OLS of next-day spread return on the signal, Newey-West t-stat.

    The paper's finding: equity-overweight signal predicts a NEGATIVE next-day
    stock-bond spread (about -17bp equity / +2..4bp bond per 1 sd, t ~ 4).
    """
    x = signal[:-1]
    y = spread_next[1:]
    keep = ~(np.isnan(x) | np.isnan(y))
    x, y = x[keep], y[keep]
    n = len(x)
    if n < 30 or np.std(x) == 0:
        return RegressionResult(n, math.nan, math.nan, math.nan, float(np.std(x)))
    design = np.column_stack([np.ones(n), x])
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    residuals = y - design @ coef
    xtx_inv = np.linalg.inv(design.T @ design)
    scores = design * residuals[:, None]
    omega = scores.T @ scores
    for lag in range(1, lags + 1):
        weight_lag = 1.0 - lag / (lags + 1.0)
        gamma = scores[lag:].T @ scores[:-lag]
        omega += weight_lag * (gamma + gamma.T)
    covariance = xtx_inv @ omega @ xtx_inv
    beta = float(coef[1])
    se = float(math.sqrt(max(covariance[1, 1], 1e-30)))
    sd = float(np.std(x))
    return RegressionResult(
        observations=n,
        beta=beta,
        bp_per_sd=beta * sd * 10_000.0,
        t_stat=beta / se,
        signal_sd=sd,
    )


# ---------------------------------------------------------------------------
# Falsification verdicts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageVerdict:
    stage: str
    passed: bool | None  # None = not decidable from available data
    detail: str


def stage1_reproduction(
    regression: RegressionResult, backtest: BacktestResult
) -> StageVerdict:
    """Gate: sign + strength of the predictive relation, and strategy shape."""
    if math.isnan(regression.t_stat):
        return StageVerdict("1 reproduction", None, "insufficient observations")
    sign_ok = regression.beta < 0
    strength_ok = regression.t_stat <= -3.0
    sharpe_ok = backtest.sharpe >= 0.7
    passed = sign_ok and strength_ok and sharpe_ok
    detail = (
        f"beta sign {'OK' if sign_ok else 'WRONG'} "
        f"({regression.bp_per_sd:+.1f}bp/sd, t={regression.t_stat:.2f} "
        f"{'<=' if strength_ok else '>'} -3), "
        f"Sharpe {backtest.sharpe:.2f} {'>=' if sharpe_ok else '<'} 0.7 "
        f"(paper ~1, replications 0.94/1.24)"
    )
    return StageVerdict("1 reproduction", passed, detail)


def stage2_recency(
    recent: RegressionResult, recent_backtest: BacktestResult
) -> StageVerdict:
    if math.isnan(recent.t_stat):
        return StageVerdict("2 recency", None, "recent window too short to estimate")
    sign_holds = recent.beta < 0
    economically_alive = recent_backtest.sharpe > 0.0
    passed = sign_holds and economically_alive
    if not sign_holds:
        state = "response sign FLIPPED"
    elif not economically_alive:
        state = "sign retained but economically dead in the recent window"
    else:
        state = "response alive"
    detail = (
        f"recent beta {recent.bp_per_sd:+.1f}bp/sd (t={recent.t_stat:.2f}), "
        f"Sharpe {recent_backtest.sharpe:.2f}; {state}"
    )
    return StageVerdict("2 recency", passed, detail)


def stage3_implementable(net: BacktestResult) -> StageVerdict:
    survives = net.sharpe >= 0.5
    detail = (
        f"net Sharpe {net.sharpe:.2f} (gate 0.5, H1), cost drag "
        f"{net.annual_cost_drag * 100:.2f}%/yr on turnover {net.annual_turnover:.1f}x/yr"
    )
    return StageVerdict("3 implementable", survives, detail)


def stage4_pairing(
    ce_delta: float | None, worst_decile_mean: float | None
) -> StageVerdict:
    if ce_delta is None or worst_decile_mean is None:
        return StageVerdict("4 pairing", None, "Atalanta stream unavailable")
    passed = ce_delta > 0 and worst_decile_mean >= 0
    detail = (
        f"MPPM CE delta {ce_delta:+.4f}, candidate mean in Atalanta worst-decile "
        f"months {worst_decile_mean:+.4f}"
    )
    return StageVerdict("4 pairing", passed, detail)


def final_decision(verdicts: list[StageVerdict]) -> str:
    for verdict in verdicts:
        if verdict.passed is False:
            failures = {
                "1 reproduction": "DEAD/REJECT - reproduction fails (pending reconciliation)",
                "2 recency": "DEAD/REJECT - alpha likely decayed; do not proceed",
                "3 implementable": "DEAD/REJECT - not implementable for this book",
                "4 pairing": "DEAD/REJECT - real strategy, wrong roster seat",
            }
            return failures[verdict.stage]
    if any(verdict.passed is None for verdict in verdicts):
        missing = ", ".join(v.stage for v in verdicts if v.passed is None)
        return f"INCONCLUSIVE - undecidable stages: {missing}"
    return "SURVIVES FOR PAPER TRADING - freeze rule + decay monitor; do not allocate"
