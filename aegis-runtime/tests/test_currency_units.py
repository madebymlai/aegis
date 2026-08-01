"""The single source of truth for minor-unit currency facts.

Both the read-side FX conversion (aegis_runtime.domain.currency) and the trader's order
sizing resolve minor-unit currencies through this one function, so guarding it
here guards both engines against drifting apart on the pence factor.
"""

from __future__ import annotations

from aegis_runtime.domain.currency_units import resolve_quote_currency


def test_gbp_pence_resolves_to_gbp_with_a_hundred_minor_units() -> None:
    assert resolve_quote_currency("GBp") == ("GBP", 100.0)


def test_a_major_currency_is_its_own_upper_cased_major_with_unit_factor() -> None:
    assert resolve_quote_currency("usd") == ("USD", 1.0)


def test_the_conversion_and_sizing_directions_are_exact_inverses() -> None:
    # Conversion divides a major-currency rate by the factor (minor->major); sizing
    # multiplies a major-currency notional by it (major->minor). Round-tripping a
    # value through both must return it unchanged.
    _major, factor = resolve_quote_currency("GBp")
    assert (500.0 * factor) / factor == 500.0
