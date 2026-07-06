import math

import pytest
from numba import njit

from aegis_runtime import debit_interest


@pytest.mark.parametrize(
        ("cash", "rate", "elapsed_days", "expected"),
        [
            (100.0, 0.05, 1.0, 0.0),
            (0.0, 0.05, 1.0, 0.0),
            (-100.0, 0.05, 30.0, 0.4166666666666667),
            (-100.0, 0.05, 0.0, 0.0),
            (-100.0, 0.05, -1.0, 0.0),
        ],
)
def test_debit_interest_charges_negative_cash_only(
    cash: float,
    rate: float,
    elapsed_days: float,
    expected: float,
) -> None:
    assert debit_interest(cash, rate, elapsed_days) == pytest.approx(expected)


def test_debit_interest_is_finite_for_finite_inputs() -> None:
    assert math.isfinite(debit_interest(-1_000_000.0, 0.0324, 3.0))


def test_debit_interest_compiles_under_numba() -> None:
    @njit
    def compiled_call() -> float:
        return debit_interest(-750_000.0, 0.0324, 3.0)

    assert compiled_call() == pytest.approx(202.5)
