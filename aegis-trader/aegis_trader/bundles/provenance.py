"""Cap provenance — assert a Book Config's exposure caps never exceed what
research validated for the sleeves' backing bundles.

The validated ceiling is each sleeve's ``ExecutionBundle`` plan
(``gross_cap``/``net_cap``) — the only manifest-grounded source.  This replaces
the earlier self-referential check that compared an operator-entered
``research_validated_cap`` against the operator's own ``per_name_cap`` (a4).

Pure (no Nautilus, no I/O); called at load once each sleeve's bundle is known.
"""

from __future__ import annotations

from collections.abc import Mapping

from aegis_runtime import ExecutionBundle

from aegis_trader.domain.book_config import BookConfig
from aegis_trader.domain.types import SleeveName

_TOLERANCE = 1e-9


class CapProvenanceError(ValueError):
    """A Book Config cap exceeds its sleeve bundle's research-validated cap."""


def check_cap_provenance(
    book: BookConfig, bundles: Mapping[SleeveName, ExecutionBundle]
) -> None:
    """Raise if any of *book*'s caps exceed a sleeve bundle's validated caps."""
    for sleeve in book.sleeves:
        bundle = bundles.get(sleeve.name)
        if bundle is None:
            raise CapProvenanceError(
                f"no bundle loaded for sleeve {sleeve.name.value!r}; "
                f"cannot ground its caps"
            )
        if book.gross_cap is not None and book.gross_cap > bundle.gross_cap + _TOLERANCE:
            raise CapProvenanceError(
                f"book gross_cap ({book.gross_cap}) exceeds sleeve "
                f"{sleeve.name.value!r} bundle gross_cap ({bundle.gross_cap})"
            )
        # A plan with no explicit net_cap bounds net exposure only by its gross
        # cap (mirrors aegis_runtime.validate_exposure), so gross is the ceiling.
        net_ceiling = bundle.net_cap if bundle.net_cap is not None else bundle.gross_cap
        if book.net_cap is not None and book.net_cap > net_ceiling + _TOLERANCE:
            raise CapProvenanceError(
                f"book net_cap ({book.net_cap}) exceeds sleeve "
                f"{sleeve.name.value!r} bundle net cap ({net_ceiling})"
            )
        # No per-name research cap exists in the contract; a single name's
        # exposure is a component of gross, so the validated gross is its ceiling.
        if book.per_name_cap is not None and book.per_name_cap > bundle.gross_cap + _TOLERANCE:
            raise CapProvenanceError(
                f"book per_name_cap ({book.per_name_cap}) exceeds sleeve "
                f"{sleeve.name.value!r} bundle gross_cap ({bundle.gross_cap})"
            )
