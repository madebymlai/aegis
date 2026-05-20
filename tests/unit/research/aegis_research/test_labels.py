import pandas as pd

from research.aegis_research.labels import (
    LabelConfig,
    LabelGeneratorConfig,
    LabelTargetConfig,
    LabelTargetSelectionConfig,
    LabelTargetTransformConfig,
    build_label_result,
    build_labels,
)


def test_fixlb_labels_match_forward_returns() -> None:
    close = pd.DataFrame({"SYN": [1.0, 2.0, 3.0, 2.0, 4.0]})
    forward_return = close.shift(-2) / close - 1
    expected = (forward_return > 0.0).astype("Int8")
    expected[forward_return.isna()] = pd.NA

    fixlb_labels = build_labels(
        close,
        _label_config("fixlb", {"n": 2}, "threshold_future_return", {"threshold": 0.0}),
    )

    pd.testing.assert_frame_equal(fixlb_labels, expected)


def test_trendlb_labels_are_binary() -> None:
    close = pd.DataFrame({"SYN": [1.0, 2.0, 3.0, 2.0, 1.0, 2.0, 3.0, 4.0, 3.0, 2.0]})
    labels = build_labels(
        close,
        _label_config(
            "trendlb",
            {"up_th": 0.2, "down_th": 0.2, "mode": "binary"},
            "identity_binary",
            {"positive_value": 1},
        ),
        high=close * 1.01,
        low=close * 0.99,
    )

    assert set(labels.stack().dropna().unique()) <= {0, 1}


def test_pivotlb_labels_use_configured_positive_value() -> None:
    close = pd.DataFrame({"SYN": [1.0, 2.0, 3.0, 2.0, 1.0, 2.0, 3.0, 4.0, 3.0, 2.0]})
    result = build_label_result(
        close,
        _label_config(
            "pivotlb",
            {"up_th": 0.2, "down_th": 0.2},
            "positive_event",
            {"positive_value": -1},
        ),
        high=close * 1.01,
        low=close * 0.99,
    )
    selected_native = result.native_labels.iloc[:, [0]].copy()
    selected_native.columns = result.labels.columns
    expected = (selected_native == -1).astype("Int8").mask(selected_native.isna(), pd.NA)

    pd.testing.assert_frame_equal(result.labels, expected)
    assert set(result.labels.stack().dropna().unique()) <= {0, 1}
    assert result.labels.sum().sum() > 0


def test_fixlb_preserves_multi_asset_label_panel() -> None:
    close = pd.DataFrame(
        {
            "AAA": [1.0, 2.0, 3.0, 2.0, 4.0],
            "BBB": [2.0, 3.0, 2.0, 4.0, 5.0],
        }
    )

    labels = build_labels(
        close,
        _label_config("fixlb", {"n": 2}, "threshold_future_return", {"threshold": 0.0}),
    )

    assert isinstance(labels, pd.DataFrame)
    assert list(labels.columns) == ["AAA", "BBB"]
    assert set(labels.stack().dropna().unique()) <= {0, 1}


def test_fixlb_native_horizon_sweep_selects_one_model_target() -> None:
    close = pd.DataFrame(
        {
            "AAA": [1.0, 2.0, 3.0, 2.0, 4.0],
            "BBB": [2.0, 3.0, 2.0, 4.0, 5.0],
        }
    )

    result = build_label_result(
        close,
        _label_config(
            "fixlb",
            {"n": [1, 2]},
            "threshold_future_return",
            {"threshold": 0.0},
            select={"n": 2},
        ),
    )

    assert set(result.native_labels.columns.get_level_values("fixlb_n")) == {1, 2}
    assert list(result.labels.columns) == ["AAA", "BBB"]
    assert result.target_schema["source"]["selected_params"] == {"n": 2}
    forward_return = close.shift(-2) / close - 1
    expected = (forward_return > 0.0).astype("Int8").mask(forward_return.isna(), pd.NA)

    pd.testing.assert_frame_equal(result.labels, expected)


def test_fixlb_records_concrete_future_row_evaluation_times() -> None:
    index = pd.to_datetime(["2024-01-01", "2024-01-03", "2024-01-06", "2024-01-10", "2024-01-15"])
    close = pd.DataFrame({"SYN": [1.0, 2.0, 3.0, 2.0, 4.0]}, index=index)

    result = build_label_result(
        close,
        _label_config("fixlb", {"n": 2}, "threshold_future_return", {"threshold": 0.0}),
    )

    evidence = result.evaluation_evidence
    assert evidence.metadata["evaluation_time"]["kind"] == "fixed_horizon"
    assert result.split_safety["evaluation_time"]["evidence"] == "label_evaluation_evidence"
    pd.testing.assert_series_equal(
        evidence.prediction_times["SYN"], pd.Series(index, index=index, name="SYN")
    )
    expected_eval = pd.Series(
        [index[2], index[3], index[4], pd.NaT, pd.NaT], index=index, name="SYN"
    )
    pd.testing.assert_series_equal(evidence.evaluation_times["SYN"], expected_eval)


def test_variable_pivot_labels_remain_fail_closed_without_confirmation_oracle() -> None:
    close = pd.DataFrame({"SYN": [1.0, 2.0, 3.0, 2.0, 1.0, 2.0, 3.0]})

    result = build_label_result(
        close,
        _label_config(
            "pivotlb",
            {"up_th": 0.2, "down_th": 0.2},
            "positive_event",
            {"positive_value": -1},
        ),
        high=close * 1.01,
        low=close * 0.99,
    )

    assert result.split_safety["evaluation_time"] == {
        "kind": "variable_unknown",
        "confirmation_time_oracle": None,
    }
    assert result.evaluation_evidence.evaluation_times.isna().all().all()
    assert result.split_safety["validation_suitability"] == "non_decision_grade_until_purged_cv"


def test_trendlb_pct_change_is_continuous_target() -> None:
    close = pd.DataFrame({"SYN": [1.0, 2.0, 3.0, 2.0, 1.0, 2.0]})

    result = build_label_result(
        close,
        _label_config(
            "trendlb",
            {"up_th": 0.2, "down_th": 0.2, "mode": "pct_change"},
            "continuous_identity",
            {},
        ),
        high=close * 1.01,
        low=close * 0.99,
    )

    assert result.target_schema["target_kind"] == "continuous"
    assert result.target_schema["source"]["selected_params"]["mode"] == "pctchange"
    assert str(result.labels.dtypes.iloc[0]) == "float64"


def _label_config(
    kind: str,
    params: dict,
    transform_name: str,
    transform_params: dict,
    *,
    role: str = "supervised_target",
    select: dict | None = None,
) -> LabelConfig:
    return LabelConfig(
        generator=LabelGeneratorConfig(kind=kind, params=params),
        target=LabelTargetConfig(
            role=role,
            select=LabelTargetSelectionConfig(params=select or {}),
            transform=LabelTargetTransformConfig(
                name=transform_name,
                params=transform_params,
            ),
        ),
    )
