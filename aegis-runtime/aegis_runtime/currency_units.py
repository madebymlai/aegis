"""Minor-unit quote currencies (e.g. GBp = pence of GBP).

A minor unit prices in a fixed fraction of a major currency. Nautilus models no
such link — its ``Currency`` carries only code/type/iso4217/name/precision and
does not even register ``GBp`` — so this is the single place the fact lives.
Both the read-side FX conversion (:mod:`aegis_runtime.currency`) and the trader's
order sizing (``aegis_trader.domain.sizing``) resolve the factor here, so the two
engines cannot drift. Deliberately Nautilus-free: a currency code is a plain
string, because Nautilus offers nothing to derive this from.
"""

from __future__ import annotations

# Minor-unit code -> (major currency code, minor units per one major unit).
# GBp is penny sterling: 100 pence to the pound. Add further sub-units here and
# both engines inherit them.
_MINOR_UNITS: dict[str, tuple[str, int]] = {"GBp": ("GBP", 100)}


def resolve_quote_currency(code: str) -> tuple[str, float]:
    """Resolve a quote-currency code to ``(major currency, minor units per major)``.

    A minor unit (``"GBp"``) resolves to its major (``"GBP"``) and how many minor
    units make up one major unit (``100.0``). Any other code is its own upper-cased
    major with factor ``1.0`` — it *is* the major unit. Multiply a major-currency
    amount by the factor to express it in the native minor unit; divide a native
    amount by it to express it in the major.
    """
    major, minor_per_major = _MINOR_UNITS.get(code, (code, 1))
    return major.upper(), float(minor_per_major)
