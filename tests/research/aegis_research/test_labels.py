import pandas as pd

from research.aegis_research.config import LabelConfig
from research.aegis_research.labels import build_labels


def test_fixlb_labels_match_forward_returns() -> None:
    close = pd.Series([1.0, 2.0, 3.0, 2.0, 4.0])
    forward_return = close.shift(-2) / close - 1
    expected = (forward_return > 0.0).astype("Int8").rename("label")
    expected[forward_return.isna()] = pd.NA

    fixlb_labels = build_labels(
        close,
        LabelConfig(kind="fixlb", horizon=2, threshold=0.0),
    )

    pd.testing.assert_series_equal(fixlb_labels, expected)


def test_trendlb_labels_are_binary() -> None:
    close = pd.Series([1.0, 2.0, 3.0, 2.0, 1.0, 2.0, 3.0, 4.0, 3.0, 2.0])
    labels = build_labels(
        close,
        LabelConfig(kind="trendlb", up_th=0.2, down_th=0.2, mode="binary"),
        high=close * 1.01,
        low=close * 0.99,
    )

    assert set(labels.dropna().unique()) <= {0, 1}


def test_pivotlb_labels_use_configured_positive_value() -> None:
    close = pd.Series([1.0, 2.0, 3.0, 2.0, 1.0, 2.0, 3.0, 4.0, 3.0, 2.0])
    labels = build_labels(
        close,
        LabelConfig(kind="pivotlb", up_th=0.2, down_th=0.2, positive_value=-1),
        high=close * 1.01,
        low=close * 0.99,
    )

    assert set(labels.dropna().unique()) <= {0, 1}
    assert labels.sum() > 0
