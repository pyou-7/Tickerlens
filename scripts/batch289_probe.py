"""Batch 289 probe: inspect balance-sheet tags for identity-break filers.

Fetches companyfacts (via the app's EdgarClient, disk-cached) for
BLK / CART / DLR / APLD and dumps every us-gaap tag whose name looks
equity/mezzanine-related, with the facts at the break period ends.
Also checks OXY 2025-12-31 Q4 derivability and BKR EPS tags.

DRY RUN only — no DB writes.
Usage: .venv/bin/python scripts/batch289_probe.py
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.edgar import EdgarClient

CIKS = {
    "BLK": "0002012383",
    "CART": "0001579091",
    "DLR": "0001297996",
    "APLD": "0001144879",
    "OXY": "0000797468",
    "BKR": "0001701605",
}
WANT_ENDS = {
    "BLK": ["2026-09-30", "2025-12-31"],
    "CART": ["2026-06-30", "2025-12-31"],
    "DLR": ["2026-03-31", "2025-12-31"],
    "APLD": ["2026-08-31", "2025-11-30"],
}
KEYWORDS = ("Equity", "Noncontrolling", "Minority", "Redeemable",
            "Temporary", "Liabilit", "Assets", "PartnersCapital",
            "Preferred")


def dump_tags(ticker: str, facts: dict) -> None:
    gaap = facts.get("facts", {}).get("us-gaap", {})
    print(f"\n{'=' * 72}\n{ticker}: {len(gaap)} us-gaap tags")
    ends = WANT_ENDS.get(ticker, [])
    for tag in sorted(gaap):
        if not any(k.lower() in tag.lower() for k in KEYWORDS):
            continue
        units = gaap[tag].get("units", {})
        for unit, flist in units.items():
            hits = [f for f in flist if f.get("end") in ends
                    and "start" not in f]
            if hits:
                vals = [(f["end"], f["val"], f.get("form"),
                         f.get("filed")) for f in hits]
                print(f"  {tag} [{unit}]: {vals}")


def main() -> int:
    client = EdgarClient()
    for ticker, cik in CIKS.items():
        try:
            facts = client.companyfacts(cik)
        except Exception as exc:  # noqa: BLE001 - probe
            print(f"{ticker}: FETCH FAILED {exc!r}")
            continue
        if ticker in WANT_ENDS:
            dump_tags(ticker, facts)
        if ticker == "OXY":
            gaap = facts.get("facts", {}).get("us-gaap", {})
            print(f"\n{'=' * 72}\nOXY revenue/NI facts around 2025-12-31")
            for tag in ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                        "NetIncomeLoss", "ProfitLoss"):
                flist = gaap.get(tag, {}).get("units", {}).get("USD", [])
                hits = [f for f in flist
                        if f.get("end", "") >= "2025-09-30"
                        and f.get("end", "") <= "2026-03-31"]
                print(f"  {tag}: {[(f.get('start'), f['end'], f['val'], f.get('fp'), f.get('form')) for f in hits]}")
        if ticker == "BKR":
            gaap = facts.get("facts", {}).get("us-gaap", {})
            print(f"\n{'=' * 72}\nBKR EPS tags")
            for tag in sorted(gaap):
                if "PerShare" in tag or "EarningsPerShare" in tag:
                    for unit, flist in gaap[tag].get("units", {}).items():
                        recent = [f for f in flist
                                  if f.get("end", "") >= "2025-01-01"][:3]
                        print(f"  {tag} [{unit}]: n={len(flist)} "
                              f"recent={[(f.get('start'), f['end'], f['val']) for f in recent]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
