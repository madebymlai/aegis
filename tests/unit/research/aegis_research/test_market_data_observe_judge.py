from __future__ import annotations

import pandas as pd

from research.aegis_research.market_data import diagnostics as observe
from research.aegis_research.market_data import quality as judge
from research.aegis_research.market_data.contracts import (
    DataDiagnostics,
    DataFeatureDiagnostics,
)
from tests.support.research.aegis_research.factories import make_data_config


def test_judge_is_a_pure_verdict_over_typed_diagnostics() -> None:
    verdict = judge.evaluate(
        make_data_config(source="diagnostic", symbols=["SYN"], arrays=["Close"]),
        (
            DataDiagnostics(
                symbol="SYN",
                configured=True,
                features={
                    "Close": DataFeatureDiagnostics(
                        available=True,
                        rows=3,
                        missing=1,
                        numeric=False,
                    )
                },
                index_evidence={
                    "raw_index_has_duplicates": True,
                    "raw_index_monotonic_increasing": False,
                },
            ),
        ),
        required_features=("Close",),
    )

    assert verdict.state == "rejected"
    assert verdict.reasons == (
        "raw data index contains duplicate timestamps",
        "raw data index is not monotonic increasing",
        "required feature 'Close' contains missing values",
        "required feature 'Close' has non-numeric symbols ['SYN']",
    )


def test_observe_reports_per_symbol_feature_diagnostics() -> None:
    index = pd.date_range("2020-01-01", periods=3, tz="UTC")
    frame = pd.DataFrame(
        {("SYN", "Close"): [1.0, 2.0, 3.0]},
        index=index,
    )
    frame.columns = pd.MultiIndex.from_tuples(frame.columns, names=["symbol", "feature"])
    config = make_data_config(source="frame", symbols=["SYN"], arrays=["Close"])

    observation = observe.observe(
        config,
        native_data=frame,
        requested_features=("Close",),
    )
    diagnostics = observe.diagnose(config, observation, evidence={"source": "frame"})

    assert diagnostics[0].symbol == "SYN"
    assert diagnostics[0].features["Close"].available is True
    assert diagnostics[0].features["Close"].rows == 3
