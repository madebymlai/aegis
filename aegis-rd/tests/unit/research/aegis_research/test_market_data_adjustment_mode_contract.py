"""MarketDataResult adjustment-mode invariant.

The continuous-futures adjustment mode is a materialisation fact: it exists iff
continuous roots were materialised. A result that pairs futures evidence with no
mode (or a mode with no futures) is a wiring bug and must fail at construction,
before it can become false Run evidence.
"""

from __future__ import annotations

import dataclasses

import pytest
from nautilus_trader.model.enums import ContinuousFutureAdjustmentType

from research.aegis_research.market_data.contracts import (
    AdjustmentModeEvidenceError,
    MarketDataQuality,
    MarketDataResult,
)
from tests.support.research.aegis_research.test_doubles import default_metadata


def _metadata(*, continuous_root_ids: list[str]):
    metadata = default_metadata()
    provenance = dataclasses.replace(
        metadata.provenance,
        source_metadata={"continuous_root_ids": continuous_root_ids},
    )
    return dataclasses.replace(metadata, provenance=provenance)


def _result(*, metadata, adjustment_mode) -> MarketDataResult:
    return MarketDataResult(
        native_data=None,
        metadata=metadata,
        diagnostics=(),
        quality=MarketDataQuality(state="healthy"),
        adjustment_mode=adjustment_mode,
    )


def test_result_carries_the_mode_alongside_futures_evidence() -> None:
    result = _result(
        metadata=_metadata(continuous_root_ids=["ES.XCME"]),
        adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_RATIO,
    )

    assert result.adjustment_mode is ContinuousFutureAdjustmentType.BACKWARD_RATIO


def test_result_rejects_futures_evidence_without_a_mode() -> None:
    with pytest.raises(AdjustmentModeEvidenceError, match="no adjustment_mode"):
        _result(
            metadata=_metadata(continuous_root_ids=["ES.XCME"]),
            adjustment_mode=None,
        )


def test_result_rejects_a_mode_without_futures_evidence() -> None:
    with pytest.raises(AdjustmentModeEvidenceError, match="no continuous roots"):
        _result(
            metadata=default_metadata(),
            adjustment_mode=ContinuousFutureAdjustmentType.BACKWARD_SPREAD,
        )


def test_result_without_futures_or_mode_is_valid() -> None:
    result = _result(metadata=default_metadata(), adjustment_mode=None)

    assert result.adjustment_mode is None
