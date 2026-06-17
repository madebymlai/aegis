"""Load a declarative ``book.toml`` into a domain :class:`BookConfig`.

A *deep* module: the TOML file format — which keys map to which BookConfig
fields, how the ``[[sleeves]]`` and ``[[band_overrides]]`` arrays-of-tables
decode — lives only here (information hiding).  The domain ``BookConfig`` stays
a plain, Nautilus-free dataclass and keeps its own structural invariants
(``__post_init__``), which this loader simply lets surface.

This is the *only* operator-facing way to declare a book; ``base_currency`` and
the sleeves' bundle wheels are read here, never hand-built in production code.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path

from aegis_trader.domain.book_config import (
    BookConfig,
    CostModelConfig,
    BorrowConfig,
    MarginInterestConfig,
    ConvexityBudgetCandidate,
    DrawdownDeleverCurve,
    RiskGroup,
    SleeveConfig,
    TailConvexityBudget,
)
from aegis_trader.domain.types import SleeveName


_BOOK_FILENAME = "book.toml"


class BookConfigError(ValueError):
    """A ``book.toml`` could not be found, read, or decoded into a BookConfig."""


def find_book_config(start: str | Path | None = None) -> Path:
    """Discover ``book.toml`` by walking up from *start* (default cwd).

    Returns the first ``book.toml`` found in *start* or any ancestor directory;
    fails closed with :class:`BookConfigError` if none exists up to the
    filesystem root.  Lets an operator run ``aegis-trader`` from anywhere inside
    a deployment tree without naming the spec explicitly.
    """
    start = Path.cwd() if start is None else Path(start)
    for directory in (start, *start.parents):
        candidate = directory / _BOOK_FILENAME
        if candidate.is_file():
            return candidate
    raise BookConfigError(
        f"no {_BOOK_FILENAME} found in {str(start)!r} or any parent directory"
    )


def load_book_config(path: str | Path) -> BookConfig:
    """Deserialize the ``book.toml`` at *path* into a :class:`BookConfig`.

    Fails closed: a missing file, malformed TOML, or a missing required sleeve
    key raises :class:`BookConfigError` naming the file; structural violations
    (no sleeves, duplicate names, invalid risk controls) surface as the
    BookConfig's own ``ValueError``.
    """
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise BookConfigError(f"cannot read book config {str(path)!r}: {exc}") from exc
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise BookConfigError(f"malformed book config {str(path)!r}: {exc}") from exc

    try:
        sleeves = tuple(
            SleeveConfig(
                name=SleeveName(s["name"]),
                wheel_filename=s["wheel_filename"],
                risk_share=float(s["risk_share"]),
                group=RiskGroup(s["group"]),
                weight_band_down=float(s.get("weight_band_down", 0.0)),
                weight_band_up=float(s.get("weight_band_up", 0.0)),
            )
            for s in data.get("sleeves", [])
        )
        band_overrides = tuple(
            (o["figi"], float(o["band_up"]), float(o["band_down"]))
            for o in data.get("band_overrides", [])
        )
        drawdown_delever = _drawdown_delever_curve(data.get("drawdown_delever"))
        tail_convexity_budget = _parse_tail_convexity_budget(data)
        costs = _parse_costs(data.get("costs"))
        starting_balances = _parse_starting_balances(data.get("starting_balances"))
    except (KeyError, TypeError, ValueError) as exc:
        raise BookConfigError(
            f"book config {str(path)!r} has a malformed sleeve/band/tail/cost entry: {exc}"
        ) from exc

    return BookConfig(
        sleeves=sleeves,
        base_currency=data.get("base_currency", "EUR"),
        book_vol_target=float(data.get("book_vol_target", 0.09)),
        sleeve_reversion_fraction=float(data.get("sleeve_reversion_fraction", 1.0)),
        max_book_gross=float(data.get("max_book_gross", 1.0)),
        gross_cap=data.get("gross_cap"),
        net_cap=data.get("net_cap"),
        per_name_cap=data.get("per_name_cap"),
        default_band_up=float(data.get("default_band_up", 0.02)),
        default_band_down=float(data.get("default_band_down", 0.02)),
        band_overrides=band_overrides,
        tail_convexity_budget=tail_convexity_budget,
        costs=costs,
        starting_balances=starting_balances,
        aggregate_drift_threshold=data.get("aggregate_drift_threshold"),
        drawdown_delever=drawdown_delever,
    )


def _parse_starting_balances(raw: object) -> tuple[tuple[str, float], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, Mapping):
        raise TypeError("starting_balances must be a TOML table")
    return tuple((str(currency), float(amount)) for currency, amount in raw.items())


def _parse_costs(raw: object) -> CostModelConfig:
    if raw is None:
        return CostModelConfig.zero()
    if not isinstance(raw, Mapping):
        raise TypeError("costs must be a TOML table")
    return CostModelConfig(
        per_share_commission=float(raw.get("per_share_commission", 0.0)),
        min_commission_per_order=float(raw.get("min_commission_per_order", 0.0)),
        max_commission_pct=float(raw.get("max_commission_pct", 0.0)),
        slippage_probability=float(raw.get("slippage_probability", 0.0)),
        slippage_seed=raw.get("slippage_seed", 0),
        margin_interest=MarginInterestConfig.from_mapping(
            raw.get("margin_interest", {})
        ),
        borrow=BorrowConfig.from_mapping(raw.get("borrow", {})),
    )


def _drawdown_delever_curve(raw: object) -> DrawdownDeleverCurve | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise TypeError("drawdown_delever must be a TOML table")
    return DrawdownDeleverCurve(
        start_drawdown=float(raw["start_drawdown"]),
        end_drawdown=float(raw["end_drawdown"]),
        floor_multiplier=float(raw["floor_multiplier"]),
    )


def _parse_tail_convexity_budget(
    data: Mapping[str, object],
) -> TailConvexityBudget | None:
    raw_budget = data.get("tail_convexity_budget")
    if raw_budget is None:
        return None
    if not isinstance(raw_budget, Mapping):
        raise TypeError("tail_convexity_budget must be a table")

    raw_carry_budget = raw_budget.get("annual_carry_budget")
    return TailConvexityBudget(
        attachment=float(raw_budget["attachment"]),
        coverage_target=float(raw_budget["coverage_target"]),
        annual_carry_budget=(
            None if raw_carry_budget is None else float(raw_carry_budget)
        ),
        candidates=tuple(
            _parse_tail_candidate(candidate)
            for candidate in raw_budget.get("candidates", [])
        ),
    )


def _parse_tail_candidate(candidate: object) -> ConvexityBudgetCandidate:
    if not isinstance(candidate, Mapping):
        raise TypeError("tail_convexity_budget candidates must be tables")
    return ConvexityBudgetCandidate(
        sleeve=SleeveName(candidate["sleeve"]),
        payoff_at_attachment=float(candidate["payoff_at_attachment"]),
        annual_carry=float(candidate["annual_carry"]),
        crisis_reliability=float(candidate["crisis_reliability"]),
        capacity_risk_share=float(candidate["capacity_risk_share"]),
    )
