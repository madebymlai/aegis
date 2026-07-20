"""Pure state model for the throwaway ETF cluster-reversal prototype."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

FORMATION_DAYS = 120
SIGNAL_DAYS = 5
MONTHLY_SNAPSHOT_DAYS = 21
MINIMUM_HISTORY_SESSIONS = FORMATION_DAYS + MONTHLY_SNAPSHOT_DAYS + SIGNAL_DAYS
ENTRY_Z = 3.0
EXIT_Z = 0.5
MAX_HOLD_DAYS = 5
CLUSTER_DISTANCE = 0.55
DUPLICATE_CORRELATION = 0.995
MIN_CLUSTER_SIZE = 3
CLUSTER_STABILITY_FLOOR = 0.60

GROUPS = {
    "TECHNOLOGY": ("IUIT", "QDVE", "SXLK", "XUTC"),
    "HEALTH_CARE": ("IUHC", "QDVG", "SXLV", "XUHC"),
    "FINANCIALS": ("IUFS", "QDVH", "SXLF", "XUFN"),
    "WORLD_EQUITY": ("SSAC", "SWDA", "VHVG", "VWRL"),
}
TICKERS = tuple(ticker for members in GROUPS.values() for ticker in members)


class ModelStateInvalid(ValueError):
    """The supplied history cannot support a coherent reversal state."""


class Action(StrEnum):
    TICK = "tick"
    FLOW_SHOCK = "flow_shock"
    BUCKET_MOVE = "bucket_move"
    DUPLICATE_MOVE = "duplicate_move"
    REGIME_BREAK = "regime_break"
    REVERT = "revert"
    FREEZE_CLUSTERS = "freeze_clusters"
    REBALANCE = "rebalance"


@dataclass(frozen=True)
class ClusterSnapshot:
    formed_on: str
    assignments: dict[str, int]
    duplicates: dict[str, str]
    stability: dict[str, float]
    market_betas: dict[str, float]


@dataclass(frozen=True)
class Assessment:
    ticker: str
    cluster: int | None
    residual_z: float | None
    volume_ratio: float
    gap: float
    stability: float
    eligible: bool
    reason: str


@dataclass(frozen=True)
class Position:
    ticker: str
    direction: int
    age: int
    entry_z: float
    cluster: int


@dataclass(frozen=True)
class PrototypeState:
    day: int
    returns: pd.DataFrame
    market: pd.Series
    volumes: pd.DataFrame
    gaps: pd.DataFrame
    clusters: ClusterSnapshot
    positions: dict[str, Position]
    targets: dict[str, float]
    last_action: str


def initial_state() -> PrototypeState:
    """Create deterministic synthetic OHLCV-derived state and freeze initial clusters."""

    returns, market, volumes, gaps = _synthetic_history()
    empty = ClusterSnapshot("", {}, {}, {}, {})
    state = PrototypeState(
        day=len(returns),
        returns=returns,
        market=market,
        volumes=volumes,
        gaps=gaps,
        clusters=empty,
        positions={},
        targets={},
        last_action="initialized deterministic synthetic history",
    )
    return _freeze_clusters(state)


def state_from_history(
    returns: pd.DataFrame,
    market: pd.Series,
    volumes: pd.DataFrame,
    gaps: pd.DataFrame,
    frozen_snapshot: ClusterSnapshot | None = None,
) -> PrototypeState:
    """Create a state whose current clusters are compared with last month's freeze."""

    _validate_history(returns, market, volumes, gaps)
    decision_snapshot = frozen_snapshot or _prior_snapshot(
        returns, market, volumes, gaps
    )
    current = PrototypeState(
        day=len(returns),
        returns=returns,
        market=market,
        volumes=volumes,
        gaps=gaps,
        clusters=decision_snapshot,
        positions={},
        targets={},
        last_action="loaded causal IBKR UCITS history",
    )
    diagnostic = _freeze_clusters(current)
    decision_snapshot = replace(
        decision_snapshot,
        stability=diagnostic.clusters.stability,
    )
    return replace(
        current,
        clusters=decision_snapshot,
        last_action="loaded current history against prior frozen clusters",
    )


def _prior_snapshot(
    returns: pd.DataFrame,
    market: pd.Series,
    volumes: pd.DataFrame,
    gaps: pd.DataFrame,
) -> ClusterSnapshot:
    empty = ClusterSnapshot("", {}, {}, {}, {})
    prior = PrototypeState(
        day=len(returns) - MONTHLY_SNAPSHOT_DAYS,
        returns=returns.iloc[:-MONTHLY_SNAPSHOT_DAYS],
        market=market.iloc[:-MONTHLY_SNAPSHOT_DAYS],
        volumes=volumes.iloc[:-MONTHLY_SNAPSHOT_DAYS],
        gaps=gaps.iloc[:-MONTHLY_SNAPSHOT_DAYS],
        clusters=empty,
        positions={},
        targets={},
        last_action="loaded prior causal history",
    )
    return _freeze_clusters(prior).clusters


def transition(state: PrototypeState, action: Action) -> PrototypeState:
    """Apply one visible prototype action and return the complete new state."""

    if action is Action.FREEZE_CLUSTERS:
        return _freeze_clusters(state)
    if action is Action.REBALANCE:
        return _rebalance(state)
    if action is Action.REGIME_BREAK:
        return _inject_regime_break(state)
    if action is Action.REVERT:
        return _append_day(state, action, _reversion_returns(state))
    return _append_day(state, action, _scenario_returns(state, action))


def rebalance_historical_state(
    state: PrototypeState, prior_positions: dict[str, Position]
) -> PrototypeState:
    """Age an existing live-like book once and apply today's deterministic rule."""

    aged = {
        ticker: replace(position, age=position.age + 1)
        for ticker, position in prior_positions.items()
    }
    return _rebalance(replace(state, positions=aged))


def assessments(state: PrototypeState) -> tuple[Assessment, ...]:
    """Describe the latest residual state without changing positions."""

    residuals = _market_residuals(state)
    rows: list[Assessment] = []
    for ticker in state.returns.columns:
        duplicate_of = state.clusters.duplicates.get(ticker)
        cluster = state.clusters.assignments.get(ticker)
        stability = state.clusters.stability.get(ticker, 0.0)
        volume_ratio = _latest_volume_ratio(state, ticker)
        gap = float(state.gaps[ticker].iloc[-1])
        if duplicate_of is not None:
            rows.append(
                Assessment(
                    ticker,
                    cluster,
                    None,
                    volume_ratio,
                    gap,
                    stability,
                    False,
                    f"duplicate wrapper of {duplicate_of}",
                )
            )
            continue
        peers = _cluster_peers(state.clusters, ticker)
        if len(peers) < MIN_CLUSTER_SIZE - 1:
            rows.append(
                Assessment(
                    ticker,
                    cluster,
                    None,
                    volume_ratio,
                    gap,
                    stability,
                    False,
                    "cluster too small",
                )
            )
            continue
        z_score = _residual_z(residuals, ticker, peers)
        if stability < CLUSTER_STABILITY_FLOOR:
            reason = "cluster unstable"
        elif abs(gap) >= 0.025:
            reason = "extreme overnight gap"
        elif abs(z_score) < ENTRY_Z:
            reason = "inside entry boundary"
        else:
            reason = "eligible residual displacement"
        rows.append(
            Assessment(
                ticker,
                cluster,
                z_score,
                volume_ratio,
                gap,
                stability,
                reason == "eligible residual displacement",
                reason,
            )
        )
    return tuple(rows)


def _synthetic_history() -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(17)
    days = 180
    index = pd.bdate_range("2025-10-01", periods=days)
    market = pd.Series(rng.normal(0.0002, 0.009, days), index=index, name="MARKET")
    group_factors = {group: rng.normal(0.0, 0.006, days) for group in GROUPS}
    market_betas = {
        "TECHNOLOGY": 1.15,
        "HEALTH_CARE": 0.85,
        "FINANCIALS": 1.05,
        "WORLD_EQUITY": 1.0,
    }
    values: dict[str, np.ndarray] = {}
    for group, members in GROUPS.items():
        for ticker in members:
            noise = rng.normal(0.0, 0.0025, days)
            values[ticker] = (
                market_betas[group] * market.to_numpy() + group_factors[group] + noise
            )
    values["QDVE"] = values["IUIT"] + rng.normal(0.0, 0.00005, days)
    values["QDVG"] = values["IUHC"] + rng.normal(0.0, 0.00008, days)
    returns = pd.DataFrame(values, index=index)
    volumes = pd.DataFrame(
        rng.lognormal(mean=16.0, sigma=0.25, size=(days, len(TICKERS))),
        index=index,
        columns=TICKERS,
    )
    gaps = pd.DataFrame(
        rng.normal(0.0, 0.002, size=(days, len(TICKERS))),
        index=index,
        columns=TICKERS,
    )
    return returns, market, volumes, gaps


def _freeze_clusters(state: PrototypeState) -> PrototypeState:
    residuals, betas = _estimate_market_residuals(state.returns, state.market)
    window = residuals.iloc[-FORMATION_DAYS:]
    correlation = window.corr().clip(-1.0, 1.0)
    duplicates = _duplicate_wrappers(correlation)
    kept = [ticker for ticker in state.returns.columns if ticker not in duplicates]
    if len(kept) < 2:
        raise ModelStateInvalid(
            "fewer than two non-duplicate assets remain for clustering"
        )
    kept_correlation = correlation.loc[kept, kept]
    distance = np.sqrt(np.maximum(0.0, (1.0 - kept_correlation.to_numpy()) / 2.0))
    np.fill_diagonal(distance, 0.0)
    tree = linkage(squareform(distance, checks=False), method="average")
    labels = fcluster(tree, t=CLUSTER_DISTANCE, criterion="distance")
    assignments = dict(zip(kept, (int(label) for label in labels), strict=True))
    for duplicate, representative in duplicates.items():
        assignments[duplicate] = assignments[representative]
    stability = _cluster_stability(state.clusters.assignments, assignments)
    snapshot = ClusterSnapshot(
        formed_on=state.returns.index[-1].date().isoformat(),
        assignments=assignments,
        duplicates=duplicates,
        stability=stability,
        market_betas=betas,
    )
    return replace(
        state,
        clusters=snapshot,
        last_action="froze clusters using trailing market-residual correlations",
    )


def _duplicate_wrappers(correlation: pd.DataFrame) -> dict[str, str]:
    duplicates: dict[str, str] = {}
    for right_index, right in enumerate(correlation.columns):
        for left in correlation.columns[:right_index]:
            if correlation.loc[left, right] >= DUPLICATE_CORRELATION:
                duplicates[right] = duplicates.get(left, left)
                break
    return duplicates


def _cluster_stability(
    previous: dict[str, int], current: dict[str, int]
) -> dict[str, float]:
    if not previous:
        return {ticker: 1.0 for ticker in current}
    stability: dict[str, float] = {}
    for ticker, current_label in current.items():
        current_members = {
            name for name, label in current.items() if label == current_label
        }
        previous_label = previous.get(ticker)
        previous_members = {
            name for name, label in previous.items() if label == previous_label
        }
        union = current_members | previous_members
        stability[ticker] = (
            len(current_members & previous_members) / len(union) if union else 0.0
        )
    return stability


def _market_residuals(state: PrototypeState) -> pd.DataFrame:
    return state.returns.subtract(
        state.market.to_numpy()[:, None]
        * np.array(
            [state.clusters.market_betas[ticker] for ticker in state.returns.columns]
        ),
        axis=0,
    )


def _estimate_market_residuals(
    returns: pd.DataFrame, market: pd.Series
) -> tuple[pd.DataFrame, dict[str, float]]:
    window_returns = returns.iloc[-FORMATION_DAYS:]
    window_market = market.iloc[-FORMATION_DAYS:]
    market_variance = float(window_market.var())
    if not np.isfinite(market_variance) or market_variance <= 0.0:
        raise ModelStateInvalid("market return variance is not positive")
    betas = {
        ticker: float(window_returns[ticker].cov(window_market) / market_variance)
        for ticker in returns.columns
    }
    residuals = returns.subtract(
        market.to_numpy()[:, None]
        * np.array([betas[ticker] for ticker in returns.columns]),
        axis=0,
    )
    if not np.isfinite(residuals.to_numpy()).all():
        raise ModelStateInvalid("market residuals contain non-finite values")
    return residuals, betas


def _cluster_peers(snapshot: ClusterSnapshot, ticker: str) -> tuple[str, ...]:
    label = snapshot.assignments.get(ticker)
    return tuple(
        name
        for name, member_label in snapshot.assignments.items()
        if member_label == label and name != ticker and name not in snapshot.duplicates
    )


def _residual_z(residuals: pd.DataFrame, ticker: str, peers: tuple[str, ...]) -> float:
    peer_return = residuals.loc[:, peers].mean(axis=1)
    formation_asset = residuals[ticker].iloc[-FORMATION_DAYS:-SIGNAL_DAYS]
    formation_peer = peer_return.iloc[-FORMATION_DAYS:-SIGNAL_DAYS]
    peer_variance = float(formation_peer.var())
    peer_beta = (
        float(formation_asset.cov(formation_peer) / peer_variance)
        if peer_variance > 0.0
        else 1.0
    )
    deviation = residuals[ticker] - peer_beta * peer_return
    historical = deviation.rolling(SIGNAL_DAYS).sum().iloc[-FORMATION_DAYS:-SIGNAL_DAYS]
    scale = float(historical.std())
    return float(deviation.iloc[-SIGNAL_DAYS:].sum() / scale) if scale > 0.0 else 0.0


def _latest_volume_ratio(state: PrototypeState, ticker: str) -> float:
    baseline = float(state.volumes[ticker].iloc[-21:-1].median())
    return float(state.volumes[ticker].iloc[-1] / baseline)


def _scenario_returns(state: PrototypeState, action: Action) -> dict[str, float]:
    rng = np.random.default_rng(1000 + state.day)
    market = float(rng.normal(0.0, 0.004))
    values = {ticker: market + float(rng.normal(0.0, 0.002)) for ticker in TICKERS}
    if action is Action.FLOW_SHOCK:
        values["XUFN"] -= 0.035
    elif action is Action.BUCKET_MOVE:
        for ticker in GROUPS["HEALTH_CARE"]:
            values[ticker] += 0.025
    elif action is Action.DUPLICATE_MOVE:
        values["IUIT"] += 0.025
        values["QDVE"] += 0.025
    return values


def _append_day(
    state: PrototypeState, action: Action, return_values: dict[str, float]
) -> PrototypeState:
    next_date = state.returns.index[-1] + pd.offsets.BDay()
    market_return = float(np.median(list(return_values.values())))
    returns = pd.concat(
        [state.returns, pd.DataFrame([return_values], index=[next_date])]
    )
    market = pd.concat([state.market, pd.Series([market_return], index=[next_date])])
    volumes = pd.concat(
        [
            state.volumes,
            pd.DataFrame(
                [
                    {
                        ticker: float(state.volumes[ticker].iloc[-20:].median())
                        * (
                            4.0
                            if action is Action.FLOW_SHOCK and ticker == "XUFN"
                            else 1.0
                        )
                        for ticker in TICKERS
                    }
                ],
                index=[next_date],
            ),
        ]
    )
    gaps = pd.concat(
        [
            state.gaps,
            pd.DataFrame(
                [
                    {
                        ticker: (
                            0.03
                            if action is Action.DUPLICATE_MOVE
                            and ticker in {"IUIT", "QDVE"}
                            else 0.0
                        )
                        for ticker in TICKERS
                    }
                ],
                index=[next_date],
            ),
        ]
    )
    aged = {
        ticker: replace(position, age=position.age + 1)
        for ticker, position in state.positions.items()
    }
    return replace(
        state,
        day=state.day + 1,
        returns=returns,
        market=market,
        volumes=volumes,
        gaps=gaps,
        positions=aged,
        last_action=action.value,
    )


def _reversion_returns(state: PrototypeState) -> dict[str, float]:
    values = _scenario_returns(state, Action.TICK)
    for position in state.positions.values():
        values[position.ticker] += 0.018 * position.direction
    return values


def _inject_regime_break(state: PrototypeState) -> PrototypeState:
    broken = state
    for offset in range(70):
        rng = np.random.default_rng(9000 + state.day + offset)
        shared = float(rng.normal(0.0, 0.008))
        values = _scenario_returns(broken, Action.TICK)
        for ticker in ("SXLV", "XUHC", "SXLF", "XUFN"):
            values[ticker] = shared + float(rng.normal(0.0, 0.001))
        broken = _append_day(broken, Action.REGIME_BREAK, values)
    return replace(
        broken, last_action="injected 70-day cross-bucket correlation regime break"
    )


def _rebalance(state: PrototypeState) -> PrototypeState:
    latest = {item.ticker: item for item in assessments(state)}
    positions: dict[str, Position] = {}
    exit_reasons: list[str] = []
    exited_tickers: set[str] = set()
    for ticker, position in state.positions.items():
        item = latest[ticker]
        if (
            item.residual_z is None
            or item.cluster != position.cluster
            or item.stability < CLUSTER_STABILITY_FLOOR
        ):
            exit_reasons.append(f"{ticker}: invalid anchor")
            exited_tickers.add(ticker)
        elif abs(item.residual_z) <= EXIT_Z:
            exit_reasons.append(f"{ticker}: normalized")
            exited_tickers.add(ticker)
        elif position.age >= MAX_HOLD_DAYS:
            exit_reasons.append(f"{ticker}: horizon expired")
            exited_tickers.add(ticker)
        else:
            positions[ticker] = position
    for item in latest.values():
        if (
            not item.eligible
            or item.ticker in positions
            or item.ticker in exited_tickers
            or item.residual_z is None
            or item.cluster is None
        ):
            continue
        positions[item.ticker] = Position(
            ticker=item.ticker,
            direction=-1 if item.residual_z > 0.0 else 1,
            age=0,
            entry_z=item.residual_z,
            cluster=item.cluster,
        )
    targets = _targets(positions, state.clusters)
    description = "rebalanced"
    if exit_reasons:
        description += "; " + ", ".join(exit_reasons)
    return replace(
        state,
        positions=positions,
        targets=targets,
        last_action=description,
    )


def _targets(
    positions: dict[str, Position], snapshot: ClusterSnapshot
) -> dict[str, float]:
    targets = {ticker: 0.0 for ticker in snapshot.assignments}
    for position in positions.values():
        peers = _cluster_peers(snapshot, position.ticker)
        if not peers:
            continue
        targets[position.ticker] += 0.5 * position.direction
        hedge = -0.5 * position.direction / len(peers)
        for peer in peers:
            targets[peer] += hedge
    gross = sum(abs(weight) for weight in targets.values())
    if gross > 0.0:
        targets = {ticker: weight / gross for ticker, weight in targets.items()}
    return {ticker: weight for ticker, weight in targets.items() if abs(weight) > 1e-9}


def _validate_history(
    returns: pd.DataFrame,
    market: pd.Series,
    volumes: pd.DataFrame,
    gaps: pd.DataFrame,
) -> None:
    minimum = FORMATION_DAYS + MONTHLY_SNAPSHOT_DAYS + SIGNAL_DAYS
    if len(returns) < minimum:
        raise ModelStateInvalid(
            f"history needs at least {minimum} aligned daily returns"
        )
    if returns.empty or returns.shape[1] < MIN_CLUSTER_SIZE:
        raise ModelStateInvalid(
            f"history needs at least {MIN_CLUSTER_SIZE} peer assets"
        )
    if not returns.index.equals(market.index):
        raise ModelStateInvalid("market and peer return indices differ")
    if not returns.index.equals(volumes.index) or not returns.index.equals(gaps.index):
        raise ModelStateInvalid("return, volume, and gap indices differ")
    if not returns.columns.equals(volumes.columns) or not returns.columns.equals(
        gaps.columns
    ):
        raise ModelStateInvalid("return, volume, and gap columns differ")
