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
from pathlib import Path

from aegis_trader.domain.book_config import BookConfig, RiskGroup, SleeveConfig
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
    (no sleeves, duplicate names, over-budget gross) surface as the BookConfig's
    own ``ValueError``.
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
            )
            for s in data.get("sleeves", [])
        )
        band_overrides = tuple(
            (o["figi"], float(o["band_up"]), float(o["band_down"]))
            for o in data.get("band_overrides", [])
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise BookConfigError(
            f"book config {str(path)!r} has a malformed sleeve/band entry: {exc}"
        ) from exc

    return BookConfig(
        sleeves=sleeves,
        base_currency=data.get("base_currency", "EUR"),
        book_vol_target=float(data.get("book_vol_target", 0.09)),
        max_book_gross=float(data.get("max_book_gross", 1.0)),
        gross_cap=data.get("gross_cap"),
        net_cap=data.get("net_cap"),
        per_name_cap=data.get("per_name_cap"),
        default_band_up=float(data.get("default_band_up", 0.02)),
        default_band_down=float(data.get("default_band_down", 0.02)),
        band_overrides=band_overrides,
        aggregate_drift_threshold=data.get("aggregate_drift_threshold"),
    )
