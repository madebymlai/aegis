"""Shared validation for bare continuous-future root symbols.

A continuous-future root is a *bare* symbol (e.g. ``"ES"``), the ``Symbol`` half of the
materialised continuous-root ``InstrumentId`` (``ES.XCME``) that aegis-data builds downstream
from the dated legs (the venue is catalog-authoritative).  Research (``DataConfig.futures``)
and live (``DataContract.futures``) declare roots as plain strings — exactly as both declare
native ids as strings — and validate them through this one function so a venue-qualified id is
rejected identically on both sides.
"""

from __future__ import annotations

import re

# A bare root is letters/digits (plus ``_``/``-``) with NO ``.`` — so it cannot be a
# venue-qualified id (``ES.XCME``) and cannot smuggle whitespace or separators.
_BARE_ROOT_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def validate_bare_root(value: str) -> str:
    """Return *value* if it is a bare continuous-future root, else raise ``ValueError``.

    Validated *positively* against a pattern (not via a caught parse error), so a config typo
    like ``"ES."`` or ``"ES "`` fails here rather than sailing through to blow up later when
    aegis-data builds ``Symbol(root)``.  A venue-qualified id (``"ES.XCME"``) carries a ``.``
    separator and is an id, not a root.
    """
    if not isinstance(value, str) or not _BARE_ROOT_RE.fullmatch(value):
        raise ValueError(
            f"continuous-future root {value!r} must be a bare root symbol like 'ES' "
            "(letters/digits only, no venue separator) — not a venue-qualified id or "
            "malformed/whitespaced string"
        )
    return value
