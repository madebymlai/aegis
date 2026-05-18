import numpy as np
import pandas as pd

from research.aegis_research.config import SignalConfig
from research.aegis_research.model_contracts import POSITIVE_CLASS_PROBABILITY
from research.aegis_research.signals import SignalResult, probabilities_to_signals


def test_probabilities_to_signals_uses_strict_hysteresis_thresholds() -> None:
    probabilities = pd.DataFrame(
        {"SYN": [0.56, 0.55, 0.525, 0.50, 0.49]},
        index=pd.date_range("2024-01-01", periods=5),
    )

    result = probabilities_to_signals(probabilities, SignalConfig())

    assert isinstance(result, SignalResult)
    assert result.entries["SYN"].tolist() == [True, False, False, False, False]
    assert result.exits["SYN"].tolist() == [False, False, False, False, True]
    assert result.diagnostics["counts"]["by_symbol"]["SYN"]["raw_entry_states"] == 1
    assert result.diagnostics["counts"]["by_symbol"]["SYN"]["raw_exit_states"] == 1


def test_nan_probabilities_emit_no_signal_and_increment_missing_counts() -> None:
    probabilities = pd.DataFrame(
        {
            "AAA": [0.60, np.nan, 0.40],
            "BBB": [np.nan, 0.20, 0.80],
        },
        index=pd.date_range("2024-01-01", periods=3),
    )

    result = probabilities_to_signals(
        probabilities,
        SignalConfig(),
        split_id="split_0",
        set_name="test",
    )

    assert result.entries.loc[:, "AAA"].tolist() == [True, False, False]
    assert result.exits.loc[:, "BBB"].tolist() == [False, True, False]
    assert result.diagnostics["split_id"] == "split_0"
    assert result.diagnostics["set_name"] == "test"
    assert result.diagnostics["counts"]["missing_probabilities"] == 2
    assert result.diagnostics["counts"]["by_symbol"]["AAA"]["missing_probabilities"] == 1
    assert result.diagnostics["counts"]["by_symbol"]["BBB"]["missing_probabilities"] == 1


def test_repeated_raw_threshold_states_are_cleaned_only_for_diagnostics() -> None:
    probabilities = pd.DataFrame(
        {"SYN": [0.90, 0.80, 0.70, 0.10]},
        index=pd.date_range("2024-01-01", periods=4),
    )

    result = probabilities_to_signals(probabilities, SignalConfig())

    counts = result.diagnostics["counts"]["by_symbol"]["SYN"]
    cleaned_counts = result.diagnostics["cleaned_diagnostics"]["by_symbol"]["SYN"]

    assert result.entries["SYN"].tolist() == [True, True, True, False]
    assert counts["raw_entry_states"] == 3
    assert cleaned_counts["clean_entry_states"] == 1
    assert cleaned_counts["clean_exit_states"] == 1
    assert result.diagnostics["cleaned_diagnostics"]["diagnostics_only"] is True


def test_signal_diagnostics_preserve_probability_metadata() -> None:
    probabilities = pd.DataFrame(
        {"SYN": [0.60]},
        index=pd.date_range("2024-01-01", periods=1),
    )

    result = probabilities_to_signals(
        probabilities,
        SignalConfig(execution_timing="same_close"),
        probability_metadata={
            "output_name": POSITIVE_CLASS_PROBABILITY,
            "positive_class": 1,
            "calibrated": False,
        },
    )

    assert result.diagnostics["policy"]["name"] == "long_only_hysteresis"
    assert result.diagnostics["policy"]["long_entry_threshold"] == 0.55
    assert result.diagnostics["execution"]["timing"] == "same_close"
    assert result.diagnostics["probability"]["source_output_name"] == POSITIVE_CLASS_PROBABILITY
    assert result.diagnostics["probability"]["positive_class"] == 1
    assert result.diagnostics["probability"]["calibrated"] is False


def test_simultaneous_raw_states_are_counted_when_masks_overlap() -> None:
    probabilities = pd.DataFrame(
        {"SYN": [0.50]},
        index=pd.date_range("2024-01-01", periods=1),
    )
    invalid_unvalidated_config = SignalConfig(
        long_entry_threshold=0.40,
        long_exit_threshold=0.60,
    )

    result = probabilities_to_signals(probabilities, invalid_unvalidated_config)

    assert result.entries.loc[:, "SYN"].tolist() == [True]
    assert result.exits.loc[:, "SYN"].tolist() == [True]
    assert result.diagnostics["counts"]["simultaneous_entry_exit_states"] == 1
