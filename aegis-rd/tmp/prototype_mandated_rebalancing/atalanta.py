"""PROTOTYPE (throwaway) — bridge to the repository's Atalanta return stream.

Uses the production reproduction path (`scripts.floor_evaluation.
load_locked_strategy_returns`) on the locked trend_floor config, and the
repository's established whole-book measure (`evaluate_floor_pair`: fixed
monthly mix, MPPM certainty equivalent at risk aversion 3, dependence summary,
block bootstrap). No fabricated proxy: if the locked stream cannot be
reproduced, pairing is reported as unavailable.

Caveat carried into every report: Atalanta's stream is EUR-based net returns
from the production simulator; the candidate is a USD futures excess-return
overlay. The comparison is a same-dates monthly alignment, not a currency-
consistent book simulation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

RD_ROOT = Path(__file__).resolve().parents[2]
ATALANTA_CONFIG = RD_ROOT / "research" / "configs" / "atalanta" / "trend_floor.yaml"
CACHE = Path(__file__).resolve().parent / "data_cache" / "atalanta_returns.csv"


def _bootstrap_path() -> None:
    if str(RD_ROOT) not in sys.path:
        sys.path.insert(0, str(RD_ROOT))


def load_atalanta_daily(refresh: bool = False) -> pd.Series | None:
    """Locked Atalanta net daily returns, cached after first reproduction."""
    if CACHE.exists() and not refresh:
        frame = pd.read_csv(CACHE, parse_dates=["date"], index_col="date")
        return frame["atalanta"]
    _bootstrap_path()
    try:
        from scripts.floor_evaluation import load_locked_strategy_returns

        locked = load_locked_strategy_returns(ATALANTA_CONFIG)
    except Exception as error:  # noqa: BLE001 - prototype: report and continue
        print(f"[atalanta] reproduction unavailable: {type(error).__name__}: {error}")
        return None
    returns = locked.returns.rename("atalanta")
    CACHE.parent.mkdir(exist_ok=True)
    returns.rename_axis("date").to_csv(CACHE)
    print(
        f"[atalanta] reproduced locked stream {locked.config_name} "
        f"({locked.lock_run_id}): {len(returns)} days "
        f"{returns.index[0].date()}..{returns.index[-1].date()}"
    )
    return returns


def evaluate_pairing(
    atalanta_daily: pd.Series, candidate_daily: pd.Series
) -> dict[str, Any]:
    """The repository's floor-pair evaluation with the candidate in the mix seat."""
    _bootstrap_path()
    from scripts.floor_evaluation import _complete_monthly_returns, evaluate_floor_pair

    joined = pd.concat(
        [atalanta_daily.rename("atalanta"), candidate_daily.rename("candidate")],
        axis=1,
        join="inner",
    ).dropna()
    atalanta_monthly = _complete_monthly_returns(joined["atalanta"])
    candidate_monthly = _complete_monthly_returns(joined["candidate"])
    return evaluate_floor_pair(atalanta_monthly, candidate_monthly)
