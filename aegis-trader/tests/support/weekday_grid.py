"""Weekday-only observation timestamps for ledger-driving fixtures.

Daily bars never stamp weekends, so fixtures that walk consecutive "days"
must walk weekdays — otherwise the weekend fold (aegis-rd-cy7l) merges their
Saturday/Sunday stamps into Monday's bucket and the fixture stops resembling
any real Book.
"""

from __future__ import annotations

_DAY_NS = 86_400_000_000_000


def weekday_ns(index: int) -> int:
    """The *index*-th weekday since Monday 1970-01-05, as a UTC timestamp."""
    weeks, weekday = divmod(index, 5)
    return (4 + weeks * 7 + weekday) * _DAY_NS
