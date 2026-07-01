import datetime as dt

from tickerlens.data.xbrl import (
    Metric,
    balance_sheet_metric,
    concept_facts,
    extract_recent_quarterly_financials,
    infer_fiscal_year,
    quarterly_cash_flow_metric,
)


def test_infer_fiscal_year_handles_calendar_and_september_year_ends() -> None:
    assert infer_fiscal_year(dt.date(2025, 12, 28), "0103") == 2025
    assert infer_fiscal_year(dt.date(2025, 12, 27), "0926") == 2026
    assert infer_fiscal_year(dt.date(2026, 3, 28), "0926") == 2026


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
