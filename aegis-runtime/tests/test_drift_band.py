import pytest

from aegis_runtime.drift_band import DriftBand, gate


@pytest.mark.parametrize(
    ("realized", "target", "up", "down", "expected"),
    [
        (0.48, 0.50, 0.02, 0.02, 0.48),
        (0.52, 0.50, 0.02, 0.02, 0.52),
        (0.47, 0.50, 0.02, 0.02, 0.50),
        (0.53, 0.50, 0.02, 0.02, 0.50),
        (0.00, 0.03, 0.02, 0.02, 0.03),
        (0.00, 0.01, 0.02, 0.02, 0.00),
        (0.48, 0.50, 0.01, 0.05, 0.48),
        (0.52, 0.50, 0.01, 0.05, 0.50),
        (0.48, 0.50, 0.00, 0.00, 0.50),
        (0.52, 0.50, 0.00, 0.00, 0.50),
    ],
)
def test_gate_resolves_hold_or_trade_by_directional_width(
    realized: float,
    target: float,
    up: float,
    down: float,
    expected: float,
) -> None:
    assert gate(realized, target, up, down) == pytest.approx(expected)


def test_drift_band_symmetric_resolves_through_gate() -> None:
    band = DriftBand.symmetric(0.02)

    assert band.resolve(realized=0.48, target=0.50) == pytest.approx(0.48)
    assert band.resolve(realized=0.47, target=0.50) == pytest.approx(0.50)


@pytest.mark.parametrize(
    ("up", "down"),
    [
        (-0.01, 0.01),
        (0.01, -0.01),
        (float("nan"), 0.01),
        (0.01, float("inf")),
    ],
)
def test_drift_band_rejects_invalid_widths(up: float, down: float) -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        DriftBand(up=up, down=down)
