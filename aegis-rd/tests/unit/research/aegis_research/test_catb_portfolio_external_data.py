import hashlib
import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from research.aegis_research.external_data.catb_portfolio import (
    CatbPortfolioWeightError,
    load_portfolio_metrics,
    parse_hanetf_workbook,
)


def _cache(tmp_path: Path, *, total_cash_weight: float = 60.0) -> tuple[Path, Path]:
    holdings = [
        {
            "isin": None,
            "weight": total_cash_weight,
            "market_value": 60.0,
            "insurance_spread": None,
        },
        {
            "isin": "A",
            "weight": 20.0,
            "market_value": 20.0,
            "insurance_spread": 10.0,
        },
        {
            "isin": "B",
            "weight": 20.0,
            "market_value": 20.0,
            "insurance_spread": 6.0,
        },
    ]
    payload = {
        "schema_version": 2,
        "retrieved_at": "2026-07-12T00:00:00+00:00",
        "fund_isin": "IE000UWJUW87",
        "holdings_sha256": hashlib.sha256(
            json.dumps(holdings, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "holdings": holdings,
    }
    path = tmp_path / "catb.json"
    path.write_text(json.dumps(payload))
    enrichment = tmp_path / "matches.json"
    enrichment.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "matches": {
                    "A": {
                        "expected_loss": 2.0,
                        "artemis_source": "https://www.artemis.bm/a",
                        "available_at": "2025-12-31T00:00:00+00:00",
                        "verified_at": "2026-07-12T00:00:00+00:00",
                    },
                    "B": {
                        "expected_loss": 2.0,
                        "artemis_source": "https://www.artemis.bm/b",
                        "available_at": "2025-12-31T00:00:00+00:00",
                        "verified_at": "2026-07-12T00:00:00+00:00",
                    },
                },
            }
        )
    )
    return path, enrichment


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("insurance_spread", 8.0),
        ("expected_loss", 2.0),
        ("net_carry", 9.0),
        ("risk_multiple", 4.0),
        ("coverage", 1.0),
    ],
)
def test_aggregates_matched_catb_positions(
    tmp_path: Path, field: str, expected: float
) -> None:
    path, enrichment = _cache(tmp_path)

    metrics = load_portfolio_metrics(
        path, enrichment, collateral_yield=4.0, fund_fee=1.0
    )

    assert getattr(metrics, field) == expected


def test_rejects_weights_that_do_not_reconcile(tmp_path: Path) -> None:
    path, enrichment = _cache(tmp_path, total_cash_weight=30.0)

    with pytest.raises(CatbPortfolioWeightError, match="reconcile"):
        load_portfolio_metrics(
            path, enrichment, collateral_yield=4.0, fund_fee=1.0
        )


def test_parses_hanetf_workbook_without_excel_dependency() -> None:
    xml = """<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
    <sheetData>
      <row r="1"><c r="A1" t="inlineStr"><is><t>KRC Cat Bond UCITS ETF (IE000UWJUW87) As Of:08-07-2026</t></is></c></row>
      <row r="2"/><row r="3"/><row r="4"/><row r="5"/>
      <row r="6"><c r="A6" t="inlineStr"><is><t>TEST RE LTD FLT 01/01/27 SR:A 8% 01/01/2027</t></is></c><c r="C6"><v>100</v></c><c r="H6" t="inlineStr"><is><t>US123</t></is></c><c r="I6"><v>1</v></c></row>
    </sheetData></worksheet>"""
    content = BytesIO()
    with zipfile.ZipFile(content, "w") as workbook:
        workbook.writestr("xl/worksheets/sheet1.xml", xml)

    as_of, holdings = parse_hanetf_workbook(content.getvalue())

    assert as_of == "2026-07-08"
    assert holdings == [
        {
            "description": "TEST RE LTD FLT 01/01/27 SR:A 8% 01/01/2027",
            "isin": "US123",
            "weight": 100.0,
            "market_value": 100.0,
            "insurance_spread": 8.0,
            "maturity": "01/01/2027",
        }
    ]
