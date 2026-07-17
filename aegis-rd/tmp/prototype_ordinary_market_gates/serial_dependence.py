"""PROTOTYPE (throwaway) — serial-dependence measurement statistics.

Pure functions only: Lo-MacKinlay variance ratios with heteroskedasticity-
robust M2 statistics, Chow-Denning joint inference by wild bootstrap, and
regime-conditioned lag-1 autocorrelation with a wild-bootstrap slope-
difference test. No I/O, no printing.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class VarianceRatioResult:
    horizons: tuple[int, ...]
    vr: tuple[float, ...]
    m2: tuple[float, ...]  # heteroskedasticity-robust z per horizon
    p_horizon: tuple[float, ...]  # per-horizon two-sided wild-bootstrap p
    joint_stat: float  # Chow-Denning MV = max_k |M2(k)|
    p_joint: float  # wild-bootstrap joint p
    n: int


def _vr_m2(x: np.ndarray, horizons: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray]:
    t = x.size
    mu = x.mean()
    d = x - mu
    var1 = (d**2).sum() / (t - 1)
    sq = d**2
    denom = sq.sum() ** 2
    vrs, m2s = [], []
    for k in horizons:
        # Lo-MacKinlay m divisor contains the factor k, so vark is already the
        # per-period variance of overlapping k-sums: VR = vark / var1.
        m = k * (t - k + 1) * (1 - k / t)
        roll = np.convolve(x, np.ones(k), mode="valid")  # overlapping k-sums
        vark = ((roll - k * mu) ** 2).sum() / m
        vr = vark / var1
        theta = 0.0
        for j in range(1, k):
            delta = (sq[j:] * sq[:-j]).sum() / denom
            theta += (2 * (k - j) / k) ** 2 * delta
        m2 = (vr - 1) / np.sqrt(theta) if theta > 0 else np.nan
        vrs.append(vr)
        m2s.append(m2)
    return np.array(vrs), np.array(m2s)


def variance_ratio_test(
    returns: np.ndarray,
    horizons: tuple[int, ...],
    n_boot: int = 4999,
    seed: int = 42,
) -> VarianceRatioResult:
    """Wild-bootstrap (Rademacher) VR test, joint over `horizons`."""
    x = np.asarray(returns, dtype=float)
    x = x[np.isfinite(x)]
    vr, m2 = _vr_m2(x, horizons)
    mv = np.max(np.abs(m2))
    rng = np.random.default_rng(seed)
    boot_m2 = np.empty((n_boot, len(horizons)))
    for b in range(n_boot):
        eta = rng.integers(0, 2, size=x.size) * 2 - 1
        _, m2b = _vr_m2(x * eta, horizons)
        boot_m2[b] = m2b
    boot_mv = np.max(np.abs(boot_m2), axis=1)
    p_joint = (1 + (boot_mv >= mv).sum()) / (n_boot + 1)
    p_h = tuple(
        float((1 + (np.abs(boot_m2[:, i]) >= abs(m2[i])).sum()) / (n_boot + 1))
        for i in range(len(horizons))
    )
    return VarianceRatioResult(
        horizons=tuple(horizons),
        vr=tuple(float(v) for v in vr),
        m2=tuple(float(z) for z in m2),
        p_horizon=p_h,
        joint_stat=float(mv),
        p_joint=float(p_joint),
        n=x.size,
    )


@dataclass(frozen=True)
class ConditionalAcResult:
    groups: tuple[str, ...]
    n_per_group: tuple[int, ...]
    slope: tuple[float, ...]  # b_g in r_{t+1} = a_g + b_g r_t per group
    mean_abs_r: tuple[float, ...]  # mean |r_t| per group (dampening footprint)
    stdev_r: tuple[float, ...]
    delta_b: float  # b_top - b_bottom
    p_one_sided: float  # wild-bootstrap P(delta_b* <= delta_b) under common-slope null
    n: int


def _group_slopes(
    r_lag: np.ndarray, r_next: np.ndarray, gid: np.ndarray, n_groups: int
) -> np.ndarray:
    slopes = np.full(n_groups, np.nan)
    for g in range(n_groups):
        m = gid == g
        if m.sum() < 3:
            continue
        xg, yg = r_lag[m], r_next[m]
        xc = xg - xg.mean()
        slopes[g] = (xc * (yg - yg.mean())).sum() / (xc**2).sum()
    return slopes


def conditional_autocorrelation(
    r_lag: np.ndarray,
    r_next: np.ndarray,
    group_id: np.ndarray,
    group_names: tuple[str, ...],
    bottom: int,
    top: int,
    n_boot: int = 4999,
    seed: int = 42,
) -> ConditionalAcResult:
    """Per-regime lag-1 slope of r_next on r_lag; wild-bootstrap test of
    delta_b = b[top] - b[bottom] < 0 under the common-slope null."""
    keep = np.isfinite(r_lag) & np.isfinite(r_next) & (group_id >= 0)
    x, y, gid = r_lag[keep], r_next[keep], group_id[keep].astype(int)
    n_groups = len(group_names)
    slopes = _group_slopes(x, y, gid, n_groups)
    delta = slopes[top] - slopes[bottom]

    # Restricted (null) model: per-group intercept, one common slope.
    xc = x - np.array([x[gid == g].mean() for g in range(n_groups)])[gid]
    yc = y - np.array([y[gid == g].mean() for g in range(n_groups)])[gid]
    b_common = (xc * yc).sum() / (xc**2).sum()
    fitted = y - yc + b_common * xc
    resid = y - fitted

    rng = np.random.default_rng(seed)
    boot = np.empty(n_boot)
    for b in range(n_boot):
        eta = rng.integers(0, 2, size=y.size) * 2 - 1
        yb = fitted + eta * resid
        sb = _group_slopes(x, yb, gid, n_groups)
        boot[b] = sb[top] - sb[bottom]
    p = (1 + (boot <= delta).sum()) / (n_boot + 1)

    return ConditionalAcResult(
        groups=group_names,
        n_per_group=tuple(int((gid == g).sum()) for g in range(n_groups)),
        slope=tuple(float(s) for s in slopes),
        mean_abs_r=tuple(float(np.abs(y[gid == g]).mean()) for g in range(n_groups)),
        stdev_r=tuple(float(y[gid == g].std(ddof=1)) for g in range(n_groups)),
        delta_b=float(delta),
        p_one_sided=float(p),
        n=int(y.size),
    )


def rolling_percentile_rank(values: np.ndarray, window: int, min_obs: int) -> np.ndarray:
    """Percentile rank of each value within its trailing `window` (inclusive)."""
    out = np.full(values.size, np.nan)
    for i in range(values.size):
        lo = max(0, i - window + 1)
        past = values[lo : i + 1]
        if past.size < min_obs:
            continue
        out[i] = (past <= values[i]).mean()
    return out


def terciles(percentile: np.ndarray) -> np.ndarray:
    """Map percentile ranks to group ids 0/1/2 (bottom/mid/top); NaN -> -1."""
    gid = np.full(percentile.size, -1)
    gid[np.isfinite(percentile) & (percentile < 1 / 3)] = 0
    gid[np.isfinite(percentile) & (percentile >= 1 / 3) & (percentile < 2 / 3)] = 1
    gid[np.isfinite(percentile) & (percentile >= 2 / 3)] = 2
    return gid
