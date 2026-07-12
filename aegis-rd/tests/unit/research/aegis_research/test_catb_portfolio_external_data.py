import zipfile
from io import BytesIO

import pytest

from research.aegis_research.external_data.catb_manager_report import parse_manager_report
from research.aegis_research.external_data.catb_portfolio import parse_hanetf_workbook


def test_parses_whole_portfolio_manager_statistics_from_publication_date() -> None:
    content = """
    <p><strong>Published Date:</strong> May 1, 2026</p>
    <p>The weighted average maturity was 1.74 years.</p>
    <p><strong>Cat Bond ETF Portfolio Statistics</strong><br><strong>As of 31/03/2026</strong></p>
    <table>
      <tr><td>Average Coupon</td><td>13.0%</td></tr>
      <tr><td>Average Yield</td><td>9.3%</td></tr>
      <tr><td>Spread</td><td>6.0%</td></tr>
      <tr><td>Expected Loss (EL) %</td><td>2.8%</td></tr>
    </table>
    """

    metrics = parse_manager_report(content)

    assert metrics.available_at.isoformat() == "2026-05-01T00:00:00+00:00"
    assert metrics.as_of == "2026-03-31"
    assert metrics.loss_adjusted_yield == pytest.approx(6.5)
    assert metrics.risk_multiple == pytest.approx(2.142857142857143)
    assert metrics.weighted_maturity_years == 1.74


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
