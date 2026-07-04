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
    ("realized", "target", "fraction", "expected"),
    [
        # Add-side breach (down band 0.02): destination interpolates edge -> target.
        (0.47, 0.50, 0.0, 0.48),
        (0.47, 0.50, 0.5, 0.49),
        (0.47, 0.50, 1.0, 0.50),
        # Trim-side breach (up band 0.02).
        (0.53, 0.50, 0.0, 0.52),
        (0.53, 0.50, 0.5, 0.51),
        (0.53, 0.50, 1.0, 0.50),
    ],
)
def test_gate_breach_stops_at_destination_fraction(
    realized: float,
    target: float,
    fraction: float,
    expected: float,
) -> None:
    assert gate(realized, target, 0.02, 0.02, fraction) == pytest.approx(expected)


def test_gate_destination_lands_inside_the_band() -> None:
    resolved = gate(0.40, 0.50, 0.02, 0.02, 0.25)

    assert resolved == pytest.approx(0.485)
    # The residual drift sits inside the band, so the next gate call holds.
    assert gate(resolved, 0.50, 0.02, 0.02, 0.25) == pytest.approx(resolved)


def test_gate_within_band_holds_regardless_of_destination_fraction() -> None:
    assert gate(0.49, 0.50, 0.02, 0.02, 0.0) == pytest.approx(0.49)


def test_gate_zero_band_trades_to_target_regardless_of_destination_fraction() -> None:
    assert gate(0.40, 0.50, 0.0, 0.0, 0.0) == pytest.approx(0.50)


def test_drift_band_resolve_uses_own_destination_fraction() -> None:
    band = DriftBand.symmetric(0.02, destination_fraction=0.5)

    assert band.resolve(realized=0.47, target=0.50) == pytest.approx(0.49)


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


@pytest.mark.parametrize("fraction", [-0.01, 1.01, float("nan"), float("inf")])
def test_drift_band_rejects_invalid_destination_fraction(fraction: float) -> None:
    with pytest.raises(ValueError, match="destination_fraction"):
        DriftBand(up=0.02, down=0.02, destination_fraction=fraction)
