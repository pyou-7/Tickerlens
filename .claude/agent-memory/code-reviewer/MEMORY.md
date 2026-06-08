# code-reviewer — Persistent Memory

This file is read at the start of every review and updated at the end when new patterns emerge.
Append entries; never delete them. Date every entry.

---

## Recurring Issues

<!-- Format:
### YYYY-MM-DD — <short title>
<What to watch for, with file:line if known. Why it matters.>
-->

*(no entries yet — first review will populate this)*

---

## Established Conventions (do not flag as issues)

<!-- Document project patterns here so the reviewer doesn't re-flag them each time.
Format:
### <Pattern name>
<Description of the convention and why it exists.>
-->

### CIK as canonical join key
Every DB join on a company uses CIK (zero-padded 10-digit string). Ticker is a display label
stored in a column, never used as a foreign key. This is intentional — do not flag ticker-based
lookups in UI presentation code as bugs unless they reach the DB layer.

### XBRL concept-mapping layer
All XBRL tag resolution goes through `src/tickerlens/data/xbrl.py`. Raw tag names (e.g.,
`us-gaap:Revenues`) must not appear in services or routes. Do flag any diff that bypasses this.

### Period join by `end` date
Quarterly financial metrics are joined by period `end` date, not by `fy/fp` label.
The `fy/fp` label on comparative facts can be misleading. This is a documented decision.

### Rate-limiting and User-Agent in EDGAR client
`src/tickerlens/data/edgar.py` owns the throttler (≤10 req/sec) and the required
`User-Agent: Tickerlens Personal <email>` header. No other file should make raw EDGAR
HTTP calls. Flag any diff that does.

### Cash-flow un-cumulation
Q2 and Q3 cash-flow line items are often YTD cumulative in 10-Qs. `data/xbrl.py` un-cumulates
them. If a diff introduces new cash-flow metric extraction that skips un-cumulation, flag it Critical.

---

## One-off Bugs Fixed (do not re-raise)

<!-- After a Critical finding is fixed and pushed, record it here so it is not re-raised.
Format:
### YYYY-MM-DD — <title> [FIXED]
<Brief description. Commit or PR reference if available.>
-->

*(none yet)*
