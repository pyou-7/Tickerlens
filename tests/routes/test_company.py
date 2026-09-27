from __future__ import annotations

import io
import zipfile
from fastapi.testclient import TestClient

from tickerlens.main import app

client = TestClient(app)


def test_company_detail_single_mode():
    response = client.get("/company/AAPL/detail")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    text = response.text
    assert "Time slicer" in text or "slicer-form" in text
    assert "Single Period" in text
    assert "Range Mode" in text
    assert "Export ZIP" in text


def test_company_detail_range_mode():
    response = client.get("/company/AAPL/detail?mode=range")
    assert response.status_code == 200
    text = response.text
    assert "Range Aggregates" in text
    assert "Cumulative Revenue" in text
    assert "Cumulative Net Income" in text
    assert "Cumulative Free Cash Flow" in text
    assert "Cumulative Total" in text


def test_company_detail_data_range_htmx():
    response = client.get("/company/AAPL/detail/data?mode=range&range_start=Q1+FY2025&range_end=Q2+FY2026")
    assert response.status_code == 200
    text = response.text
    assert "Range Aggregates" in text
    assert "Cumulative Total" in text


def test_company_export_zip():
    response = client.get("/company/AAPL/export-zip")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    assert "aapl_earnings_export.zip" in response.headers["content-disposition"].lower()

    # Validate ZIP integrity
    zf = zipfile.ZipFile(io.BytesIO(response.content), "r")
    namelist = zf.namelist()
    assert "aapl_financials.csv" in namelist
    assert "README.txt" in namelist
    csv_bytes = zf.read("aapl_financials.csv").decode("utf-8")
    assert "Revenue ($)" in csv_bytes
    assert "Net Income ($)" in csv_bytes
    assert "AAPL" in csv_bytes
