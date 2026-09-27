from __future__ import annotations

import io
import sys
import urllib.parse
import urllib.request
import zipfile

BASE_URL = "http://127.0.0.1:8000"


def fetch(path: str) -> tuple[int, bytes, dict[str, str]]:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "TickerlensValidator/1.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, resp.read(), headers
    except urllib.error.HTTPError as e:
        headers = {k.lower(): v for k, v in e.headers.items()}
        return e.code, e.read(), headers


def run_validations():
    print("=" * 65)
    print("STARTING E2E VALIDATION: TIME SLICER RANGE MODE & EARNINGS ZIP")
    print("=" * 65)

    # 1. Single Mode Detail View Check
    print("\n[1/5] Validating Single Period Detail View...")
    status, body, _ = fetch("/company/NVDA/detail")
    html = body.decode("utf-8")
    assert status == 200, f"Expected 200 got {status}"
    assert "Single Period" in html, "Missing Single Period button"
    assert "Range Mode" in html, "Missing Range Mode button"
    assert "Export ZIP" in html, "Missing Export ZIP button"
    print("  ✓ Detail page loaded with mode controls & ZIP export action")

    # 2. Range Mode Detail View Check (NVDA)
    print("\n[2/5] Validating Time Slicer Range Mode (/company/NVDA/detail?mode=range)...")
    status, body, _ = fetch("/company/NVDA/detail?mode=range")
    html = body.decode("utf-8")
    assert status == 200, f"Expected 200 got {status}"
    assert "Range Aggregates" in html, "Range Mode missing Range Aggregates hero banner"
    assert "Cumulative Revenue" in html, "Range Mode missing Cumulative Revenue card"
    assert "Cumulative Net Income" in html, "Range Mode missing Cumulative Net Income card"
    assert "Cumulative Free Cash Flow" in html, "Range Mode missing Cumulative FCF card"
    assert "Cumulative Total" in html, "Range Mode missing Cumulative Total column in table"
    assert "Latest Period" in html, "Range Mode missing Latest Period column in balance sheet"
    print("  ✓ Range Aggregates hero banner verified")
    print("  ✓ Cumulative fundamental totals verified")
    print("  ✓ Multi-period comparative statement columns verified")

    # 3. HTMX Partial Swap for Range Mode
    print("\n[3/5] Validating HTMX Range Swap (/company/NVDA/detail/data?mode=range)...")
    status, body, _ = fetch("/company/NVDA/detail/data?mode=range")
    html = body.decode("utf-8")
    assert status == 200, f"Expected 200 got {status}"
    assert "Range Aggregates" in html, "HTMX partial missing Range Aggregates"
    assert "Cumulative Total" in html, "HTMX partial missing Cumulative Total"
    print("  ✓ HTMX partial swap for Range Mode verified")

    # 4. ZIP Export Archive Generation & Integrity Check
    print("\n[4/5] Validating One-Click Earnings ZIP Export (/company/NVDA/export-zip)...")
    status, data, headers = fetch("/company/NVDA/export-zip")
    assert status == 200, f"Expected 200 got {status}"
    assert "application/zip" in headers.get("content-type", ""), f"Wrong content-type: {headers.get('content-type')}"
    assert "attachment" in headers.get("content-disposition", ""), "Missing attachment Content-Disposition"
    assert "nvda_earnings_export.zip" in headers.get("content-disposition", "").lower(), "Wrong zip filename"

    # Inspect ZIP contents
    zf = zipfile.ZipFile(io.BytesIO(data), "r")
    namelist = zf.namelist()
    assert "nvda_financials.csv" in namelist, "ZIP missing financials CSV"
    assert "README.txt" in namelist, "ZIP missing README.txt"

    # Validate CSV content
    csv_text = zf.read("nvda_financials.csv").decode("utf-8")
    assert "Revenue ($)" in csv_text, "CSV missing Revenue column"
    assert "Net Income ($)" in csv_text, "CSV missing Net Income column"
    assert "Free Cash Flow ($)" in csv_text, "CSV missing Free Cash Flow column"
    assert "NVDA" in csv_text, "CSV missing NVDA ticker data"

    # Validate README content
    readme_text = zf.read("README.txt").decode("utf-8")
    assert "NVIDIA" in readme_text or "NVDA" in readme_text, "README missing company name/ticker"
    assert "Tickerlens" in readme_text, "README missing Tickerlens attribution"

    print(f"  ✓ Valid ZIP archive returned ({len(data)} bytes, {len(namelist)} files)")
    print("  ✓ Comprehensive financials CSV verified")
    print("  ✓ Disclosures and README.txt verified")

    # 5. Full 10 Companies Range & Export Smoke Test
    print("\n[5/5] Validating Range Mode & ZIP Export across all 10 companies...")
    all_10 = ["AAPL", "MSFT", "ORCL", "NVDA", "TSLA", "AMZN", "GOOGL", "INTC", "MRVL", "META"]
    for sym in all_10:
        s_range, b_range, _ = fetch(f"/company/{sym}/detail/data?mode=range")
        assert s_range == 200, f"Failed range on {sym}: {s_range}"
        s_zip, b_zip, _ = fetch(f"/company/{sym}/export-zip")
        assert s_zip == 200, f"Failed export-zip on {sym}: {s_zip}"
        print(f"  ✓ {sym}: Range mode OK, Export ZIP OK ({len(b_zip)} bytes)")

    print("\n" + "=" * 65)
    print("ALL 5 RANGE MODE & ZIP EXPORT CHECKS PASSED (100% OK)")
    print("=" * 65)


if __name__ == "__main__":
    try:
        run_validations()
    except Exception as exc:
        print(f"\n❌ Validation failed: {exc}")
        sys.exit(1)
