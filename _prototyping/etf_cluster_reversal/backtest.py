"""Causal walk-forward evaluation for the UCITS ETF reversal prototype."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from .model import (
    MIN_CLUSTER_SIZE,
    MINIMUM_HISTORY_SESSIONS,
    MONTHLY_SNAPSHOT_DAYS,
    ClusterSnapshot,
    Position,
    PrototypeState,
    rebalance_historical_state,
    state_from_history,
)

TRADING_DAYS_PER_YEAR = 252
BASIS_POINTS_PER_UNIT = 10_000.0


class BacktestFailure(ValueError):
    """A named failure prevents a valid backtest result."""


class BacktestCostInvalid(BacktestFailure):
    """A cost assumption is outside its valid domain."""


class SignalHistoryInsufficient(BacktestFailure):
    """The signal history is too short for one causal estimate."""


class ExecutionHistoryInvalid(BacktestFailure):
    """The execution panel does not match the signal panel."""


class HistoricalEligibilityInvalid(BacktestFailure):
    """The point-in-time eligibility contract is internally inconsistent."""


class BacktestStatisticsUndefined(BacktestFailure):
    """The return path cannot produce meaningful summary statistics."""


@dataclass(frozen=True)
class BacktestConfig:
    transaction_cost_bps: float = 10.0
    annual_short_borrow_bps: float = 100.0

    def __post_init__(self) -> None:
        if self.transaction_cost_bps < 0.0:
            raise BacktestCostInvalid("transaction cost cannot be negative")
        if self.annual_short_borrow_bps < 0.0:
            raise BacktestCostInvalid("short borrow cost cannot be negative")


@dataclass(frozen=True)
class UndefinedStatistic:
    reason: str


@dataclass(frozen=True)
class HistoricalEligibility:
    """Point-in-time liquidity and peer-family membership for candidate ETFs."""

    dollar_volumes: pd.DataFrame
    family_by_ticker: dict[str, str]
    minimum_median_dollar_volume: float
    liquidity_lookback_sessions: int = 60

    def __post_init__(self) -> None:
        if self.minimum_median_dollar_volume < 0.0:
            raise HistoricalEligibilityInvalid(
                "minimum dollar volume cannot be negative"
            )
        if self.liquidity_lookback_sessions < 1:
            raise HistoricalEligibilityInvalid("liquidity lookback must be positive")
        missing = set(self.dollar_volumes.columns) - set(self.family_by_ticker)
        if missing:
            raise HistoricalEligibilityInvalid(
                f"peer families missing for: {', '.join(sorted(missing))}"
            )
        if not self.dollar_volumes.index.is_monotonic_increasing:
            raise HistoricalEligibilityInvalid("eligibility dates are not ordered")
        if not self.dollar_volumes.index.is_unique:
            raise HistoricalEligibilityInvalid("eligibility dates are not unique")
        values = self.dollar_volumes.to_numpy()
        if not np.isfinite(values).all() or (values < 0.0).any():
            raise HistoricalEligibilityInvalid(
                "dollar volumes must be finite and nonnegative"
            )

    def eligible_tickers(self, formation_date: pd.Timestamp) -> tuple[str, ...]:
        trailing = self.dollar_volumes.loc[:formation_date].tail(
            self.liquidity_lookback_sessions
        )
        if len(trailing) < self.liquidity_lookback_sessions:
            return ()
        medians = trailing.median()
        liquid = {
            ticker
            for ticker, value in medians.items()
            if float(value) >= self.minimum_median_dollar_volume
        }
        family_counts: dict[str, int] = {}
        for ticker in liquid:
            family = self.family_by_ticker[ticker]
            family_counts[family] = family_counts.get(family, 0) + 1
        return tuple(
            ticker
            for ticker in self.dollar_volumes.columns
            if ticker in liquid
            and family_counts[self.family_by_ticker[ticker]] >= MIN_CLUSTER_SIZE
        )


@dataclass(frozen=True)
class SignalPath:
    targets: pd.DataFrame
    entries: int
    exits: int


@dataclass(frozen=True)
class BacktestResult:
    daily: pd.DataFrame
    targets: pd.DataFrame
    entries: int
    exits: int
    exposure_days: int
    turnover: float
    gross_total_return: float
    net_total_return: float
    annualized_net_return: float
    annualized_volatility: float
    sharpe: float | UndefinedStatistic
    maximum_drawdown: float
    transaction_cost_drag: float
    borrow_cost_drag: float


def run_backtest(
    state: PrototypeState,
    execution_returns: pd.DataFrame,
    eligibility: HistoricalEligibility,
    config: BacktestConfig = BacktestConfig(),
) -> BacktestResult:
    """Generate causal targets and evaluate next-session open executions."""

    _validate_execution_returns(state, execution_returns)
    complete_execution = execution_returns.dropna()
    if complete_execution.empty:
        raise ExecutionHistoryInvalid(
            "execution history has no complete forward sessions"
        )
    last_signal_date = complete_execution.index[-1]
    signal_state = _state_through(state, last_signal_date)
    signal_path = walk_forward_targets(signal_state, eligibility)
    daily = evaluate_target_path(
        signal_path.targets,
        complete_execution,
        config,
    )
    return _result(signal_path, daily)


def walk_forward_targets(
    state: PrototypeState, eligibility: HistoricalEligibility
) -> SignalPath:
    """Rebuild each signal using only observations available at that close."""

    if len(state.returns) < MINIMUM_HISTORY_SESSIONS:
        raise SignalHistoryInsufficient(
            f"signal history needs at least {MINIMUM_HISTORY_SESSIONS} sessions"
        )
    _validate_eligibility(state, eligibility)
    positions: dict[str, Position] = {}
    targets_by_date: dict[pd.Timestamp, dict[str, float]] = {}
    entries = 0
    exits = 0
    frozen_snapshot: ClusterSnapshot | None = None
    active_tickers: tuple[str, ...] = ()
    for signal_number, observations in enumerate(
        range(MINIMUM_HISTORY_SESSIONS, len(state.returns) + 1)
    ):
        if signal_number % MONTHLY_SNAPSHOT_DAYS == 0:
            formation_observations = observations - MONTHLY_SNAPSHOT_DAYS
            formation_date = state.returns.index[formation_observations - 1]
            active_tickers = eligibility.eligible_tickers(formation_date)
            removed = set(positions) - set(active_tickers)
            exits += len(removed)
            positions = {
                ticker: position
                for ticker, position in positions.items()
                if ticker in active_tickers
            }
            frozen_snapshot = None
        signal_date = state.returns.index[observations - 1]
        if len(active_tickers) < MIN_CLUSTER_SIZE:
            targets_by_date[signal_date] = {}
            continue
        current = _historical_state(
            state,
            observations,
            active_tickers,
            frozen_snapshot,
        )
        if frozen_snapshot is None:
            frozen_snapshot = current.clusters
        previous_positions = positions
        current = rebalance_historical_state(current, positions)
        entered, exited = _position_transitions(previous_positions, current.positions)
        entries += entered
        exits += exited
        positions = current.positions
        targets_by_date[current.returns.index[-1]] = current.targets
    targets = pd.DataFrame.from_dict(targets_by_date, orient="index")
    targets = targets.reindex(
        index=pd.Index(targets_by_date), columns=state.returns.columns
    ).fillna(0.0)
    targets.index.name = "signal_date"
    exits += len(positions)
    return SignalPath(targets=targets, entries=entries, exits=exits)


def evaluate_target_path(
    targets: pd.DataFrame,
    execution_returns: pd.DataFrame,
    config: BacktestConfig,
) -> pd.DataFrame:
    """Apply costs to targets earning the supplied next-open-to-next-open returns."""

    _validate_target_path(targets, execution_returns)
    if not targets.columns.equals(execution_returns.columns):
        raise ExecutionHistoryInvalid("target and execution columns differ")
    common = targets.index.intersection(execution_returns.dropna().index)
    if common.empty:
        raise ExecutionHistoryInvalid("target and execution histories do not overlap")
    aligned_targets = targets.loc[common]
    aligned_returns = execution_returns.loc[common]
    simple_asset_returns = np.expm1(aligned_returns)
    gross_return = (aligned_targets * simple_asset_returns).sum(axis=1)
    prior_targets = aligned_targets.shift(1).fillna(0.0)
    turnover = (aligned_targets - prior_targets).abs().sum(axis=1)
    turnover.iloc[-1] += float(aligned_targets.iloc[-1].abs().sum())
    transaction_cost = turnover * config.transaction_cost_bps / BASIS_POINTS_PER_UNIT
    short_gross = -aligned_targets.clip(upper=0.0).sum(axis=1)
    borrow_cost = (
        short_gross
        * config.annual_short_borrow_bps
        / BASIS_POINTS_PER_UNIT
        / TRADING_DAYS_PER_YEAR
    )
    return pd.DataFrame(
        {
            "gross_return": gross_return,
            "turnover": turnover,
            "transaction_cost": transaction_cost,
            "borrow_cost": borrow_cost,
            "net_return": gross_return - transaction_cost - borrow_cost,
            "gross_exposure": aligned_targets.abs().sum(axis=1),
            "net_exposure": aligned_targets.sum(axis=1),
        },
        index=common,
    )


def _state_through(state: PrototypeState, end: pd.Timestamp) -> PrototypeState:
    mask = state.returns.index <= end
    return replace(
        state,
        day=int(mask.sum()),
        returns=state.returns.loc[mask],
        market=state.market.loc[mask],
        volumes=state.volumes.loc[mask],
        gaps=state.gaps.loc[mask],
        positions={},
        targets={},
    )


def _historical_state(
    state: PrototypeState,
    observations: int,
    tickers: tuple[str, ...],
    frozen_snapshot: ClusterSnapshot | None,
) -> PrototypeState:
    return state_from_history(
        state.returns.loc[:, tickers].iloc[:observations],
        state.market.iloc[:observations],
        state.volumes.loc[:, tickers].iloc[:observations],
        state.gaps.loc[:, tickers].iloc[:observations],
        frozen_snapshot=frozen_snapshot,
    )


def _position_transitions(
    before: dict[str, Position], after: dict[str, Position]
) -> tuple[int, int]:
    before_keys = {(ticker, position.direction) for ticker, position in before.items()}
    after_keys = {(ticker, position.direction) for ticker, position in after.items()}
    return len(after_keys - before_keys), len(before_keys - after_keys)


def _validate_execution_returns(
    state: PrototypeState, execution_returns: pd.DataFrame
) -> None:
    if not state.returns.columns.equals(execution_returns.columns):
        raise ExecutionHistoryInvalid("state and execution columns differ")
    if not execution_returns.index.is_monotonic_increasing:
        raise ExecutionHistoryInvalid("execution dates are not ordered")
    if not execution_returns.index.is_unique:
        raise ExecutionHistoryInvalid("execution dates are not unique")
    finite_values = execution_returns.to_numpy()[~execution_returns.isna().to_numpy()]
    if not np.isfinite(finite_values).all():
        raise ExecutionHistoryInvalid("execution returns contain infinite values")
    complete = execution_returns.notna().all(axis=1)
    if complete.any():
        last_complete = int(np.flatnonzero(complete.to_numpy())[-1])
        if not complete.iloc[: last_complete + 1].all():
            raise ExecutionHistoryInvalid(
                "execution history has an incomplete session before its endpoint"
            )


def _validate_target_path(
    targets: pd.DataFrame, execution_returns: pd.DataFrame
) -> None:
    for name, frame in (("target", targets), ("execution", execution_returns)):
        if not frame.index.is_monotonic_increasing:
            raise ExecutionHistoryInvalid(f"{name} dates are not ordered")
        if not frame.index.is_unique:
            raise ExecutionHistoryInvalid(f"{name} dates are not unique")
        values = frame.to_numpy()[~frame.isna().to_numpy()]
        if not np.isfinite(values).all():
            raise ExecutionHistoryInvalid(f"{name} values contain infinities")
    if targets.isna().any().any():
        raise ExecutionHistoryInvalid("targets contain missing values")


def _validate_eligibility(
    state: PrototypeState, eligibility: HistoricalEligibility
) -> None:
    if not state.returns.columns.equals(eligibility.dollar_volumes.columns):
        raise HistoricalEligibilityInvalid("state and eligibility columns differ")


def _result(signal_path: SignalPath, daily: pd.DataFrame) -> BacktestResult:
    if len(daily) < 2:
        raise BacktestStatisticsUndefined(
            "at least two return observations are required"
        )
    if (daily["net_return"] <= -1.0).any():
        raise BacktestStatisticsUndefined("daily net return reached or crossed -100%")
    gross_total = float((1.0 + daily["gross_return"]).prod() - 1.0)
    net_total = float((1.0 + daily["net_return"]).prod() - 1.0)
    observations = len(daily)
    annualized_net = float(
        (1.0 + net_total) ** (TRADING_DAYS_PER_YEAR / observations) - 1.0
    )
    daily_volatility = float(daily["net_return"].std(ddof=1))
    annualized_volatility = daily_volatility * np.sqrt(TRADING_DAYS_PER_YEAR)
    sharpe: float | UndefinedStatistic = (
        float(daily["net_return"].mean() / daily_volatility)
        * np.sqrt(TRADING_DAYS_PER_YEAR)
        if daily_volatility > 0.0
        else UndefinedStatistic("zero return variance")
    )
    wealth = (1.0 + daily["net_return"]).cumprod()
    drawdown = wealth / wealth.cummax() - 1.0
    return BacktestResult(
        daily=daily,
        targets=signal_path.targets.loc[daily.index],
        entries=signal_path.entries,
        exits=signal_path.exits,
        exposure_days=int((daily["gross_exposure"] > 0.0).sum()),
        turnover=float(daily["turnover"].sum()),
        gross_total_return=gross_total,
        net_total_return=net_total,
        annualized_net_return=annualized_net,
        annualized_volatility=float(annualized_volatility),
        sharpe=sharpe,
        maximum_drawdown=float(drawdown.min()),
        transaction_cost_drag=float(daily["transaction_cost"].sum()),
        borrow_cost_drag=float(daily["borrow_cost"].sum()),
    )
