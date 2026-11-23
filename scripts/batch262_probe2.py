"""Batch 262 probe 2: which hard_table sub-predicate fires on each DIS
tripping line, and the lengths / figure counts involved."""
import sys

sys.path.insert(0, "src")

from tickerlens.data import filings as F
from batch231_repair import hard_table  # noqa: F401  (imported for parity)

sys.path.insert(0, "scripts")

TRIPPING = [
    "◦ Direct-to-Consumer operating income increased $431 million to $293 million",
    "◦ 178 million Disney+ and Hulu subscriptions, an increase of 0.9 million vs. Q4 fiscal 2024",
    "◦ 125 million Disney+ subscribers, a decrease of 0.7 million vs. Q4 fiscal 2024",
    "◦ Domestic ESPN advertising revenue up 15% vs. Q1 fiscal 2024",
    "◦ Direct-to-Consumer operating income increased $289 million to $336 million",
    "◦ Direct-to-Consumer operating income increased $365 million to $346 million",
    "◦ Direct-to-Consumer operating income increased $99 million to $352 million",
]
NON_TRIPPING = [
    "◦ Direct-to-Consumer advertising revenue declined 2%; excluding the Disney+ Hotstar service in India(2), Direct-to-Consumer advertising revenue was up 16% vs. Q1 fiscal 2024",
    "◦ Content Sales/Licensing and Other operating income increased $536 million to $312 million driven by the performance of Moana2",
    "◦ 180.7 million Disney+ and Hulu subscriptions, an increase of 2.5 million versus Q1 fiscal 2025",
    "◦ 126.0 million Disney+ subscribers, an increase of 1.4 million versus Q1 fiscal 2025",
    "• Sports: Segment operating income increased $350 million to $247 million",
]

preds = {
    "_is_lede_data_row": F._is_lede_data_row,
    "_is_lede_table_header": F._is_lede_table_header,
    "_is_lede_period_header": F._is_lede_period_header,
    "_is_trailing_units_period_header": F._is_trailing_units_period_header,
    "_is_trailing_table_data_row": F._is_trailing_table_data_row,
    "_is_trailing_table_header_orphan": F._is_trailing_table_header_orphan,
    "_LEDE_BARE_UNITS_RE": lambda ln: bool(F._LEDE_BARE_UNITS_RE.match(ln)),
    "_LEDE_BARE_UNITS_LOWER_RE": lambda ln: bool(F._LEDE_BARE_UNITS_LOWER_RE.match(ln)),
}

for label, lines in (("TRIPPING", TRIPPING), ("NON-TRIPPING", NON_TRIPPING)):
    print(f"=== {label}")
    for ln in lines:
        fired = [name for name, p in preds.items() if p(ln)]
        print(f"  len={len(ln)} bullet_lead={bool(F._BULLET_LEAD_RE.match(ln))} "
              f"terminated={F._is_sentence_terminated(ln)} fired={fired}")
        print(f"    {ln!r}")
