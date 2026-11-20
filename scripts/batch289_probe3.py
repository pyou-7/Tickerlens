"""Batch 289 probe 3: extension-taxonomy tags + residual hunt.

Checks non-us-gaap taxonomies in companyfacts for BLK/CART/APLD/DLR
and searches every taxonomy for instant USD facts at the break ends
near the residual gap. DRY RUN only.
Usage: .venv/bin/python scripts/batch289_probe3.py
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.edgar import EdgarClient

CASES = [
    # ticker, cik, end, residual gap (A - L - E - known mezz)
    ("BLK", "0002012383", "2025-12-31", 5427e6),
    ("BLK", "0002012383", "2026-09-30", 3850e6),
    ("CART", "0001579091", "2025-12-31", 195e6),
    ("APLD", "0001144879", "2025-11-30", 622190000 - 516972000),
    ("APLD", "0001144879", "2026-08-31", None),
    ("DLR", "0001297996", "2025-12-31", 1498975000),
]


def main() -> int:
    client = EdgarClient()
    cache = {}
    for ticker, cik, end, gap in CASES:
        if cik not in cache:
            cache[cik] = client.companyfacts(cik)
        facts = cache[cik]
        taxonomies = list(facts.get("facts", {}).keys())
        print(f"\n{'=' * 72}\n{ticker} {end}: taxonomies={taxonomies}")
        for tax in taxonomies:
            tags = facts["facts"][tax]
            for tag, spec in sorted(tags.items()):
                for f in spec.get("units", {}).get("USD", []):
                    if f.get("end") != end or "start" in f:
                        continue
                    val = f["val"]
                    near = gap and abs(val - gap) <= 0.05 * abs(gap)
                    named = any(k in tag.lower() for k in
                                ("equity", "noncontrolling", "minority",
                                 "redeemable", "temporary", "mezzanine",
                                 "preferred", "capital"))
                    if tax != "us-gaap" or near or named:
                        print(f"   [{tax}] {tag}: {val:,.0f} "
                              f"({f.get('form')} {f.get('filed')})"
                              f"{'  <-- NEAR GAP' if near else ''}")
        # APLD residual: also print A/L/E/rnci for the end
        if ticker == "APLD":
            gaap = facts["facts"].get("us-gaap", {})
            for tag in ("Assets", "Liabilities", "StockholdersEquity",
                        "RedeemableNoncontrollingInterestEquityCarryingAmount",
                        "TemporaryEquityCarryingAmountAttributableToParent",
                        "TemporaryEquityCarryingAmountIncludingPortion"
                        "AttributableToNoncontrollingInterests"):
                for f in gaap.get(tag, {}).get("units", {}).get("USD", []):
                    if f.get("end") == end and "start" not in f:
                        print(f"   APLD-check {tag}: {f['val']:,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
