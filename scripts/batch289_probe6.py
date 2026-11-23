"""Batch 289 probe 6: BLK balance-sheet face + OXY/BKR follow-ups.

Fetches BLK's "Consolidated Statements of Financial Condition" R file
and prints the face text. Also re-runs the OXY Q4-derivability and BKR
EPS checks from probe 1 (output was truncated there). DRY RUN only.
Usage: .venv/bin/python scripts/batch289_probe6.py
"""
import re
import sys

sys.path.insert(0, "src")

from tickerlens.data.edgar import EdgarClient, SEC_SUBMISSIONS_URL, normalize_cik


def blk_face(client: EdgarClient) -> None:
    cik = "0002012383"
    sub = client.fetch_json(SEC_SUBMISSIONS_URL.format(
        cik=normalize_cik(cik)))
    recent = sub["filings"]["recent"]
    accn = None
    for i, f in enumerate(recent["form"]):
        if f == "10-K" and recent["filingDate"][i] == "2026-02-25":
            accn = recent["accessionNumber"][i]
            break
    print(f"BLK 10-K accn={accn}")
    base = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accn.replace('-', '')}/")
    summary = client.fetch_text(base + "FilingSummary.xml")
    reports = re.findall(r"<Report[^>]*>.*?</Report>", summary, re.S)
    for rep in reports:
        short = re.search(r"<ShortName>(.*?)</ShortName>", rep)
        html = re.search(r"<HtmlFileName>(.*?)</HtmlFileName>", rep)
        if short and html and short.group(1) == \
                "Consolidated Statements of Financial Condition":
            bs_html = client.fetch_text(base + html.group(1))
            text = re.sub(r"<[^>]+>", " ", bs_html)
            text = re.sub(r"\s+", " ", text)
            print(f"BLK face ({len(text)} chars):\n{text[:6000]}")
            return
    print("BLK face report not found")


def oxy_bkr(client: EdgarClient) -> None:
    facts = client.companyfacts("0000797468")
    gaap = facts.get("facts", {}).get("us-gaap", {})
    print(f"\n{'=' * 72}\nOXY revenue/NI facts, ends 2025-09-30..2026-03-31")
    for tag in ("Revenues",
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                "NetIncomeLoss", "ProfitLoss",
                "NetIncomeLossAvailableToCommonStockholdersBasic"):
        flist = gaap.get(tag, {}).get("units", {}).get("USD", [])
        hits = [f for f in flist
                if "2025-09-30" <= f.get("end", "") <= "2026-03-31"]
        print(f"  {tag}:")
        for f in hits:
            print(f"    start={f.get('start')} end={f['end']} "
                  f"val={f['val']:,} fp={f.get('fp')} fy={f.get('fy')} "
                  f"form={f.get('form')} filed={f.get('filed')}")
    facts = client.companyfacts("0001701605")
    gaap = facts.get("facts", {}).get("us-gaap", {})
    print(f"\n{'=' * 72}\nBKR EPS tags")
    for tag in sorted(gaap):
        if "PerShare" in tag:
            for unit, flist in gaap[tag].get("units", {}).items():
                recent = [f for f in flist
                          if f.get("end", "") >= "2025-06-30"][:4]
                print(f"  {tag} [{unit}]: n={len(flist)}")
                for f in recent:
                    print(f"    start={f.get('start')} end={f['end']} "
                          f"val={f['val']} fp={f.get('fp')} "
                          f"form={f.get('form')}")


def main() -> int:
    client = EdgarClient()
    blk_face(client)
    oxy_bkr(client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
