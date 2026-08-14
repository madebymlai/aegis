"""Environmental fault boundary for synchronous historical providers."""

from collections.abc import Iterator
from contextlib import contextmanager


class GapFillProviderError(RuntimeError):
    """A provider failed environmentally while filling a Catalog gap."""


_CAUSE_SUMMARY_LIMIT = 200


@contextmanager
def gap_fill_boundary(subject: str) -> Iterator[None]:
    """Name the failed provider subject while preserving the original cause."""
    try:
        yield
    except Exception as exc:
        first_line = str(exc).splitlines()[0] if str(exc) else ""
        if len(first_line) > _CAUSE_SUMMARY_LIMIT:
            first_line = first_line[:_CAUSE_SUMMARY_LIMIT] + "…"
        raise GapFillProviderError(
            f"the gap-fill provider could not serve {subject}: "
            f"{type(exc).__name__}: {first_line}"
        ) from exc


__all__ = ["GapFillProviderError", "gap_fill_boundary"]
