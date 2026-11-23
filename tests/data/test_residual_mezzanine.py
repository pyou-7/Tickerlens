"""Dimensional mezzanine recovery + double-tag dedupe — batch 289.

Round-30 audit (all 303 stored companies) found 83 quarters rendering
Assets != Liabilities + Equity at the code tolerance. Causes:

1. Digital Realty files its mezzanine total under
   ``TemporaryEquityCarryingAmountIncludingPortionAttributableTo
   NoncontrollingInterests`` ($1,498,975,000 at 2025-12-31 — exactly the
   gap), a tag the TEMPORARY_EQUITY chain lacked (it held only the
   parent-attributable variant, KDP-shaped).

2. BlackRock, Maplebear, and Applied Digital tag mezzanine only with
   dimensional facts (member/series axes), which companyfacts drops:
   BLK's temporary equity is Subco $2,791M + Consolidated Sponsored
   Investment Products $2,636M = $5,427M (2025-12-31 face); CART's is
   Series A redeemable convertible preferred $196M; APLD's is three
   per-series temporary-equity lines ($105,218K) on top of its filed
   redeemable NCI. ``_derive_residual_mezzanine`` recovers the total as
   A − L − E − filed mezzanine, but only on a corroborated single-filing
   basis (``_single_filing_basis``), with a material positive residual
   and an empty target slot.

3. KKR (pre-existing) and Prudential/NEE/TDG (exposed by the chain
   addition) tag ONE mezzanine line under both concepts with identical
   amounts; summing both double-counts. ``_dedupe_double_tagged_
   mezzanine`` drops the temporary-equity copy when one copy closes
   the identity and two break it.
"""

from tickerlens.data.xbrl import extract_recent_quarterly_financials

ACCN = "0001193125-26-071966"  # BLK 10-K filed 2026-02-25 (fixture basis)
ACCN_OTHER = "0001193125-26-099999"
ACCN_LATER = "0001193125-26-447043"  # later 10-Q comparative (fixture)


def _instant(end: str, val: float, accn: str | None = ACCN,
             filed: str = "2026-11-04") -> dict:
    fact = {
        "end": end,
        "val": val,
        "fy": 2026,
        "fp": "Q3",
        "form": "10-Q",
        "filed": filed,
    }
    if accn is not None:
        fact["accn"] = accn
    return fact


def _rev(start: str, end: str, val: float) -> dict:
    return {
        "start": start,
        "end": end,
        "val": val,
        "fy": 2026,
        "fp": "Q3",
        "form": "10-Q",
        "filed": "2026-11-04",
    }


def _blk_shaped() -> dict:
    """Mirror BlackRock's 2026-09-30 face (in $M): A=177,898, L=110,123,
    E=63,925 (incl. NCI); temporary equity $3,850M exists only as
    dimensional member-axis facts, absent from companyfacts."""
    end = "2026-09-30"
    return {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {"USD": [_rev("2026-07-01", end, 6_000_000_000)]}
                },
                "Assets": {
                    "units": {"USD": [_instant(end, 177_898_000_000)]}
                },
                "Liabilities": {
                    "units": {"USD": [_instant(end, 110_123_000_000)]}
                },
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": {
                    "units": {"USD": [_instant(end, 63_925_000_000)]}
                },
            }
        }
    }


def _extract(facts: dict):
    rows = extract_recent_quarterly_financials(
        facts, fiscal_year_end="1231", periods=4
    )
    assert len(rows) == 1
    return rows[0]


def test_residual_mezzanine_derived_into_temporary_equity() -> None:
    row = _extract(_blk_shaped())
    assert row.temporary_equity == 3_850_000_000
    assert row.redeemable_nci is None
    assert (
        row.total_liabilities + row.temporary_equity + row.total_equity
        == row.total_assets
    )


def test_residual_derivation_needs_single_filing_basis() -> None:
    """Legs spanning two filings with no corroborating fact: the gap may
    be a mixed-basis artifact (Darden class), never derived mezzanine."""
    facts = _blk_shaped()
    facts["facts"]["us-gaap"]["Assets"]["units"]["USD"][0]["accn"] = ACCN_OTHER
    row = _extract(facts)
    assert row.temporary_equity is None
    assert row.redeemable_nci is None


def test_residual_derivation_needs_accn_provenance() -> None:
    """Facts without accession numbers cannot prove a single-filing
    basis, so nothing derives (legacy fixtures stay unchanged)."""
    facts = _blk_shaped()
    for tag in ("Assets", "Liabilities",
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"):
        del facts["facts"]["us-gaap"][tag]["units"]["USD"][0]["accn"]
    row = _extract(facts)
    assert row.temporary_equity is None


def test_residual_derives_when_equity_leg_is_later_comparative() -> None:
    """The attested BLK/CART/APLD pattern: Assets/Liabilities from the
    original filing, Equity chosen from a later filing's comparative
    column repeating the same value. The original filing's own Equity
    fact corroborates the basis, so the residual derives."""
    facts = _blk_shaped()
    end = "2026-09-30"
    eq = facts["facts"]["us-gaap"][
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
    ]["units"]["USD"]
    # Later comparative repeats the value; latest-wins picks it.
    eq.append(_instant(end, 63_925_000_000, ACCN_LATER, filed="2026-11-20"))
    row = _extract(facts)
    assert row.temporary_equity == 3_850_000_000


def test_no_derivation_when_comparative_equity_value_differs() -> None:
    """A later filing restates Equity to a different value: the chosen
    legs no longer share one filing's balance sheet, so the residual
    could be a restatement artifact — nothing derives."""
    facts = _blk_shaped()
    end = "2026-09-30"
    eq = facts["facts"]["us-gaap"][
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
    ]["units"]["USD"]
    eq.append(_instant(end, 64_500_000_000, ACCN_LATER, filed="2026-11-20"))
    row = _extract(facts)
    assert row.total_equity == 64_500_000_000
    assert row.temporary_equity is None


def test_no_derivation_when_identity_already_closes() -> None:
    facts = _blk_shaped()
    # Equity restated so the two-leg identity closes exactly.
    facts["facts"]["us-gaap"][
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
    ]["units"]["USD"][0]["val"] = 67_775_000_000
    row = _extract(facts)
    assert row.temporary_equity is None
    assert row.redeemable_nci is None


def test_no_derivation_for_negative_residual() -> None:
    """Liabilities + Equity overshoot Assets: a wrong leg, not negative
    mezzanine — leave the gap as filed."""
    facts = _blk_shaped()
    facts["facts"]["us-gaap"]["Liabilities"]["units"]["USD"][0]["val"] = (
        120_000_000_000
    )
    row = _extract(facts)
    assert row.temporary_equity is None
    assert row.redeemable_nci is None


def test_no_derivation_below_tolerance() -> None:
    """A residual inside rounding tolerance (max($2M, 0.1% of assets))
    is filer rounding, not a mezzanine section."""
    facts = _blk_shaped()
    # Shrink the gap to $1M: E = A - L - 1M.
    facts["facts"]["us-gaap"][
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
    ]["units"]["USD"][0]["val"] = 67_774_000_000
    row = _extract(facts)
    assert row.temporary_equity is None


def test_filed_redeemable_nci_plus_residual_temporary_equity() -> None:
    """APLD-shaped: redeemable NCI is filed non-dimensionally, the
    per-series temporary equity is not. The residual lands in the empty
    temporary-equity slot; the filed NCI is untouched."""
    facts = _blk_shaped()
    end = "2026-09-30"
    # Filed redeemable NCI explains part of the $3,850M gap.
    facts["facts"]["us-gaap"][
        "RedeemableNoncontrollingInterestEquityCarryingAmount"
    ] = {"units": {"USD": [_instant(end, 2_000_000_000)]}}
    row = _extract(facts)
    assert row.redeemable_nci == 2_000_000_000
    assert row.temporary_equity == 1_850_000_000
    assert (
        row.total_liabilities
        + row.redeemable_nci
        + row.temporary_equity
        + row.total_equity
        == row.total_assets
    )


def test_filed_values_never_overwritten_when_both_slots_full() -> None:
    """Both mezzanine slots filed and a residual still remains: the gap
    is left as filed rather than inflating either filed value."""
    facts = _blk_shaped()
    end = "2026-09-30"
    facts["facts"]["us-gaap"][
        "RedeemableNoncontrollingInterestEquityCarryingAmount"
    ] = {"units": {"USD": [_instant(end, 1_000_000_000)]}}
    facts["facts"]["us-gaap"][
        "TemporaryEquityCarryingAmountAttributableToParent"
    ] = {"units": {"USD": [_instant(end, 500_000_000)]}}
    row = _extract(facts)
    assert row.redeemable_nci == 1_000_000_000
    assert row.temporary_equity == 500_000_000


def _dlr_shaped() -> dict:
    """Mirror Digital Realty's 2025-12-31 face: A=49,410,468K,
    L=24,564,494K, E=23,346,999K (incl. NCI), temporary equity
    (incl.-NCI variant) 1,498,975K — closes exactly."""
    end = "2025-12-31"
    return {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {"USD": [_rev("2025-10-01", end, 1_600_000_000)]}
                },
                "Assets": {
                    "units": {"USD": [_instant(end, 49_410_468_000)]}
                },
                "Liabilities": {
                    "units": {"USD": [_instant(end, 24_564_494_000)]}
                },
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": {
                    "units": {"USD": [_instant(end, 23_346_999_000)]}
                },
                "TemporaryEquityCarryingAmountIncludingPortionAttributableToNoncontrollingInterests": {
                    "units": {"USD": [_instant(end, 1_498_975_000)]}
                },
            }
        }
    }


def test_including_nci_temporary_equity_tag_extracted() -> None:
    facts = _dlr_shaped()
    # The DLR fixture's revenue fact is a Q4 standalone; extraction must
    # still anchor on it.
    rows = extract_recent_quarterly_financials(
        facts, fiscal_year_end="1231", periods=4
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.temporary_equity == 1_498_975_000
    assert (
        row.total_liabilities + row.temporary_equity + row.total_equity
        == row.total_assets
    )


def test_parent_temporary_equity_tag_wins_over_including_variant() -> None:
    """Gap-fill semantics: where the parent-attributable tag has a fact
    it keeps winning (KDP behavior unchanged); the including variant
    only fills ends the parent tag lacks."""
    facts = _dlr_shaped()
    end = "2025-12-31"
    facts["facts"]["us-gaap"][
        "TemporaryEquityCarryingAmountAttributableToParent"
    ] = {"units": {"USD": [_instant(end, 1_200_000_000)]}}
    rows = extract_recent_quarterly_financials(
        facts, fiscal_year_end="1231", periods=4
    )
    assert rows[0].temporary_equity == 1_200_000_000


def _kkr_shaped(mezz: float = 1_322_308_000) -> dict:
    """Mirror KKR's double-tagged mezzanine: one line filed under both
    the redeemable-NCI tag and the temporary-equity tag, identical
    amounts. A = L + E + one copy."""
    end = "2026-09-30"
    a = 360_655_876_000
    l_val = 200_000_000_000
    e_val = a - l_val - mezz
    return {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {"USD": [_rev("2026-07-01", end, 5_000_000_000)]}
                },
                "Assets": {"units": {"USD": [_instant(end, a)]}},
                "Liabilities": {"units": {"USD": [_instant(end, l_val)]}},
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": {
                    "units": {"USD": [_instant(end, e_val)]}
                },
                "RedeemableNoncontrollingInterestEquityCarryingAmount": {
                    "units": {"USD": [_instant(end, mezz)]}
                },
                "TemporaryEquityCarryingAmountIncludingPortionAttributableToNoncontrollingInterests": {
                    "units": {"USD": [_instant(end, mezz)]}
                },
            }
        }
    }


def test_double_tagged_mezzanine_deduped_to_redeemable_nci() -> None:
    row = _extract(_kkr_shaped())
    assert row.redeemable_nci == 1_322_308_000
    assert row.temporary_equity is None
    assert (
        row.total_liabilities + row.redeemable_nci + row.total_equity
        == row.total_assets
    )


def test_equal_mezzanine_legs_kept_when_both_needed_to_close() -> None:
    """Two distinct lines that happen to be equal: the identity needs
    both copies, so neither is dropped."""
    facts = _kkr_shaped()
    # Grow assets by one more mezzanine copy: A = L + E + 2*mezz.
    facts["facts"]["us-gaap"]["Assets"]["units"]["USD"][0]["val"] += (
        1_322_308_000
    )
    row = _extract(facts)
    assert row.redeemable_nci == 1_322_308_000
    assert row.temporary_equity == 1_322_308_000
    assert (
        row.total_liabilities
        + row.redeemable_nci
        + row.temporary_equity
        + row.total_equity
        == row.total_assets
    )


def test_double_tag_deduped_even_when_within_tolerance() -> None:
    """Tesla-shaped: the $63M double-tag sits inside the $122M identity
    tolerance on $122B of assets, so two copies "close" too — but one
    copy fits strictly better (gap 0 vs $63M), so the duplicate drops."""
    facts = _kkr_shaped(mezz=63_000_000)
    # Scale assets up so tolerance (0.1% of A) exceeds the mezzanine.
    end = "2026-09-30"
    a = 122_070_000_000
    l_val = 48_390_000_000
    e_val = a - l_val - 63_000_000
    facts["facts"]["us-gaap"]["Assets"]["units"]["USD"][0]["val"] = a
    facts["facts"]["us-gaap"]["Liabilities"]["units"]["USD"][0]["val"] = l_val
    facts["facts"]["us-gaap"][
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
    ]["units"]["USD"][0]["val"] = e_val
    assert facts["facts"]["us-gaap"]["Assets"]["units"]["USD"][0]["end"] == end
    row = _extract(facts)
    assert row.redeemable_nci == 63_000_000
    assert row.temporary_equity is None


def test_distinct_mezzanine_values_untouched_by_dedupe() -> None:
    facts = _kkr_shaped()
    end = "2026-09-30"
    # Temporary equity is a different, smaller line; identity needs both.
    facts["facts"]["us-gaap"][
        "TemporaryEquityCarryingAmountIncludingPortionAttributableToNoncontrollingInterests"
    ]["units"]["USD"][0]["val"] = 300_000_000
    facts["facts"]["us-gaap"]["Assets"]["units"]["USD"][0]["val"] = (
        200_000_000_000
        + (360_655_876_000 - 200_000_000_000 - 1_322_308_000)
        + 1_322_308_000
        + 300_000_000
    )
    row = _extract(facts)
    assert row.redeemable_nci == 1_322_308_000
    assert row.temporary_equity == 300_000_000
