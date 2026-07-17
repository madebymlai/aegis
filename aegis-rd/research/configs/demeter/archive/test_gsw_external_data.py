from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from research.aegis_research.external_data.gsw import GswNominalCurveSource


def _curve_payload() -> bytes:
    return b"""Note: test fixture

Series,Compounding Convention,Mnemonic(s)
Zero-coupon yield,Continuously Compounded,SVENYXX

Date,BETA0,BETA1,BETA2,BETA3,SVENY01,SVENY02,SVENY03,TAU1,TAU2
2020-08-28,1.5,0,0,0,1.50,1.50,1.50,5,6
2020-09-01,2.5,0,0,0,2.50,2.50,2.50,5,6
"""


def test_source_returns_causal_interpolated_zero_yield_with_provenance(
    tmp_path: Path,
) -> None:
    payload = _curve_payload()
    source = GswNominalCurveSource(tmp_path, fetch=lambda: payload)

    snapshot = source.load()
    observation = snapshot.zero_yield("2020-08-31", 2.5)

    assert observation.curve_date.date().isoformat() == "2020-08-28"
    assert observation.zero_yield_pct == pytest.approx(1.5)
    assert snapshot.provenance.sha256 == hashlib.sha256(payload).hexdigest()
    assert snapshot.provenance.first_date.date().isoformat() == "2020-08-28"
    assert snapshot.provenance.last_date.date().isoformat() == "2020-09-01"


def test_source_reuses_content_addressed_snapshot_when_live_fetch_fails(
    tmp_path: Path,
) -> None:
    payload = _curve_payload()
    expected = GswNominalCurveSource(tmp_path, fetch=lambda: payload).load()

    def offline() -> bytes:
        raise OSError("offline")

    actual = GswNominalCurveSource(tmp_path, fetch=offline).load()

    assert actual.provenance == expected.provenance
    assert sorted(path.name for path in tmp_path.glob("*.csv")) == [
        f"gsw-nominal-{hashlib.sha256(payload).hexdigest()[:16]}.csv"
    ]


def test_source_ignores_official_calendar_rows_without_fitted_parameters(
    tmp_path: Path,
) -> None:
    payload = _curve_payload().replace(
        b"2020-09-01,2.5,0,0,0,2.50,2.50,2.50,5,6\n",
        b"2020-08-31,NA,NA,NA,NA,NA,NA,NA,NA,NA\n"
        b"2020-09-01,2.5,0,0,0,2.50,2.50,2.50,5,6\n",
    )

    snapshot = GswNominalCurveSource(tmp_path, fetch=lambda: payload).load()
    observation = snapshot.zero_yield("2020-08-31", 2.5)

    assert list(snapshot.curve.index.strftime("%Y-%m-%d")) == [
        "2020-08-28",
        "2020-09-01",
    ]
    assert observation.curve_date.date().isoformat() == "2020-08-28"
