from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from research.aegis_research.external_data.ishares_credit import (
    IsharesCreditDataError,
    IsharesCreditSource,
)


def _ucits_payload() -> bytes:
    rows = [
        [
            "ALPHA",
            "Alpha Bond",
            "Industrials",
            "Fixed Income",
            {"raw": 600.0},
            {"raw": 60.0},
            {"raw": 600.0},
            {"raw": 6.0},
            {"raw": 600.0},
            "US0000000001",
        ],
        [
            "BETA",
            "Beta Bond",
            "Industrials",
            "Fixed Income",
            {"raw": 400.0},
            {"raw": 40.0},
            {"raw": 400.0},
            {"raw": 4.0},
            {"raw": 400.0},
            "US0000000002",
        ],
    ]
    return json.dumps({"aaData": rows}).encode()


def _analytics_payload() -> bytes:
    points = {
        "asOfDate": {"value": 20200831},
        "issueName": {"value": ["Alpha Bond", "Beta Bond"]},
        "isin": {"value": ["US0000000001", "US0000000002"]},
        "yieldToWorst": {"value": [5.0, 7.0]},
        "modifiedDuration": {"value": [2.0, 4.0]},
    }
    payload = {
        "componentsByNameMap": {
            "holdings": {
                "containersByNameMap": {
                    "all": {"dataPointsByNameMap": points},
                }
            }
        }
    }
    return json.dumps(payload).encode()


class _IssuerResponses:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, url: str) -> bytes:
        self.calls += 1
        if "asOfDate=20200831" not in url:
            return json.dumps({"aaData": []}).encode()
        if "component=holdings.all" in url:
            return _analytics_payload()
        return _ucits_payload()


def test_source_returns_ucits_weighted_security_analytics(tmp_path: Path) -> None:
    responses = _IssuerResponses()
    source = IsharesCreditSource(tmp_path, fetch=responses)

    panel = source.load_window(pd.Timestamp("2020-08-01"), pd.Timestamp("2020-08-31"))

    sdhy = panel.loc[(pd.Timestamp("2020-08-31"), "SDHY.LSEETF")]
    assert sdhy.to_dict() == {
        "available_at": pd.Timestamp("2020-09-01"),
        "net_ytw": 5.35,
        "modified_duration": 2.8,
        "coverage": 1.0,
    }


def test_source_reuses_immutable_cache_when_offline(tmp_path: Path) -> None:
    responses = _IssuerResponses()
    online = IsharesCreditSource(tmp_path, fetch=responses)
    expected = online.load_window(pd.Timestamp("2020-08-01"), pd.Timestamp("2020-08-31"))
    cached_paths = sorted(tmp_path.glob("*.json"))

    def offline(url: str) -> bytes:
        raise OSError(f"offline: {url}")

    actual = IsharesCreditSource(tmp_path, fetch=offline).load_window(
        pd.Timestamp("2020-08-01"), pd.Timestamp("2020-08-31")
    )

    pd.testing.assert_frame_equal(actual, expected)
    assert sorted(tmp_path.glob("*.json")) == cached_paths


def test_source_does_not_query_an_incomplete_calendar_month(tmp_path: Path) -> None:
    responses = _IssuerResponses()
    source = IsharesCreditSource(tmp_path, fetch=responses)

    panel = source.load_window(pd.Timestamp("2020-08-01"), pd.Timestamp("2020-09-01"))

    assert panel.index.get_level_values("as_of_date").unique().tolist() == [
        pd.Timestamp("2020-08-31")
    ]


def test_source_accepts_timezone_aware_window_boundaries(tmp_path: Path) -> None:
    responses = _IssuerResponses()
    source = IsharesCreditSource(tmp_path, fetch=responses)

    panel = source.load_window(
        pd.Timestamp("2020-08-01", tz="UTC"),
        pd.Timestamp("2020-08-31", tz="UTC"),
    )

    assert len(panel) == 4


def test_source_exposes_low_match_coverage_without_inventing_values(tmp_path: Path) -> None:
    def missing_beta(url: str) -> bytes:
        if "asOfDate=20200831" not in url:
            return json.dumps({"aaData": []}).encode()
        if "component=holdings.all" not in url:
            return _ucits_payload()
        payload = json.loads(_analytics_payload())
        points = payload["componentsByNameMap"]["holdings"]["containersByNameMap"]["all"][
            "dataPointsByNameMap"
        ]
        for name in ("issueName", "isin", "yieldToWorst", "modifiedDuration"):
            points[name]["value"] = points[name]["value"][:1]
        return json.dumps(payload).encode()

    source = IsharesCreditSource(tmp_path, fetch=missing_beta)

    panel = source.load_window(pd.Timestamp("2020-08-01"), pd.Timestamp("2020-08-31"))

    sdhy = panel.loc[(pd.Timestamp("2020-08-31"), "SDHY.LSEETF")]
    assert sdhy["coverage"] == 0.6
    assert sdhy["net_ytw"] == 4.55
    assert sdhy["modified_duration"] == 2.0


def test_source_rejects_analytics_from_a_different_as_of_date(tmp_path: Path) -> None:
    def mismatched_date(url: str) -> bytes:
        if "asOfDate=20200831" not in url:
            return json.dumps({"aaData": []}).encode()
        if "component=holdings.all" not in url:
            return _ucits_payload()
        payload = json.loads(_analytics_payload())
        points = payload["componentsByNameMap"]["holdings"]["containersByNameMap"]["all"][
            "dataPointsByNameMap"
        ]
        points["asOfDate"]["value"] = 20200930
        return json.dumps(payload).encode()

    source = IsharesCreditSource(tmp_path, fetch=mismatched_date)

    with pytest.raises(IsharesCreditDataError, match="different as-of date"):
        source.load_window(pd.Timestamp("2020-08-01"), pd.Timestamp("2020-08-31"))

    assert list(tmp_path.glob("credit-analytics-*.json")) == []
