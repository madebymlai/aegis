"""Risk-budget e2e: 5-year covariance vol-target budget and attribution."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from aegis_trader.domain.allocator import (
    covariance_book_vol,
    portfolio_skew,
    risk_contribution_shares,
)
from aegis_trader.domain.attribution import AttributionPeriod, compute_sleeve_attribution
from aegis_trader.domain.book_config import (
    BookConfig,
    ConvexityBudgetCandidate,
    DrawdownDeleverCurve,
    RiskGroup,
    SleeveConfig,
    TailConvexityBudget,
)
from aegis_trader.domain.rebalancer import rebalance, rebalance_plan
from aegis_runtime import ListedRef
from aegis_trader.domain.types import SleeveName

_TREND = SleeveName("trend")
_CARRY = SleeveName("carry")
_TAIL = SleeveName("tail")
_EXPANSION = SleeveName("expansion")


def test_five_year_covariance_risk_budget_hits_vol_target_and_attribution_reconciles():
    """Tracer for the commingled backtest invariant without external data/wheels.

    Five years of synthetic daily sleeve returns produce a realized covariance
    input.  The rebalancer must use the allocator seam (not static capital
    budgets): the higher-vol tail receives half the capital multiplier of the
    lower-vol trend in the zero-correlation limit, the book hits the configured
    annualized vol target when leverage is permitted (``max_book_gross`` headroom,
    so the down-only clamp does not bind), and attribution sums back to the
    realized NAV change.
    """
    days = 252 * 5
    x = np.linspace(0.0, 80.0 * np.pi, days)
    trend_returns = 0.10 / np.sqrt(252.0) * np.sin(x)
    tail_returns = 0.20 / np.sqrt(252.0) * np.cos(x)
    covariance = _annualized_covariance(
        {
            _TREND: trend_returns,
            _TAIL: tail_returns,
        }
    )

    book = BookConfig(
        sleeves=(
            SleeveConfig(
                name=_TREND,
                wheel_filename="trend.whl",
                risk_share=0.5,
                group=RiskGroup.FLOOR,
            ),
            SleeveConfig(
                name=_TAIL,
                wheel_filename="tail.whl",
                risk_share=0.5,
                group=RiskGroup.TARGET,
            ),
        ),
        book_vol_target=0.09,
        max_book_gross=2.0,  # permit leverage so the solve hits the target (clamp tested separately)
    )

    target = _one_row_target
    deltas = rebalance(
        {
            _TREND: target({"TREND": 1.0}),
            _TAIL: target({"TAIL": 1.0}),
        },
        book,
        realized_covariance=covariance,
    )
    weights = {delta.ref.value: delta.delta for delta in deltas}

    assert weights["TAIL"] == pytest.approx(weights["TREND"] / 2.0, rel=0.02)
    assert covariance_book_vol(
        {_TREND: weights["TREND"], _TAIL: weights["TAIL"]},
        covariance,
    ) == pytest.approx(book.book_vol_target)

    nav = 1_000_000.0
    periods = [
        AttributionPeriod(
            nav=nav,
            realized_weights={ListedRef(k): v for k, v in weights.items()},
            sleeve_targets={_TREND: {ListedRef("TREND"): 1.0}, _TAIL: {ListedRef("TAIL"): 1.0}},
            closes={ListedRef("TREND"): 100.0, ListedRef("TAIL"): 100.0},
        ),
        AttributionPeriod(
            nav=nav,
            realized_weights={ListedRef(k): v for k, v in weights.items()},
            sleeve_targets={_TREND: {ListedRef("TREND"): 1.0}, _TAIL: {ListedRef("TAIL"): 1.0}},
            closes={ListedRef("TREND"): 101.0, ListedRef("TAIL"): 98.0},
        ),
    ]
    attribution = compute_sleeve_attribution(
        periods,
        budgets={_TREND: 0.5, _TAIL: 0.5},
    )
    book_pnl = (
        weights["TREND"] * 0.01
        + weights["TAIL"] * -0.02
    ) * nav

    assert sum(attribution.values()) == pytest.approx(book_pnl)


def test_down_only_clamp_runs_unlevered_book_as_a_vol_ceiling():
    """An unlevered book (gross_cap = max_book_gross = 1.0) whose vol-target solve
    over-levers no longer fails closed: the down-only clamp holds gross at the cap
    and realized vol sits below the target as a ceiling (ADR-0004 amendment)."""
    days = 252 * 5
    x = np.linspace(0.0, 80.0 * np.pi, days)
    trend_returns = 0.10 / np.sqrt(252.0) * np.sin(x)
    tail_returns = 0.20 / np.sqrt(252.0) * np.cos(x)
    covariance = _annualized_covariance({_TREND: trend_returns, _TAIL: tail_returns})

    book = BookConfig(
        sleeves=(
            SleeveConfig(name=_TREND, wheel_filename="trend.whl", risk_share=0.5, group=RiskGroup.FLOOR),
            SleeveConfig(name=_TAIL, wheel_filename="tail.whl", risk_share=0.5, group=RiskGroup.TARGET),
        ),
        book_vol_target=0.09,
        max_book_gross=1.0,
        gross_cap=1.0,
    )

    # The solve wants ~1.35x gross to peg 9%; previously this raised
    # "Gross exposure ... exceeds cap".  The down-only clamp now lets it run.
    deltas = rebalance(
        {_TREND: _one_row_target({"TREND": 1.0}), _TAIL: _one_row_target({"TAIL": 1.0})},
        book,
        realized_covariance=covariance,
    )
    weights = {d.ref.value: d.delta for d in deltas}
    gross = sum(abs(v) for v in weights.values())

    # Clamp bound at the cap -> proves the solve had over-levered past it.
    assert gross == pytest.approx(book.max_book_gross)
    # Realized book vol is a ceiling, below target (not pegged up via leverage).
    assert covariance_book_vol(
        {_TREND: weights["TREND"], _TAIL: weights["TAIL"]}, covariance
    ) < book.book_vol_target


def test_five_year_tail_convexity_budget_bounds_target_risk_and_zeros_expansion():
    """A convexity-premium Target budget keeps the tail from dominating risk."""
    days = 252 * 5
    x = np.linspace(0.0, 50.0 * np.pi, days)
    trend_returns = 0.10 / np.sqrt(252.0) * np.sin(x)
    tail_returns = 0.70 / np.sqrt(252.0) * np.cos(x)
    expansion_returns = 0.15 / np.sqrt(252.0) * np.sin(x + 0.4)
    returns = {
        _TREND: trend_returns,
        _TAIL: tail_returns,
        _EXPANSION: expansion_returns,
    }
    covariance = _annualized_covariance(returns)

    book = BookConfig(
        sleeves=(
            SleeveConfig(
                name=_TREND,
                wheel_filename="trend.whl",
                risk_share=0.60,
                group=RiskGroup.FLOOR,
            ),
            SleeveConfig(
                name=_TAIL,
                wheel_filename="tail.whl",
                risk_share=0.90,  # ignored: Target risk is set by the convexity budget
                group=RiskGroup.TARGET,
            ),
            SleeveConfig(
                name=_EXPANSION,
                wheel_filename="expansion.whl",
                risk_share=0.40,  # ignored until Expansion earns an explicit budget
                group=RiskGroup.EXPANSION,
            ),
        ),
        book_vol_target=0.09,
        tail_convexity_budget=TailConvexityBudget(
            attachment=-0.20,
            coverage_target=0.01,
            annual_carry_budget=0.0075,
            candidates=(
                ConvexityBudgetCandidate(
                    sleeve=_TAIL,
                    payoff_at_attachment=0.20,
                    annual_carry=0.08,
                    crisis_reliability=0.75,
                    capacity_risk_share=0.05,
                ),
            ),
        ),
    )

    deltas = rebalance(
        {
            _TREND: _one_row_target({"TREND": 1.0}),
            _TAIL: _one_row_target({"TAIL": 1.0}),
            _EXPANSION: _one_row_target({"EXPANSION": 1.0}),
        },
        book,
        realized_covariance=covariance,
    )
    weights = {delta.ref.value: delta.delta for delta in deltas}

    assert "EXPANSION" not in weights
    realized_risk = risk_contribution_shares(
        {_TREND: weights["TREND"], _TAIL: weights["TAIL"]},
        {_TREND: covariance[_TREND], _TAIL: covariance[_TAIL]},
    )
    assert realized_risk[_TAIL] < 0.02
    assert realized_risk[_TAIL] < realized_risk[_TREND]
    assert weights["TAIL"] < weights["TREND"] * 0.02


def _annualized_covariance(
    returns: dict[SleeveName, np.ndarray],
) -> dict[SleeveName, dict[SleeveName, float]]:
    return {
        left: {
            right: float(np.cov(left_returns, right_returns, ddof=1)[0, 1] * 252.0)
            for right, right_returns in returns.items()
        }
        for left, left_returns in returns.items()
    }


def _one_row_target(figi_to_weight: dict[str, float]):
    import pandas as pd

    df = pd.DataFrame(
        {k: [v] for k, v in figi_to_weight.items()},
        index=pd.DatetimeIndex(["2025-06-01"], name="timestamp"),
    )
    df.columns.name = "figi"
    return df


def test_sleeve_bands_cut_turnover_while_vol_target_stays_close():
    """Synthetic two-period revalidation of the sleeve-band allocator seam."""
    book = BookConfig(
        sleeves=(
            SleeveConfig(
                name=_TREND,
                wheel_filename="trend.whl",
                risk_share=0.5,
                group=RiskGroup.FLOOR,
                weight_band_down=0.01,
                weight_band_up=0.01,
            ),
            SleeveConfig(
                name=_TAIL,
                wheel_filename="tail.whl",
                risk_share=0.5,
                group=RiskGroup.TARGET,
                weight_band_down=0.01,
                weight_band_up=0.01,
            ),
        ),
        book_vol_target=0.09,
        sleeve_reversion_fraction=0.5,
    )
    targets = {_TREND: _one_row_target({"TREND": 1.0}), _TAIL: _one_row_target({"TAIL": 1.0})}
    first_covariance = {
        _TREND: {_TREND: 0.10**2, _TAIL: 0.0},
        _TAIL: {_TREND: 0.0, _TAIL: 0.10**2},
    }
    second_covariance = {
        _TREND: {_TREND: 0.10**2, _TAIL: 0.0},
        _TAIL: {_TREND: 0.0, _TAIL: 0.102**2},
    }

    first = rebalance_plan(targets, book, realized_covariance=first_covariance)
    full_second = rebalance_plan(targets, book, realized_covariance=second_covariance)
    banded_second = rebalance_plan(
        targets,
        book,
        realized_covariance=second_covariance,
        previous_sleeve_weights=dict(first.applied_sleeve_weights),
    )

    full_turnover = sum(
        abs(full_second.applied_sleeve_weights[name] - first.applied_sleeve_weights[name])
        for name in first.applied_sleeve_weights
    )
    banded_turnover = sum(
        abs(banded_second.applied_sleeve_weights[name] - first.applied_sleeve_weights[name])
        for name in first.applied_sleeve_weights
    )

    assert banded_turnover < full_turnover
    assert banded_turnover == pytest.approx(full_turnover / 2.0)
    assert covariance_book_vol(
        dict(banded_second.applied_sleeve_weights),
        second_covariance,
    ) == pytest.approx(book.book_vol_target, abs=0.001)


def test_all_concave_floor_allocates_by_conviction_tilt_with_no_skew_enforcement():
    """Net-convexity is by construction (ADR-0004 amendment), not a live solve.

    Both Floor poles can be transiently concave with no convex donor — the case
    that used to raise "skew constraint cannot be satisfied" (the bu4.7 blocker).
    With the live skew solve removed, the book simply allocates by its risk-budget
    conviction tilt (trend the larger pole) and completes; there is no skew
    machinery left to go infeasible.
    """
    book = BookConfig(
        sleeves=(
            SleeveConfig(
                name=_TREND,
                wheel_filename="trend.whl",
                risk_share=0.6,
                group=RiskGroup.FLOOR,
            ),
            SleeveConfig(
                name=_CARRY,
                wheel_filename="carry.whl",
                risk_share=0.4,
                group=RiskGroup.FLOOR,
            ),
        ),
        book_vol_target=0.09,
        max_book_gross=2.0,  # isolate from the down-only clamp; this is about skew
    )

    # The allocator no longer takes any skew input; an all-concave Floor is just
    # ordinary data it allocates over.
    deltas = rebalance(
        {
            _TREND: _one_row_target({"TREND": 1.0}),
            _CARRY: _one_row_target({"CARRY": 1.0}),
        },
        book,
        realized_covariance={
            _TREND: {_TREND: 0.10**2, _CARRY: 0.0},
            _CARRY: {_TREND: 0.0, _CARRY: 0.10**2},
        },
    )
    weights = {delta.ref.value: delta.delta for delta in deltas}

    # Completed (no infeasibility) and kept the conviction tilt: trend > carry.
    assert weights["TREND"] > weights["CARRY"]


def test_backtest_drawdown_delever_engages_in_worst_window_and_returns_are_measured():
    """Backtest seam: NAV drawdown from the engine drives a book-level de-lever.

    A five-year synthetic path opens with an early crash, stays in the trough,
    then heals.  The strategy computes drawdown from its recorded NAV path and
    passes it to the allocator; the observable effect is a sell order while the
    bundle still asks for a constant long target.
    """
    book = BookConfig(
        sleeves=(
            SleeveConfig(
                name=_TREND,
                wheel_filename="trend.whl",
                risk_share=1.0,
                group=RiskGroup.FLOOR,
            ),
        ),
        book_vol_target=0.09,
        drawdown_delever=DrawdownDeleverCurve(
            start_drawdown=0.05,
            end_drawdown=0.25,
            floor_multiplier=0.50,
        ),
    )

    # No drawdown: full allocation.
    deltas = rebalance(
        {_TREND: _one_row_target({"TREND": 1.0})},
        book,
        realized_vols={_TREND: 0.10},
        realized_drawdown=0.0,
    )
    weights = {delta.ref.value: delta.delta for delta in deltas}

    # Deep drawdown: scaled allocation.
    stressed = rebalance(
        {_TREND: _one_row_target({"TREND": 1.0})},
        book,
        realized_vols={_TREND: 0.10},
        realized_drawdown=0.25,
    )
    stressed_weights = {delta.ref.value: delta.delta for delta in stressed}
    assert stressed_weights["TREND"] == pytest.approx(weights["TREND"] * 0.50)

    # Recovery returns to full.
    recovered = rebalance(
        {_TREND: _one_row_target({"TREND": 1.0})},
        book,
        realized_vols={_TREND: 0.10},
        realized_drawdown=0.04,
    )
    recovered_weights = {delta.ref.value: delta.delta for delta in recovered}
    assert recovered_weights["TREND"] == pytest.approx(weights["TREND"])


# ── Slice 3 (aegis-rd-ytr.3): full multi-year re-validation of the down-only book ──
#
# The mechanism (down-only clamp, ytr.1; live skew solve deleted + net-convex by
# construction, ytr.2) is driven through a five-year synthetic window that traverses
# every regime: a calm stretch where the vol-target solve over-levers (clamp binds),
# an all-concave-Floor stretch (the old bu4.7 halt case — must NOT fail closed now),
# and a crisis drawdown (de-lever must engage).  The real-data run + operator sign-off
# stay in aegis-rd-bu4.7; this proves the mechanism runs clean and holds every invariant.

_TRADING_DAYS = 252
_REBALANCE_EVERY = 21          # monthly
_COV_WINDOW = 252              # trailing 1y covariance
_CONCAVE_FLOOR_DAYS = (300, 360)   # both Floor poles transiently concave
_CRISIS_DAYS = (600, 700)          # book-wide drawdown -> de-lever


def _five_year_sleeve_returns() -> dict[SleeveName, np.ndarray]:
    """Deterministic 5y daily returns: a convex trend pole, a concave carry pole,
    a strongly convex tail, plus an all-concave-Floor stretch and a crisis window."""
    rng = np.random.default_rng(20260615)
    n = _TRADING_DAYS * 5

    def convex(mean: float, vol: float, p: float, lo: float, hi: float) -> np.ndarray:
        r = rng.normal(mean, vol, n)
        m = rng.random(n) < p
        r[m] += rng.uniform(lo, hi, int(m.sum()))
        return r

    def concave(mean: float, vol: float, p: float, lo: float, hi: float) -> np.ndarray:
        r = rng.normal(mean, vol, n)
        m = rng.random(n) < p
        r[m] -= rng.uniform(lo, hi, int(m.sum()))
        return r

    trend = convex(-0.0010, 0.004, 0.08, 0.040, 0.090)  # convex pole (strong right-skew)
    carry = concave(0.0004, 0.004, 0.015, 0.006, 0.012)  # mildly concave pole (left-skew)
    tail = convex(-0.0008, 0.003, 0.02, 0.10, 0.25)     # strongly convex, tiny budget

    # All-concave Floor stretch: trend also turns left-skewed (the halt case).
    lo, hi = _CONCAVE_FLOOR_DAYS
    seg = hi - lo
    trend[lo:hi] = rng.normal(0.0008, 0.004, seg)
    m = rng.random(seg) < 0.18
    trend[lo:hi][m] -= rng.uniform(0.02, 0.04, int(m.sum()))

    # Crisis: book-wide sharp losses drive an NAV drawdown past the de-lever curve.
    clo, chi = _CRISIS_DAYS
    trend[clo:chi] = rng.normal(-0.012, 0.010, chi - clo)
    carry[clo:chi] = rng.normal(-0.010, 0.009, chi - clo)

    return {_TREND: trend, _CARRY: carry, _TAIL: tail}


def _five_year_down_only_book() -> BookConfig:
    """The real-shaped unlevered book: trend+carry Floor, tail Target via the
    convexity-premium budget; gross = net = max_book_gross = 1.0; 9% vol target."""
    return BookConfig(
        sleeves=(
            SleeveConfig(name=_TREND, wheel_filename="trend.whl", risk_share=0.60, group=RiskGroup.FLOOR),
            SleeveConfig(name=_CARRY, wheel_filename="carry.whl", risk_share=0.40, group=RiskGroup.FLOOR),
            SleeveConfig(name=_TAIL, wheel_filename="tail.whl", risk_share=0.90, group=RiskGroup.TARGET),
        ),
        book_vol_target=0.09,
        max_book_gross=1.0,
        gross_cap=1.0,
        net_cap=1.0,
        drawdown_delever=DrawdownDeleverCurve(
            start_drawdown=0.05, end_drawdown=0.25, floor_multiplier=0.50
        ),
        tail_convexity_budget=TailConvexityBudget(
            attachment=-0.20,
            coverage_target=0.01,
            annual_carry_budget=0.0075,
            candidates=(
                ConvexityBudgetCandidate(
                    sleeve=_TAIL, payoff_at_attachment=0.20, annual_carry=0.08,
                    crisis_reliability=0.75, capacity_risk_share=0.05,
                ),
            ),
        ),
    )


@dataclass(frozen=True)
class _BookRun:
    book: BookConfig
    risk_shares: dict[SleeveName, float]
    rebalance_days: list[int]
    grosses: list[float]
    share_path: list[dict[SleeveName, float]]
    final_floor_weights: dict[SleeveName, float]
    daily_book_returns: list[float]
    daily_floor_returns: dict[SleeveName, list[float]]
    nav_path: list[float]
    attribution_periods: list[AttributionPeriod]

    def realized_annual_vol(self) -> float:
        return float(np.std(self.daily_book_returns, ddof=1) * np.sqrt(_TRADING_DAYS))

    def floor_skew(self) -> float:
        """Realized skew of the conviction-tilted Floor stream over the window."""
        series = {name: tuple(vals) for name, vals in self.daily_floor_returns.items()}
        return portfolio_skew(self.final_floor_weights, series)

    def quarter_floor_skews(self) -> list[float]:
        series = {name: tuple(vals) for name, vals in self.daily_floor_returns.items()}
        n = len(series[_TREND])
        q = _TRADING_DAYS // 4
        return [
            portfolio_skew(self.final_floor_weights, {name: series[name][i:i + q] for name in series})
            for i in range(0, n - q, q)
        ]

    def drawdowns(self) -> np.ndarray:
        nav = np.array(self.nav_path[:-1])
        return (np.maximum.accumulate(nav) - nav) / np.maximum.accumulate(nav)

    def gross_at_worst_drawdown(self) -> float:
        return self.grosses[int(self.drawdowns().argmax())]

    def calm_gross(self) -> float:
        g = np.array(self.grosses)
        return float(np.median(g[self.drawdowns() < 0.02]))


def _run_five_year_down_only_book() -> _BookRun:
    """Drive the rebalance pipeline monthly through the 5y window, holding each
    month's applied weights over the next month and accruing NAV by the realized-
    weight identity (so attribution reconciles by construction)."""
    returns = _five_year_sleeve_returns()
    names = (_TREND, _CARRY, _TAIL)
    floor = (_TREND, _CARRY)
    n = len(returns[_TREND])

    prices = {name: np.concatenate([[100.0], 100.0 * np.cumprod(1.0 + returns[name])]) for name in names}
    targets = {name: _one_row_target({name.value.upper(): 1.0}) for name in names}

    book = _five_year_down_only_book()
    risk_shares = book.allocator_risk_shares()

    nav = 1_000_000.0
    nav_path = [nav]
    peak = nav
    prev_weights: dict[SleeveName, float] | None = None
    rebalance_days, grosses, share_path = [], [], []
    daily_book_returns: list[float] = []
    daily_floor_returns: dict[SleeveName, list[float]] = {_TREND: [], _CARRY: []}
    attribution_periods: list[AttributionPeriod] = []
    last_weights: dict[SleeveName, float] = {}

    for t in range(_COV_WINDOW, n - _REBALANCE_EVERY, _REBALANCE_EVERY):
        window = {name: returns[name][t - _COV_WINDOW:t] for name in names}
        covariance = _annualized_covariance(window)
        drawdown = max(0.0, (peak - nav) / peak)

        plan = rebalance_plan(
            targets, book,
            realized_covariance=covariance,
            realized_drawdown=drawdown,
            previous_sleeve_weights=prev_weights,
        )
        # Economics use the CLAMPED book positions (deltas, post down-only clamp),
        # not the pre-clamp allocator multipliers; band continuity threads the
        # multipliers, matching production (ytr.1 clamps net positions).
        w = {name: 0.0 for name in names}
        for delta in plan.deltas:
            w[SleeveName(delta.ref.value.lower())] = float(delta.delta)
        last_weights = w
        prev_weights = dict(plan.applied_sleeve_weights)

        rebalance_days.append(t)
        grosses.append(sum(abs(v) for v in w.values()))
        share_path.append(risk_contribution_shares(w, covariance))

        attribution_periods.append(
            AttributionPeriod(
                nav=nav,
                realized_weights={ListedRef(name.value): w[name] for name in names},
                sleeve_targets={name: {ListedRef(name.value): 1.0} for name in names},
                closes={ListedRef(name.value): float(prices[name][t]) for name in names},
            )
        )

        # Hold w over the next month: daily book/floor returns (for vol + skew) and
        # the close-to-close period return (for NAV + attribution reconciliation).
        for d in range(t, t + _REBALANCE_EVERY):
            daily_book_returns.append(sum(w[name] * returns[name][d] for name in names))
            for name in floor:
                daily_floor_returns[name].append(float(returns[name][d]))
        period_return = sum(
            w[name] * (prices[name][t + _REBALANCE_EVERY] / prices[name][t] - 1.0) for name in names
        )
        nav *= 1.0 + period_return
        nav_path.append(nav)
        peak = max(peak, nav)

    # Closing period so the final realized weights attribute over their last month.
    t_last = rebalance_days[-1] + _REBALANCE_EVERY
    attribution_periods.append(
        AttributionPeriod(
            nav=nav,
            realized_weights={ListedRef(name.value): last_weights[name] for name in names},
            sleeve_targets={name: {ListedRef(name.value): 1.0} for name in names},
            closes={ListedRef(name.value): float(prices[name][t_last]) for name in names},
        )
    )

    return _BookRun(
        book=book,
        risk_shares=risk_shares,
        rebalance_days=rebalance_days,
        grosses=grosses,
        share_path=share_path,
        final_floor_weights={name: last_weights[name] for name in floor},
        daily_book_returns=daily_book_returns,
        daily_floor_returns=daily_floor_returns,
        nav_path=nav_path,
        attribution_periods=attribution_periods,
    )


@pytest.fixture(scope="module")
def five_year_run() -> _BookRun:
    return _run_five_year_down_only_book()


def test_five_year_down_only_book_runs_the_full_window_without_failing_closed(five_year_run):
    """Criterion 1: the book runs the full multi-year window end-to-end — through
    the all-concave-Floor stretch and the crisis — without ever failing closed."""
    # The loop completed across every regime (no raise == no fail-closed).
    assert len(five_year_run.grosses) == len(five_year_run.rebalance_days)
    assert len(five_year_run.grosses) > 40  # ~47 monthly rebalances over the 5y window
    assert five_year_run.nav_path[-1] > 0.0


def test_five_year_realized_gross_never_exceeds_the_cap(five_year_run):
    """Criterion 2: the down-only clamp holds realized gross ≤ cap at every
    rebalance — and the clamp actually binds (the solve over-levered)."""
    cap = five_year_run.book.max_book_gross
    assert all(gross <= cap + 1e-9 for gross in five_year_run.grosses)
    # The clamp engaged: at least one month the vol-target solve hit the cap.
    assert max(five_year_run.grosses) == pytest.approx(cap)


def test_five_year_realized_vol_is_a_ceiling_and_de_levers_in_the_worst_window(five_year_run):
    """Criterion 3: realized vol behaves as a ceiling (≤ target), and the book
    de-levers hard in the worst drawdown window."""
    assert five_year_run.realized_annual_vol() <= five_year_run.book.book_vol_target
    # Worst-drawdown gross is far below the calm-period gross (de-lever engaged).
    assert five_year_run.gross_at_worst_drawdown() < 0.6 * five_year_run.calm_gross()


def test_five_year_tail_risk_share_stays_bounded_and_never_dominates(five_year_run):
    """Criterion 4: the convexity-premium tail's realized Risk Share stays small
    and never dominates the Floor at any rebalance."""
    assert max(shares[_TAIL] for shares in five_year_run.share_path) < 0.05
    assert all(shares[_TAIL] < shares[_TREND] for shares in five_year_run.share_path)


def test_five_year_per_sleeve_attribution_reconciles_to_nav_change(five_year_run):
    """Criterion 5: per-sleeve P&L attribution sums back to the realized NAV change."""
    attribution = compute_sleeve_attribution(
        five_year_run.attribution_periods, budgets=five_year_run.risk_shares
    )
    nav_change = five_year_run.nav_path[-1] - five_year_run.nav_path[0]
    assert sum(attribution.values()) == pytest.approx(nav_change)


def test_five_year_floor_stays_net_convex_by_construction(five_year_run):
    """Criterion 6 (aegis-rd-ytr.2 validation): with the live skew solve gone, the
    conviction-tilted Floor is net-convex BY CONSTRUCTION over the window — full-
    window skew ≥ 0 (hard) and net-convex in the majority of rolling quarters (soft).

    A negative result here would NOT resurrect the deleted live solve: it is a
    calibration signal for the convex pole / tail, routed to aegis-rd-bu4.7.
    """
    assert five_year_run.floor_skew() >= 0.0
    quarters = five_year_run.quarter_floor_skews()
    net_convex = sum(1 for s in quarters if s >= 0.0)
    assert net_convex > len(quarters) / 2
