"""Batch 289 audit: data-quality sweep over all stored quarters.

Checks (stored data only, no network):
1. Accounting identity: Assets == Liabilities + Equity (+ redeemable NCI /
   temporary equity where present), tolerance 1% or $50M.
2. EPS sanity: diluted > basic by more than rounding (impossible when both
   positive; allowed when net income negative — dilution is anti-dilutive,
   so diluted loss per share is *smaller* in magnitude... actually with a
   loss, diluted EPS == basic EPS; diluted more negative than basic is
   impossible).
3. Missing core metrics per quarter (revenue / net income / EPS / FCF).
4. Quarter sequence: duplicate (fy, fp) labels, gaps > 120 days between
   consecutive period ends, stale latest quarter (> 200 days old).
5. Sign sanity: negative revenue, negative total assets.

DRY RUN only — no DB writes.
Usage: .venv/bin/python scripts/batch289_audit.py
"""
import sqlite3
from datetime import date

DB = "tickerlens.db"
TODAY = date(2026, 11, 20)


def main() -> int:
    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT c.ticker, q.period_end, q.fiscal_year, q.fiscal_period, "
        "q.revenue, q.net_income, q.eps_basic, q.eps_diluted, "
        "q.free_cash_flow, q.total_assets, q.total_liabilities, "
        "q.total_equity, q.cash_and_equivalents, q.redeemable_nci, "
        "q.temporary_equity "
        "FROM quarterly_financials q JOIN companies c ON c.cik = q.cik "
        "ORDER BY c.ticker, q.period_end"
    ).fetchall()
    print(f"{len(rows)} stored quarters")

    identity_breaks = []
    eps_inversions = []
    neg_revenue = []
    neg_assets = []
    missing = {"revenue": 0, "net_income": 0, "eps_basic": 0,
               "eps_diluted": 0, "fcf": 0, "assets": 0}
    by_ticker: dict[str, list] = {}

    for (ticker, pe, fy, fp, rev, ni, eb, ed, fcf, ta, tl, te, cash,
         rnci, temp_eq) in rows:
        by_ticker.setdefault(ticker, []).append((pe, fy, fp))
        if rev is None:
            missing["revenue"] += 1
        if ni is None:
            missing["net_income"] += 1
        if eb is None:
            missing["eps_basic"] += 1
        if ed is None:
            missing["eps_diluted"] += 1
        if fcf is None:
            missing["fcf"] += 1
        if ta is None:
            missing["assets"] += 1
        if rev is not None and rev < 0:
            neg_revenue.append((ticker, pe, rev))
        if ta is not None and ta < 0:
            neg_assets.append((ticker, pe, ta))
        # Identity: A = L + E (+ redeemable NCI + temporary equity)
        if None not in (ta, tl, te):
            rhs = tl + te + (rnci or 0) + (temp_eq or 0)
            gap = abs(ta - rhs)
            tol = max(0.01 * abs(ta), 50e6)
            if gap > tol:
                identity_breaks.append(
                    (ticker, pe, ta, tl, te, rnci, temp_eq, gap))
        # EPS: with positive NI, diluted <= basic (+1c rounding).
        # With negative NI, diluted == basic (anti-dilutive); diluted
        # more negative than basic by >1c is impossible.
        if eb is not None and ed is not None and ni is not None:
            if ni > 0 and ed > eb + 0.011:
                eps_inversions.append((ticker, pe, ni, eb, ed))
            if ni < 0 and ed < eb - 0.011:
                eps_inversions.append((ticker, pe, ni, eb, ed))

    print(f"\nMissing counts: {missing}")
    print(f"\nNegative revenue rows: {len(neg_revenue)}")
    for r in neg_revenue[:10]:
        print("  ", r)
    print(f"Negative assets rows: {len(neg_assets)}")
    for r in neg_assets[:10]:
        print("  ", r)

    print(f"\nIdentity breaks (>{1}% or $50M): {len(identity_breaks)}")
    for (t, pe, ta, tl, te, rnci, teq, gap) in identity_breaks[:25]:
        print(f"   {t} {pe}: A={ta/1e9:.2f}B L={tl/1e9:.2f}B "
              f"E={te/1e9:.2f}B rnci={rnci} temp={teq} gap={gap/1e9:.2f}B")

    print(f"\nEPS inversions: {len(eps_inversions)}")
    for r in eps_inversions[:25]:
        print("  ", r)

    # Sequence checks
    dup_labels = []
    gaps = []
    stale = []
    for ticker, qs in sorted(by_ticker.items()):
        seen = {}
        for pe, fy, fp in qs:
            key = (fy, fp)
            if key in seen:
                dup_labels.append((ticker, fy, fp, seen[key], pe))
            seen[key] = pe
        ends = [date.fromisoformat(pe) for pe, _, _ in qs]
        for a, b in zip(ends, ends[1:]):
            d = (b - a).days
            if d > 130:
                gaps.append((ticker, str(a), str(b), d))
        latest_age = (TODAY - ends[-1]).days
        if latest_age > 200:
            stale.append((ticker, str(ends[-1]), latest_age, len(qs)))

    print(f"\nDuplicate (fy,fp) labels: {len(dup_labels)}")
    for r in dup_labels[:15]:
        print("  ", r)
    print(f"\nQuarter gaps >130d: {len(gaps)}")
    for r in gaps[:15]:
        print("  ", r)
    print(f"\nStale latest quarter (>200d before {TODAY}): {len(stale)}")
    for r in stale[:20]:
        print("  ", r)

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
