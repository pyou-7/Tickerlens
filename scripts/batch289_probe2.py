"""Batch 289 probe 2: find the filed tag that closes each identity gap.

For each break (ticker, end, gap), list every instant USD fact at that
end whose value is within 3% of the gap, plus all equity/mezzanine-
named tags. DRY RUN only.
Usage: .venv/bin/python scripts/batch289_probe2.py
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.edgar import EdgarClient

CASES = [
    ("BLK", "0002012383", "2025-12-31", 169998e6 - 108456e6 - 56115e6),
    ("BLK", "0002012383", "2026-09-30", 177898e6 - 110123e6 - 63925e6),
    ("CART", "0001579091", "2025-12-31", 3687e6 - 974e6 - 2518e6),
    ("CART", "0001579091", "2026-06-30", 3510e6 - 988e6 - 2322e6),
    ("DLR", "0001297996", "2025-12-31", None),
    ("APLD", "0001144879", "2025-11-30", None),
]
EQ_KEYS = ("equity", "noncontrolling", "minority", "redeemable",
           "temporary", "mezzanine", "partnerscapital")


def main() -> int:
    client = EdgarClient()
    cache = {}
    for ticker, cik, end, gap in CASES:
        if cik not in cache:
            cache[cik] = client.companyfacts(cik)
        facts = cache[cik]
        gaap = facts.get("facts", {}).get("us-gaap", {})
        # gather all instant USD facts at end
        at_end = []
        for tag, spec in gaap.items():
            for f in spec.get("units", {}).get("USD", []):
                if f.get("end") == end and "start" not in f:
                    at_end.append((tag, f["val"], f.get("form"),
                                   f.get("filed")))
        # dedupe by (tag, val)
        seen = {}
        for tag, val, form, filed in at_end:
            seen.setdefault((tag, val), (form, filed))
        a = next((v for (t, v) in seen if t == "Assets"), None)
        l = next((v for (t, v) in seen if t == "Liabilities"), None)
        e = next((v for (t, v) in seen
                  if t == "StockholdersEquityIncludingPortion"
                         "AttributableToNoncontrollingInterest"), None)
        if e is None:
            e = next((v for (t, v) in seen if t == "StockholdersEquity"),
                     None)
        if gap is None and None not in (a, l, e):
            gap = a - l - e
        print(f"\n{'=' * 72}\n{ticker} {end}: A={a} L={l} E={e} gap={gap}")
        print("-- equity/mezzanine-named tags at end --")
        for (tag, val), (form, filed) in sorted(seen.items()):
            if any(k in tag.lower() for k in EQ_KEYS):
                print(f"   {tag}: {val:,.0f} ({form} {filed})")
        if gap:
            print(f"-- facts within 3% of gap {gap:,.0f} --")
            for (tag, val), (form, filed) in sorted(seen.items()):
                if val and abs(val - gap) <= 0.03 * abs(gap):
                    print(f"   {tag}: {val:,.0f} ({form} {filed})")
            print("-- facts within 3% of gap/2, gap combos (L+gap?) --")
            for (tag, val), (form, filed) in sorted(seen.items()):
                if val and l and abs(val - (l + gap)) <= 0.005 * (l + gap):
                    print(f"   L+gap {tag}: {val:,.0f} ({form} {filed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
