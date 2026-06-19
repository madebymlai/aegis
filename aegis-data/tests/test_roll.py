"""Pure futures roll schedule (aegis-rd-clz.2).

A continuous back-adjusted series needs to know which dated contracts make up the
chain and when the position rolls from one to the next.  For a quarterly index
future (ES: H/M/U/Z, expiry on the third Friday) the calendar rule is pure: roll
a fixed number of business days before each contract's expiry.
"""

from __future__ import annotations

from datetime import date

from aegis_data.roll import quarterly_roll_schedule


def test_quarterly_schedule_lists_contracts_expiries_and_roll_dates() -> None:
    sched = quarterly_roll_schedule("ES", date(2024, 1, 1), date(2024, 12, 31), roll_lead_days=5)

    # 2024 quarterly cycle: Mar(H), Jun(M), Sep(U), Dec(Z).
    assert sched.symbols == ("ESH4", "ESM4", "ESU4", "ESZ4")
    # Third Friday of March 2024 is the 15th.
    assert sched.expiries[0] == date(2024, 3, 15)
    # One roll per seam (n-1).
    assert len(sched.roll_dates) == 3
    # Roll 5 business days before expiry: Fri 03-15 → Thu 14, Wed 13, Tue 12, Mon 11, Fri 08.
    assert sched.roll_dates[0] == date(2024, 3, 8)


def test_quarterly_schedule_crosses_year_boundary() -> None:
    sched = quarterly_roll_schedule("ES", date(2024, 6, 1), date(2025, 4, 1), roll_lead_days=5)

    # Mar 2024 (H4) expires before the start and is excluded; Jun 2025 (M5)
    # expires after the end and is excluded.  The chain rolls 2024→2025.
    assert sched.symbols == ("ESM4", "ESU4", "ESZ4", "ESH5")
    assert sched.expiries[-1] == date(2025, 3, 21)  # third Friday March 2025
    assert len(sched.roll_dates) == 3
    assert list(sched.roll_dates) == sorted(sched.roll_dates)  # chronological
