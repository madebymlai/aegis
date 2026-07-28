"""Complete-path Candidate validity tests."""

from __future__ import annotations

import pandas as pd
import pytest

from research.aegis_research.optimization.candidate_validity import (
    Verdicts,
    classify_continuous_candidates,
)


def test_continuous_classification_uses_complete_path_records_with_precedence() -> None:
    metrics = pd.DataFrame(
        {
            "total_return": [9.0, 0.0, 0.2, 0.8],
            "total_trades": [9.0, 0.0, 1.0, 5.0],
        },
        index=pd.MultiIndex.from_tuples(
            [("invalid",), ("flat",), ("thin",), ("live",)], names=["candidate"]
        ),
    )

    verdict = classify_continuous_candidates(
        metrics,
        invalid_keys={("invalid",)},
        min_trades=2,
        metric="total_return",
    )

    assert verdict.invalid == {("invalid",)}
    assert verdict.non_trading == {("flat",)}
    assert verdict.under_traded == {("thin",)}
    assert verdict.valid == {("live",)}


def test_continuous_classification_rejects_missing_ranking_metric() -> None:
    metrics = pd.DataFrame(
        {"total_trades": [2.0]},
        index=pd.MultiIndex.from_tuples([("candidate",)], names=["candidate"]),
    )

    with pytest.raises(KeyError, match="not present in metric columns"):
        classify_continuous_candidates(
            metrics, invalid_keys=set(), min_trades=0, metric="total_return"
        )


def test_continuous_classification_handles_empty_candidate_field() -> None:
    metrics = pd.DataFrame(
        columns=["total_return", "total_trades"],
        index=pd.MultiIndex.from_tuples([], names=["candidate"]),
    )

    verdict = classify_continuous_candidates(
        metrics, invalid_keys=set(), min_trades=0, metric="total_return"
    )

    assert verdict == Verdicts()


def test_verdict_counts_are_derived_from_the_partition() -> None:
    verdict = Verdicts(
        invalid={("a",)},
        non_trading={("b",), ("c",)},
        under_traded={("d",)},
        valid={("e",), ("f",), ("g",)},
    )

    assert verdict.excluded_invalid == 1
    assert verdict.excluded_degenerate == 4
    assert verdict.total == 7
    assert verdict.admissible == verdict.valid
    assert verdict.excluded_invalid <= verdict.excluded_degenerate <= verdict.total
