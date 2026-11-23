"""Batch 289 probe 4: wide-net fact dump around residual gaps.

For BLK/CART/APLD break ends, dump every instant USD fact (all
taxonomies) with value in [0.4*gap, 2.5*gap], plus every tag whose
name mentions consolidated/fund/sponsored/variable-interest.
DRY RUN only.
Usage: .venv/bin/python scripts/batch289_probe4.py
"""
import sys

sys.path.insert(0, "src")

from tickerlens.data.edgar import EdgarClient

CASES = [
    ("BLK", "0002012383", "2025-12-31", 5427e6),
    ("BLK", "0002012383", "2026-09-30", 3850e6),
    ("CART", "0001579091", "2025-12-31", 195e6),
    ("APLD", "0001144879", "2025-11-30", 105218000),
    ("APLD", "0001144879", "2026-08-31", 181302000),
]
NAME_KEYS = ("consolidat", "fund", "sponsored", "variableinterest",
             "vie", "noncontrolling", "minority", "redeemable",
             "temporary", "mezzanine", "preferred", "equity",
             "capital", "interest")


def main() -> int:
    client = EdgarClient()
    cache = {}
    for ticker, cik, end, gap in CASES:
        if cik not in cache:
            cache[cik] = client.companyfacts(cik)
        facts = cache[cik]
        print(f"\n{'=' * 72}\n{ticker} {end}: gap={gap:,.0f}")
        hits = []
        for tax, tags in facts.get("facts", {}).items():
            for tag, spec in tags.items():
                for f in spec.get("units", {}).get("USD", []):
                    if f.get("end") != end or "start" in f:
                        continue
                    val = f["val"]
                    in_range = 0.4 * gap <= val <= 2.5 * gap
                    named = any(k in tag.lower() for k in NAME_KEYS)
                    if in_range or named:
                        hits.append((tag, val, tax, f.get("form"),
                                     in_range))
        seen = set()
        for tag, val, tax, form, in_range in sorted(
                hits, key=lambda h: -h[1]):
            key = (tag, val)
            if key in seen:
                continue
            seen.add(key)
            mark = "  <-- IN GAP RANGE" if in_range else ""
            print(f"   [{tax}] {tag}: {val:,.0f} ({form}){mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
