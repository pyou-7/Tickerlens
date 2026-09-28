import datetime as dt

from tickerlens.data.xbrl import (
    Metric,
    balance_sheet_metric,
    concept_facts,
    extract_recent_quarterly_financials,
    infer_fiscal_year,
    quarterly_cash_flow_metric,
    quarterly_income_metric,
)


def test_infer_fiscal_year_handles_calendar_and_september_year_ends() -> None:
    # January year-ends label by the year the fiscal year ends in
    # (verified against Walmart's SEC companyfacts: year ended 2025-01-31 -> fy 2025).
    assert infer_fiscal_year(dt.date(2025, 12, 28), "0103") == 2026
    assert infer_fiscal_year(dt.date(2025, 12, 27), "0926") == 2026
    assert infer_fiscal_year(dt.date(2026, 3, 28), "0926") == 2026


def test_infer_fiscal_year_tolerates_floating_year_ends() -> None:
    # Regression: Apple reports fiscalYearEnd 0926 but its floating "last
    # Saturday of September" year-end fell on 2024-09-28. The old hard
    # day-cutoff mislabeled it FY2025, duplicating the "Q4 FY2025" option.
    assert infer_fiscal_year(dt.date(2024, 9, 28), "0926") == 2024
    assert infer_fiscal_year(dt.date(2025, 9, 27), "0926") == 2025
    # A period just after the nominal year-end still belongs to the year
    # that just ended, not the next one.
    assert infer_fiscal_year(dt.date(2025, 1, 4), "1231") == 2024
    assert infer_fiscal_year(dt.date(2024, 12, 31), "1231") == 2024


def test_concept_mapping_falls_back_to_revenues() -> None:
    companyfacts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            fact(
                                start="2026-01-01",
                                end="2026-03-31",
                                val=100,
                                fy=2026,
                                fp="Q1",
                            )
                        ]
                    }
                }
            }
        }
    }

    source_tag, facts = concept_facts(companyfacts, Metric.REVENUE)

    assert source_tag == "Revenues"
    assert facts[0].val == 100


def test_cash_flow_uncumulates_ytd_periods() -> None:
    companyfacts = make_companyfacts(
        revenue_values=[],
        net_income_values=[],
        basic_eps_values=[],
        diluted_eps_values=[],
        opcf_values=[
            ("2025-01-01", "2025-03-31", 100, 2025, "Q1"),
            ("2025-01-01", "2025-06-30", 250, 2025, "Q2"),
            ("2025-01-01", "2025-09-30", 450, 2025, "Q3"),
            ("2025-01-01", "2025-12-31", 700, 2025, "FY"),
        ],
        capex_values=[],
    )

    rows = quarterly_cash_flow_metric(
        companyfacts,
        Metric.OPERATING_CASH_FLOW,
        fiscal_year_end="1231",
    )

    assert [(row.period, row.value) for row in rows] == [
        ("FY2025 Q1", 100),
        ("FY2025 Q2", 150),
        ("FY2025 Q3", 200),
        ("FY2025 Q4", 250),
    ]


def test_recent_quarterly_financials_joins_by_end_date_not_label() -> None:
    companyfacts = make_companyfacts(
        revenue_values=[
            ("2025-03-31", "2025-06-29", 23743, 2025, "Q2"),
            ("2025-06-30", "2025-09-28", 23993, 2025, "Q3"),
            ("2025-09-29", "2025-12-28", 24564, 2025, "Q4"),
            ("2025-12-29", "2026-03-29", 24062, 2026, "Q1"),
        ],
        net_income_values=[
            ("2025-03-31", "2025-06-29", 5537, 2025, "Q2"),
            ("2025-06-30", "2025-09-28", 5152, 2025, "Q3"),
            ("2025-09-29", "2025-12-28", 5116, 2025, "Q4"),
            ("2025-12-29", "2026-03-29", 5235, 2026, "Q1"),
        ],
        basic_eps_values=[
            ("2025-03-31", "2025-06-29", 2.30, 2025, "Q2"),
            ("2025-06-30", "2025-09-28", 2.14, 2025, "Q3"),
            ("2025-09-29", "2025-12-28", 2.12, 2025, "Q4"),
            ("2025-12-29", "2026-03-29", 2.17, 2026, "Q1"),
        ],
        diluted_eps_values=[
            ("2025-03-31", "2025-06-29", 2.29, 2025, "Q2"),
            ("2025-06-30", "2025-09-28", 2.12, 2025, "Q3"),
            ("2025-09-29", "2025-12-28", 2.09, 2025, "Q4"),
            ("2025-12-29", "2026-03-29", 2.14, 2026, "Q1"),
        ],
        opcf_values=[
            ("2024-12-30", "2025-03-30", 4174, 2025, "Q1"),
            ("2024-12-30", "2025-03-30", 4174, 2026, "Q1"),
            ("2024-12-30", "2025-06-29", 8052, 2025, "Q2"),
            ("2024-12-30", "2025-09-28", 17221, 2025, "Q3"),
            ("2024-12-30", "2025-12-28", 24530, 2025, "FY"),
            ("2025-12-29", "2026-03-29", 2514, 2026, "Q1"),
        ],
        capex_values=[
            ("2024-12-30", "2025-03-30", 795, 2025, "Q1"),
            ("2024-12-30", "2025-03-30", 795, 2026, "Q1"),
            ("2024-12-30", "2025-06-29", 1838, 2025, "Q2"),
            ("2024-12-30", "2025-09-28", 2995, 2025, "Q3"),
            ("2024-12-30", "2025-12-28", 4832, 2025, "FY"),
            ("2025-12-29", "2026-03-29", 1049, 2026, "Q1"),
        ],
    )

    rows = extract_recent_quarterly_financials(
        companyfacts,
        fiscal_year_end="0103",
        periods=4,
    )

    assert [(row.period, row.free_cash_flow) for row in rows] == [
        ("FY2025 Q2", 2835),
        ("FY2025 Q3", 8012),
        ("FY2025 Q4", 5472),
        ("FY2026 Q1", 1465),
    ]


def test_balance_sheet_metric_takes_latest_filed_per_end() -> None:
    # Same period end reported twice (a 10-Q then a restated later filing) plus a second
    # quarter. We keep the latest-filed value per end date.
    companyfacts = {
        "facts": {
            "us-gaap": {
                "Assets": {
                    "units": {
                        "USD": [
                            instant_fact("2025-03-29", 331_000, 2025, "Q1", filed="2025-05-01"),
                            # restated later — must win for the same end date
                            instant_fact("2025-03-29", 331_500, 2025, "Q1", filed="2025-08-05"),
                            instant_fact("2025-06-28", 337_000, 2025, "Q2", filed="2025-08-05"),
                        ]
                    }
                }
            }
        }
    }

    values = balance_sheet_metric(companyfacts, Metric.TOTAL_ASSETS, fiscal_year_end="0928")

    assert values[dt.date(2025, 3, 29)] == 331_500  # latest filed wins
    assert values[dt.date(2025, 6, 28)] == 337_000


def test_extract_joins_balance_sheet_by_period_end() -> None:
    companyfacts = make_companyfacts(
        revenue_values=[
            ("2025-12-29", "2026-03-29", 24_062, 2026, "Q1"),
        ],
        net_income_values=[],
        basic_eps_values=[],
        diluted_eps_values=[],
        opcf_values=[],
        capex_values=[],
        assets_values=[
            ("2026-03-29", 331_233, 2026, "Q1"),  # matches the revenue period end
            ("2025-12-28", 344_085, 2025, "Q4"),  # different end — must not leak in
        ],
    )

    rows = extract_recent_quarterly_financials(
        companyfacts,
        fiscal_year_end="0928",
        periods=4,
    )

    assert len(rows) == 1
    assert rows[0].period == "FY2026 Q1"
    assert rows[0].total_assets == 331_233


def make_companyfacts(
    *,
    revenue_values: list[tuple[str, str, float, int, str]],
    net_income_values: list[tuple[str, str, float, int, str]],
    basic_eps_values: list[tuple[str, str, float, int, str]],
    diluted_eps_values: list[tuple[str, str, float, int, str]],
    opcf_values: list[tuple[str, str, float, int, str]],
    capex_values: list[tuple[str, str, float, int, str]],
    assets_values: list[tuple[str, float, int, str]] | None = None,
) -> dict:
    us_gaap = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": units("USD", revenue_values),
        "NetIncomeLoss": units("USD", net_income_values),
        "EarningsPerShareBasic": units("USD/shares", basic_eps_values),
        "EarningsPerShareDiluted": units("USD/shares", diluted_eps_values),
        "NetCashProvidedByUsedInOperatingActivities": units("USD", opcf_values),
        "PaymentsToAcquirePropertyPlantAndEquipment": units("USD", capex_values),
    }
    if assets_values is not None:
        us_gaap["Assets"] = instant_units(assets_values)
    return {"facts": {"us-gaap": us_gaap}}


def units(unit_name: str, values: list[tuple[str, str, float, int, str]]) -> dict:
    return {"units": {unit_name: [fact(*value) for value in values]}}


def instant_units(values: list[tuple[str, float, int, str]]) -> dict:
    return {"units": {"USD": [instant_fact(*value) for value in values]}}


def instant_fact(
    end: str,
    val: float,
    fy: int,
    fp: str,
    filed: str = "2026-04-22",
) -> dict:
    """An instant (point-in-time) balance-sheet fact — has ``end`` but no ``start``."""
    return {
        "end": end,
        "val": val,
        "fy": fy,
        "fp": fp,
        "form": "10-Q" if fp != "FY" else "10-K",
        "filed": filed,
    }


def fact(
    start: str,
    end: str,
    val: float,
    fy: int,
    fp: str,
    filed: str = "2026-04-22",
) -> dict:
    return {
        "start": start,
        "end": end,
        "val": val,
        "fy": fy,
        "fp": fp,
        "form": "10-Q" if fp != "FY" else "10-K",
        "filed": filed,
    }


def _stale_chain_facts() -> dict:
    """Mirror the PLUG case: first-chain tag abandoned for quarterly facts."""
    return {
        "facts": {
            "us-gaap": {
                # First in chain, but quarterly facts end in 2020; only a
                # half-year fact is recent (keeps the tag "alive" overall).
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            fact("2020-10-01", "2020-12-31", 100.0, 2020, "Q4"),
                            fact("2026-01-01", "2026-06-30", 999.0, 2026, "Q2"),
                        ]
                    }
                },
                # Second in chain, with current quarterly facts.
                "RevenueFromContractWithCustomerIncludingAssessedTax": {
                    "units": {
                        "USD": [
                            fact("2026-04-01", "2026-06-30", 200.0, 2026, "Q2"),
                        ]
                    }
                },
            }
        }
    }


def test_concept_facts_skips_abandoned_tag_for_quarterly_window():
    tag, _ = concept_facts(
        _stale_chain_facts(), Metric.REVENUE, staleness_window=(70, 100)
    )
    assert tag == "RevenueFromContractWithCustomerIncludingAssessedTax"


def test_concept_facts_prefers_chain_order_when_fresh():
    cf = _stale_chain_facts()
    # Without the quarterly window the first tag's half-year fact makes it
    # look current, so chain order (semantic preference) wins.
    tag, _ = concept_facts(cf, Metric.REVENUE)
    assert tag == "RevenueFromContractWithCustomerExcludingAssessedTax"


def test_concept_facts_falls_back_to_first_tag_when_all_stale():
    cf = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": [fact("2020-10-01", "2020-12-31", 100.0, 2020, "Q4")]}
                },
            }
        }
    }
    tag, _ = concept_facts(cf, Metric.REVENUE, staleness_window=(70, 100))
    assert tag == "RevenueFromContractWithCustomerExcludingAssessedTax"


def _comparative_relabel_facts(restated_val: float | None = None) -> dict:
    """Mirror the JNJ case: Q3-2024 appears twice — the original 10-Q labels it
    fy=2024, while the comparative column in next year's 10-Q re-tags it
    fy=2025. SEC's nominal fiscalYearEnd ("0103") agrees with the wrong one."""
    original = fact(
        "2024-06-30", "2024-09-29", 22471.0, 2024, "Q3", filed="2024-10-23"
    )
    comparative = fact(
        "2024-06-30",
        "2024-09-29",
        restated_val if restated_val is not None else 22471.0,
        2025,
        "Q3",
        filed="2025-10-22",
    )
    return {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": [original, comparative]}
                }
            }
        }
    }


def test_duplicate_facts_keep_original_filing_labels():
    metrics = quarterly_income_metric(
        _comparative_relabel_facts(), Metric.REVENUE, fiscal_year_end="0103"
    )
    assert len(metrics) == 1
    assert (metrics[0].fy, metrics[0].fp) == (2024, "Q3")
    assert metrics[0].end == dt.date(2024, 9, 29)


def test_duplicate_facts_take_restated_value_from_latest_filing():
    metrics = quarterly_income_metric(
        _comparative_relabel_facts(restated_val=22500.0),
        Metric.REVENUE,
        fiscal_year_end="0103",
    )
    assert len(metrics) == 1
    # Labels still describe the original period; the number reflects the restatement.
    assert (metrics[0].fy, metrics[0].fp) == (2024, "Q3")
    assert metrics[0].value == 22500.0
