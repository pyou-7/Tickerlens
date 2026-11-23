"""Batch 289 probe 5: filing-level balance-sheet inspection.

For BLK/CART/APLD, fetch submissions JSON, locate the 10-K/10-Q for a
break period end, then try to fetch the FilingSummary.xml + the
balance-sheet R file from SEC Archives to see every tagged concept on
the face (including dimensional/mezzanine lines companyfacts drops).
DRY RUN only.
Usage: .venv/bin/python scripts/batch289_probe5.py
"""
import re
import sys

sys.path.insert(0, "src")

from tickerlens.data.edgar import EdgarClient, SEC_SUBMISSIONS_URL, normalize_cik

CASES = [
    ("BLK", "0002012383", "10-K", "2026-02-25"),
    ("CART", "0001579091", "10-K", "2026-02-26"),
    ("APLD", "0001144879", "10-Q", "2026-01-08"),
]


def main() -> int:
    client = EdgarClient()
    for ticker, cik, form, filed in CASES:
        sub = client.fetch_json(SEC_SUBMISSIONS_URL.format(
            cik=normalize_cik(cik)))
        recent = sub["filings"]["recent"]
        accn = None
        for i, f in enumerate(recent["form"]):
            if f == form and recent["filingDate"][i] == filed:
                accn = recent["accessionNumber"][i]
                break
        print(f"\n{'=' * 72}\n{ticker} {form} filed {filed}: accn={accn}")
        if not accn:
            continue
        accn_nodash = accn.replace("-", "")
        cik_int = str(int(cik))
        base = (f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
                f"{accn_nodash}/")
        try:
            summary = client.fetch_text(base + "FilingSummary.xml")
        except Exception as exc:  # noqa: BLE001
            print(f"  FilingSummary fetch failed: {exc!r}")
            continue
        # find balance sheet report
        reports = re.findall(
            r"<Report[^>]*>.*?</Report>", summary, re.S)
        bs_file = None
        for rep in reports:
            short = re.search(r"<ShortName>(.*?)</ShortName>", rep)
            html = re.search(r"<HtmlFileName>(.*?)</HtmlFileName>", rep)
            if short and html and "balance" in short.group(1).lower() \
                    and "sheet" in short.group(1).lower():
                bs_file = html.group(1)
                print(f"  BS report: {short.group(1)} -> {bs_file}")
                break
        if not bs_file:
            names = re.findall(r"<ShortName>(.*?)</ShortName>", summary)
            print(f"  no BS report found; reports: {names[:20]}")
            continue
        try:
            bs_html = client.fetch_text(base + bs_file)
        except Exception as exc:  # noqa: BLE001
            print(f"  BS R-file fetch failed: {exc!r}")
            continue
        text = re.sub(r"<[^>]+>", " ", bs_html)
        text = re.sub(r"\s+", " ", text)
        print(f"  BS text ({len(text)} chars): {text[:3000]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
