"""SIC code → readable sector label mapping."""

from __future__ import annotations

_RANGES: list[tuple[int, int, str]] = [
    (100, 999, "Agriculture"),
    (1000, 1499, "Mining"),
    (1500, 1799, "Construction"),
    (2000, 3999, "Manufacturing"),
    (4000, 4999, "Transportation & Utilities"),
    (5000, 5199, "Wholesale Trade"),
    (5200, 5999, "Retail Trade"),
    (6000, 6199, "Banking"),
    (6200, 6299, "Securities & Investments"),
    (6300, 6399, "Insurance"),
    (6500, 6799, "Real Estate"),
    (7000, 7299, "Hospitality & Services"),
    (7300, 7369, "Business Services"),
    (7370, 7379, "Technology"),
    (7380, 7399, "Business Services"),
    (7400, 7999, "Services"),
    (8000, 8099, "Healthcare"),
    (8100, 8999, "Professional Services"),
    (9000, 9999, "Public Administration"),
]


def sector_for_sic(sic: str | int | None) -> str | None:
    if sic is None:
        return None
    try:
        code = int(sic)
    except (ValueError, TypeError):
        return None
    for lo, hi, label in _RANGES:
        if lo <= code <= hi:
            return label
    return None
