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


def test_missing_liabilities_derived_from_assets_minus_equity() -> None:
    """Mirror the Eli Lilly (LLY) case: no standalone ``Liabilities`` tag —
    only Assets and StockholdersEquity instants. Total liabilities is derived
    from the accounting identity instead of showing None."""
    companyfacts = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": [fact("2026-01-01", "2026-03-31", 10_000, 2026, "Q1")]}
                },
                "Assets": {
                    "units": {"USD": [instant_fact("2026-03-31", 142_283, 2026, "Q1")]}
                },
                "StockholdersEquity": {
                    "units": {"USD": [instant_fact("2026-03-31", 33_879, 2026, "Q1")]}
                },
            }
        }
    }

    rows = extract_recent_quarterly_financials(companyfacts, fiscal_year_end="1231", periods=4)

    assert len(rows) == 1
    assert rows[0].total_assets == 142_283
    assert rows[0].total_equity == 33_879
    assert rows[0].total_liabilities == 142_283 - 33_879


def test_explicit_liabilities_tag_never_overwritten_by_identity() -> None:
    """A filed Liabilities value wins over the Assets − Equity derivation."""
    companyfacts = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": [fact("2026-01-01", "2026-03-31", 10_000, 2026, "Q1")]}
                },
                "Assets": {
                    "units": {"USD": [instant_fact("2026-03-31", 142_283, 2026, "Q1")]}
                },
                "StockholdersEquity": {
                    "units": {"USD": [instant_fact("2026-03-31", 33_879, 2026, "Q1")]}
                },
                "Liabilities": {
                    "units": {"USD": [instant_fact("2026-03-31", 100_000, 2026, "Q1")]}
                },
            }
        }
    }

    rows = extract_recent_quarterly_financials(companyfacts, fiscal_year_end="1231", periods=4)

    assert len(rows) == 1
    assert rows[0].total_liabilities == 100_000


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


def _nvda_capex_tag_switch_facts() -> dict:
    """Mirror the NVDA case: ``PaymentsToAcquirePropertyPlantAndEquipment``
    has facts ending in 2020; CapEx is now filed quarterly under
    ``PaymentsToAcquireProductiveAssets``."""
    return {
        "facts": {
            "us-gaap": {
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "units": {
                        "USD": [
                            fact("2020-04-27", "2020-07-26", 217_000_000.0, 2021, "Q2"),
                        ]
                    }
                },
                "PaymentsToAcquireProductiveAssets": {
                    "units": {
                        "USD": [
                            fact("2026-01-26", "2026-04-26", 1_757_000_000.0, 2027, "Q1"),
                            fact("2026-01-26", "2026-07-26", 4_434_000_000.0, 2027, "Q2"),
                        ]
                    }
                },
            }
        }
    }


def test_capex_falls_back_to_productive_assets_tag():
    tag, _ = concept_facts(_nvda_capex_tag_switch_facts(), Metric.CAPEX)
    assert tag == "PaymentsToAcquireProductiveAssets"


def test_capex_keeps_ppande_tag_when_fresh():
    cf = _nvda_capex_tag_switch_facts()
    # A filer still using the classic tag: chain order (semantic preference)
    # wins because both tags are current.
    cf["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"]["units"][
        "USD"
    ].append(fact("2026-01-01", "2026-03-31", 500_000_000.0, 2026, "Q1"))
    tag, _ = concept_facts(cf, Metric.CAPEX)
    assert tag == "PaymentsToAcquirePropertyPlantAndEquipment"


def test_net_income_falls_back_to_common_stockholders_tag_when_abandoned() -> None:
    """Mirror the Realty Income (O) case: ``NetIncomeLoss`` quarterly facts
    stop at 2025-09-30 (273 days behind); the filer now reports net income as
    ``NetIncomeLossAvailableToCommonStockholdersBasic`` through 2026-06-30.
    The lag exceeds the staleness threshold, so the fallback wins.
    """
    companyfacts = {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            fact("2025-07-01", "2025-09-30", 315_771_000.0, 2025, "Q3"),
                        ]
                    }
                },
                "NetIncomeLossAvailableToCommonStockholdersBasic": {
                    "units": {
                        "USD": [
                            fact("2026-01-01", "2026-03-31", 311_766_000.0, 2026, "Q1"),
                            fact("2026-04-01", "2026-06-30", 343_955_000.0, 2026, "Q2"),
                        ]
                    }
                },
            }
        }
    }
    tag, facts = concept_facts(companyfacts, Metric.NET_INCOME, staleness_window=(70, 100))
    assert tag == "NetIncomeLossAvailableToCommonStockholdersBasic"
    assert max(f.end for f in facts).isoformat() == "2026-06-30"


def test_net_income_prefers_classic_tag_when_both_fresh() -> None:
    """Chain order (semantic preference) wins when both net-income tags are
    current — the fallback only kicks in for abandoned tags."""
    companyfacts = {
        "facts": {
            "us-gaap": {
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            fact("2026-04-01", "2026-06-30", 500_000_000.0, 2026, "Q2"),
                        ]
                    }
                },
                "NetIncomeLossAvailableToCommonStockholdersBasic": {
                    "units": {
                        "USD": [
                            fact("2026-04-01", "2026-06-30", 480_000_000.0, 2026, "Q2"),
                        ]
                    }
                },
            }
        }
    }
    tag, _ = concept_facts(companyfacts, Metric.NET_INCOME, staleness_window=(70, 100))
    assert tag == "NetIncomeLoss"


def test_net_income_falls_back_to_profit_loss_when_nothing_else() -> None:
    """``ProfitLoss`` serves as the last-resort net-income tag when the filer
    reports neither ``NetIncomeLoss`` nor the common-stockholders tag."""
    companyfacts = {
        "facts": {
            "us-gaap": {
                "ProfitLoss": {
                    "units": {
                        "USD": [
                            fact("2026-04-01", "2026-06-30", 123_000_000.0, 2026, "Q2"),
                        ]
                    }
                },
            }
        }
    }
    tag, facts = concept_facts(companyfacts, Metric.NET_INCOME, staleness_window=(70, 100))
    assert tag == "ProfitLoss"
    assert facts[0].val == 123_000_000.0


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


def _xbrl_row(fy: int, fp: str, end: dt.date) -> "QuarterlyFinancials":
    from tickerlens.data.xbrl import QuarterlyFinancials

    return QuarterlyFinancials(fy=fy, fp=fp, end=end, revenue=1.0)


def test_dedupe_period_labels_walks_earlier_comparative_back() -> None:
    """XOM's new-CIK dataset holds only the 2026 10-Q, so the 2025-06-30
    comparative column is tagged fy=2026 — colliding with real Q2 FY2026."""
    from tickerlens.data.xbrl import _dedupe_period_labels

    rows = [
        _xbrl_row(2026, "Q2", dt.date(2025, 6, 30)),
        _xbrl_row(2026, "Q2", dt.date(2026, 6, 30)),
    ]
    fixed = _dedupe_period_labels(rows)
    labels = sorted((r.fy, r.fp) for r in fixed)
    assert labels == [(2025, "Q2"), (2026, "Q2")]
    # the later (trustworthy) end keeps its label
    later = next(r for r in fixed if r.end == dt.date(2026, 6, 30))
    assert (later.fy, later.fp) == (2026, "Q2")


def test_dedupe_period_labels_leaves_unique_labels_alone() -> None:
    from tickerlens.data.xbrl import _dedupe_period_labels

    rows = [
        _xbrl_row(2025, "Q1", dt.date(2025, 3, 31)),
        _xbrl_row(2025, "Q2", dt.date(2025, 6, 30)),
    ]
    fixed = _dedupe_period_labels(rows)
    assert [(r.fy, r.fp) for r in fixed] == [(2025, "Q1"), (2025, "Q2")]


def _bank_companyfacts(
    noninterest: list[dict] | None,
    interest_net: list[dict] | None,
    revenues: list[dict] | None = None,
) -> dict:
    tags: dict[str, dict] = {}
    if noninterest is not None:
        tags["NoninterestIncome"] = {"units": {"USD": noninterest}}
    if interest_net is not None:
        tags["InterestIncomeExpenseNet"] = {"units": {"USD": interest_net}}
    if revenues is not None:
        tags["Revenues"] = {"units": {"USD": revenues}}
    return {"facts": {"us-gaap": tags}}


def test_bank_revenue_composite_sums_components() -> None:
    """Finance SICs get NoninterestIncome + InterestIncomeExpenseNet summed."""
    companyfacts = _bank_companyfacts(
        noninterest=[
            fact("2026-01-01", "2026-03-31", 22000.0, 2026, "Q1"),
            fact("2026-04-01", "2026-06-30", 21700.0, 2026, "Q2"),
        ],
        interest_net=[
            fact("2026-01-01", "2026-03-31", 23300.0, 2026, "Q1"),
            fact("2026-04-01", "2026-06-30", 23200.0, 2026, "Q2"),
        ],
    )

    metrics = quarterly_income_metric(
        companyfacts, Metric.REVENUE, fiscal_year_end="1231", sic="6021"
    )

    assert [(m.end, m.value) for m in metrics] == [
        (dt.date(2026, 3, 31), 45300.0),
        (dt.date(2026, 6, 30), 44900.0),
    ]


def test_bank_revenue_composite_beats_stale_revenues_chain() -> None:
    """JPM case: generic chain's quarterly facts end in 2014; fresh bank
    components must win so the revenue anchor (and every joined metric)
    stays current."""
    companyfacts = _bank_companyfacts(
        noninterest=[fact("2026-01-01", "2026-03-31", 22000.0, 2026, "Q1")],
        interest_net=[fact("2026-01-01", "2026-03-31", 23300.0, 2026, "Q1")],
        revenues=[
            fact("2014-01-01", "2014-03-31", 25000.0, 2014, "Q1"),
            fact("2025-01-01", "2025-12-31", 182000.0, 2025, "FY"),
        ],
    )

    metrics = quarterly_income_metric(
        companyfacts, Metric.REVENUE, fiscal_year_end="1231", sic=6021
    )

    assert [m.end for m in metrics] == [dt.date(2026, 3, 31)]
    assert metrics[0].value == 45300.0


def test_bank_revenue_uses_fresh_revenues_when_available() -> None:
    """Finance SIC with current quarterly Revenues uses it directly (the
    finance preference), even without bank components."""
    companyfacts = _bank_companyfacts(
        noninterest=None,
        interest_net=None,
        revenues=[_recent_fact(149, 60, 50000.0)],
    )

    metrics = quarterly_income_metric(
        companyfacts, Metric.REVENUE, fiscal_year_end="1231", sic="6021"
    )

    assert len(metrics) == 1
    assert metrics[0].value == 50000.0
    assert metrics[0].source_tag == "Revenues"


def test_non_bank_sic_uses_generic_chain() -> None:
    """A manufacturer with both generic and bank-component tags uses the
    generic chain — the composite must not leak outside finance SICs."""
    companyfacts = _bank_companyfacts(
        noninterest=[fact("2026-01-01", "2026-03-31", 1000.0, 2026, "Q1")],
        interest_net=[fact("2026-01-01", "2026-03-31", 2000.0, 2026, "Q1")],
        revenues=[fact("2026-01-01", "2026-03-31", 50000.0, 2026, "Q1")],
    )

    metrics = quarterly_income_metric(
        companyfacts, Metric.REVENUE, fiscal_year_end="1231", sic="3571"
    )

    assert [(m.end, m.value, m.source_tag) for m in metrics] == [
        (dt.date(2026, 3, 31), 50000.0, "Revenues")
    ]


def test_is_bank_sic_boundaries() -> None:
    from tickerlens.data.xbrl import _is_bank_sic

    assert _is_bank_sic(6021)
    assert _is_bank_sic("6211")
    assert _is_bank_sic(6000)
    assert _is_bank_sic(6299)
    assert not _is_bank_sic(5999)
    assert not _is_bank_sic(6300)  # insurers have a different revenue structure
    assert not _is_bank_sic(None)
    assert not _is_bank_sic("n/a")


def test_bank_composite_end_to_end_anchors_recent_quarters() -> None:
    """extract_recent_quarterly_financials with a bank SIC anchors on the
    composite, so joined metrics (net income) follow recent ends."""
    companyfacts = _bank_companyfacts(
        noninterest=[fact("2026-01-01", "2026-03-31", 22000.0, 2026, "Q1")],
        interest_net=[fact("2026-01-01", "2026-03-31", 23300.0, 2026, "Q1")],
    )
    companyfacts["facts"]["us-gaap"]["NetIncomeLoss"] = {
        "units": {
            "USD": [fact("2026-01-01", "2026-03-31", 15000.0, 2026, "Q1")]
        }
    }

    rows = extract_recent_quarterly_financials(
        companyfacts, fiscal_year_end="1231", periods=4, sic="6021"
    )

    assert [(r.end, r.revenue, r.net_income) for r in rows] == [
        (dt.date(2026, 3, 31), 45300.0, 15000.0)
    ]


def _recent_fact(start_offset: int, end_offset: int, val: float, filed_offset: int = 20) -> dict:
    """A 10-Q fact ending ``end_offset`` days ago (durations in the 70-100d window)."""
    today = dt.date.today()
    end = today - dt.timedelta(days=end_offset)
    start = end - dt.timedelta(days=89)
    filed = today - dt.timedelta(days=filed_offset)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "val": val,
        "fy": end.year,
        "fp": f"Q{(end.month - 1) // 3 + 1}",
        "form": "10-Q",
        "filed": filed.isoformat(),
    }


def test_finance_revenue_prefers_total_revenues_over_contract_subcomponent() -> None:
    """MET case: insurer SIC with fresh Revenues ($19B total) and a fresh but
    tiny contract-revenue tag ($0.7B fee income) must use Revenues."""
    companyfacts = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": [_recent_fact(149, 60, 724_000_000.0)]}
                },
                "Revenues": {
                    "units": {"USD": [_recent_fact(149, 60, 19_154_000_000.0)]}
                },
            }
        }
    }

    metrics = quarterly_income_metric(
        companyfacts, Metric.REVENUE, fiscal_year_end="1231", sic="6331"
    )

    assert len(metrics) == 1
    assert metrics[0].value == 19_154_000_000.0
    assert metrics[0].source_tag == "Revenues"


def test_finance_revenue_stale_revenues_nonbank_falls_back_to_generic_chain() -> None:
    """Insurer whose Revenues quarterly facts are absolutely stale (>400d)
    falls back to the generic chain (fresh contract tag wins there)."""
    companyfacts = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": [_recent_fact(149, 60, 724_000_000.0)]}
                },
                "Revenues": {
                    "units": {"USD": [_recent_fact(789, 700, 15_000_000_000.0)]}
                },
            }
        }
    }

    metrics = quarterly_income_metric(
        companyfacts, Metric.REVENUE, fiscal_year_end="1231", sic="6331"
    )

    assert len(metrics) == 1
    assert metrics[0].value == 724_000_000.0
    assert metrics[0].source_tag == "RevenueFromContractWithCustomerExcludingAssessedTax"


def test_finance_revenue_stale_revenues_bank_uses_composite() -> None:
    """Bank SIC with absolutely-stale Revenues skips the finance preference
    and uses the NoninterestIncome + net-interest-income composite."""
    companyfacts = _bank_companyfacts(
        noninterest=[_recent_fact(149, 60, 22_000_000_000.0)],
        interest_net=[_recent_fact(149, 60, 23_300_000_000.0)],
        revenues=[_recent_fact(789, 700, 25_000_000_000.0)],
    )

    metrics = quarterly_income_metric(
        companyfacts, Metric.REVENUE, fiscal_year_end="1231", sic="6021"
    )

    assert len(metrics) == 1
    assert metrics[0].value == 45_300_000_000.0
    assert "NoninterestIncome" in metrics[0].source_tag


def test_is_finance_sic_boundaries() -> None:
    from tickerlens.data.xbrl import _is_finance_sic

    assert _is_finance_sic(6021)   # bank
    assert _is_finance_sic(6331)   # insurer
    assert _is_finance_sic("6798")  # REIT
    assert _is_finance_sic(6000)
    assert _is_finance_sic(6999)
    assert not _is_finance_sic(5999)
    assert not _is_finance_sic(7000)
    assert not _is_finance_sic(None)
    assert not _is_finance_sic("n/a")


def test_balance_sheet_tag_abandonment_picks_fresh_tag() -> None:
    # Regression: UNH abandoned StockholdersEquity in 2015 (fresh tag:
    # StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest);
    # PG abandoned CashAndCashEquivalentsAtCarryingValue in 2019 (fresh tag:
    # CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents). Instant
    # (point-in-time) facts carry no ``start``, which made _newest_in_window
    # return None for every tag — so the staleness check never engaged and the
    # first (abandoned) tag always won, blanking the metric for all quarters.
    companyfacts = {
        "facts": {
            "us-gaap": {
                "StockholdersEquity": instant_units([("2015-06-30", 40_000, 2015, "Q2")]),
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": instant_units(
                    [("2026-06-30", 105_000, 2026, "Q2")]
                ),
            }
        }
    }
    source_tag, _ = concept_facts(companyfacts, Metric.TOTAL_EQUITY, instant=True)
    assert source_tag == (
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
    )


def test_balance_sheet_prefers_total_equity_when_both_fresh() -> None:
    # Chain order expresses semantic preference when both tags are current:
    # total equity (including noncontrolling interests) is the tag that
    # satisfies Assets = Liabilities + Equity (NEE's 2026-03-31: 154.79 +
    # 66.63 = 221.42 exactly; parent-only StockholdersEquity leaves an
    # $11.4B gap), so it wins over the parent-only tag.
    companyfacts = {
        "facts": {
            "us-gaap": {
                "StockholdersEquity": instant_units([("2026-06-30", 40_000, 2026, "Q2")]),
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": instant_units(
                    [("2026-06-30", 105_000, 2026, "Q2")]
                ),
            }
        }
    }
    source_tag, _ = concept_facts(companyfacts, Metric.TOTAL_EQUITY, instant=True)
    assert (
        source_tag
        == "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"
    )


def test_balance_sheet_metric_uses_fresh_tag_values() -> None:
    # End to end: the fresh tag's values, not the abandoned tag's (which has
    # no overlap with recent quarters), must land on the recent period ends.
    companyfacts = {
        "facts": {
            "us-gaap": {
                "StockholdersEquity": instant_units([("2015-06-30", 40_000, 2015, "Q2")]),
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": instant_units(
                    [
                        ("2026-03-31", 100_000, 2026, "Q1"),
                        ("2026-06-30", 105_000, 2026, "Q2"),
                    ]
                ),
            }
        }
    }
    values = balance_sheet_metric(companyfacts, Metric.TOTAL_EQUITY)
    assert values[dt.date(2026, 6, 30)] == 105_000
    assert values[dt.date(2026, 3, 31)] == 100_000


def _eps_metric(
    metric, end: str, val: float, fy: int, fp: str, source_tag: str
) -> "PeriodMetric":
    from tickerlens.data.xbrl import PeriodMetric

    return PeriodMetric(
        metric=metric, fy=fy, fp=fp, end=dt.date.fromisoformat(end), value=val,
        source_tag=source_tag,
    )


def test_fill_missing_eps_basic_prefers_basic_and_fills_gap() -> None:
    from tickerlens.data.xbrl import _fill_missing_eps_basic

    basic = [
        _eps_metric(Metric.EPS_BASIC, "2026-03-31", 17.74, 2026, "Q1", "EarningsPerShareBasic"),
    ]
    diluted = [
        _eps_metric(Metric.EPS_DILUTED, "2026-03-31", 17.55, 2026, "Q1", "EarningsPerShareDiluted"),
        _eps_metric(Metric.EPS_DILUTED, "2026-06-30", 20.98, 2026, "Q2", "EarningsPerShareDiluted"),
    ]
    merged = _fill_missing_eps_basic(basic, diluted)
    by_end = {m.end: m for m in merged}
    # Basic fact survives where it exists (17.74, not diluted's 17.55).
    assert by_end[dt.date(2026, 3, 31)].value == 17.74
    # Missing quarter filled from diluted, labeled EPS_BASIC, source noted.
    filled = by_end[dt.date(2026, 6, 30)]
    assert filled.value == 20.98
    assert filled.metric == Metric.EPS_BASIC
    assert filled.source_tag == "EarningsPerShareDiluted"


def test_fill_missing_eps_basic_empty_inputs() -> None:
    from tickerlens.data.xbrl import _fill_missing_eps_basic

    assert _fill_missing_eps_basic([], []) == []
    only_diluted = [
        _eps_metric(Metric.EPS_DILUTED, "2026-06-30", 20.98, 2026, "Q2", "EarningsPerShareDiluted"),
    ]
    merged = _fill_missing_eps_basic([], only_diluted)
    assert len(merged) == 1 and merged[0].value == 20.98


def test_capex_falls_back_to_other_ppande_tag() -> None:
    """Mirror the Eli Lilly (LLY) case: no ``PaymentsToAcquirePropertyPlantAndEquipment``
    facts at all, ``PaymentsToAcquireProductiveAssets`` abandoned in 2022, and
    CapEx filed quarterly as ``PaymentsToAcquireOtherPropertyPlantAndEquipment``."""
    companyfacts = {
        "facts": {
            "us-gaap": {
                "PaymentsToAcquireProductiveAssets": {
                    "units": {
                        "USD": [
                            fact("2022-01-01", "2022-03-31", 400_000_000.0, 2022, "Q1"),
                        ]
                    }
                },
                "PaymentsToAcquireOtherPropertyPlantAndEquipment": {
                    "units": {
                        "USD": [
                            fact("2026-01-01", "2026-03-31", 1_200_000_000.0, 2026, "Q1"),
                            fact("2026-01-01", "2026-06-30", 2_500_000_000.0, 2026, "Q2"),
                        ]
                    }
                },
            }
        }
    }

    tag, _ = concept_facts(companyfacts, Metric.CAPEX)
    assert tag == "PaymentsToAcquireOtherPropertyPlantAndEquipment"


def test_cash_flow_9m_window_covers_52week_filer() -> None:
    """Mirror the Costco (COST) case: a 52/53-week filer's 9M YTD fact is
    251 days — below the old 255-day floor — so Q3 could not be uncumulated
    and FCF showed None."""
    companyfacts = make_companyfacts(
        revenue_values=[],
        net_income_values=[],
        basic_eps_values=[],
        diluted_eps_values=[],
        opcf_values=[
            ("2025-09-01", "2025-11-23", 3_000, 2026, "Q1"),   # 83d
            ("2025-09-01", "2026-02-15", 5_500, 2026, "Q2"),   # 167d
            ("2025-09-01", "2026-05-10", 9_000, 2026, "Q3"),   # 251d
        ],
        capex_values=[],
    )

    rows = quarterly_cash_flow_metric(
        companyfacts,
        Metric.OPERATING_CASH_FLOW,
        fiscal_year_end="0830",
    )

    assert [(row.period, row.value) for row in rows] == [
        ("FY2026 Q1", 3_000),
        ("FY2026 Q2", 2_500),
        ("FY2026 Q3", 3_500),
    ]


def test_missing_equity_derived_from_assets_minus_liabilities() -> None:
    """Mirror the Visa (V) case: no standalone equity tag — only Assets and
    Liabilities instants. Total equity is derived from the accounting
    identity instead of showing None."""
    companyfacts = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": [fact("2026-01-01", "2026-03-31", 10_000, 2026, "Q1")]}
                },
                "Assets": {
                    "units": {"USD": [instant_fact("2026-03-31", 95_049, 2026, "Q1")]}
                },
                "Liabilities": {
                    "units": {"USD": [instant_fact("2026-03-31", 59_388, 2026, "Q1")]}
                },
            }
        }
    }

    rows = extract_recent_quarterly_financials(companyfacts, fiscal_year_end="0930", periods=4)

    assert len(rows) == 1
    assert rows[0].total_assets == 95_049
    assert rows[0].total_liabilities == 59_388
    assert rows[0].total_equity == 95_049 - 59_388


def test_assets_never_derived_from_identity() -> None:
    """Assets is the anchor of the identity — when only Liabilities and
    Equity are filed, assets stays None rather than being fabricated."""
    companyfacts = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": [fact("2026-01-01", "2026-03-31", 10_000, 2026, "Q1")]}
                },
                "Liabilities": {
                    "units": {"USD": [instant_fact("2026-03-31", 59_388, 2026, "Q1")]}
                },
                "StockholdersEquity": {
                    "units": {"USD": [instant_fact("2026-03-31", 35_661, 2026, "Q1")]}
                },
            }
        }
    }

    rows = extract_recent_quarterly_financials(companyfacts, fiscal_year_end="0930", periods=4)

    assert len(rows) == 1
    assert rows[0].total_assets is None
    assert rows[0].total_liabilities == 59_388
    assert rows[0].total_equity == 35_661


def _duol_like_companyfacts(
    *,
    net_income_values: list,
    basic_eps_values: list,
    diluted_eps_values: list,
) -> dict:
    """DUOL FY2025-shaped facts: a huge Q3 one-off (tax benefit) makes the
    naive FY_EPS − 9M_EPS subtraction visibly wrong."""
    return make_companyfacts(
        revenue_values=[
            ("2025-01-01", "2025-03-31", 230_743_000, 2025, "Q1"),
            ("2025-04-01", "2025-06-30", 252_265_000, 2025, "Q2"),
            ("2025-07-01", "2025-09-30", 271_713_000, 2025, "Q3"),
            ("2025-01-01", "2025-12-31", 1_015_721_000, 2025, "FY"),
        ],
        net_income_values=net_income_values,
        basic_eps_values=basic_eps_values,
        diluted_eps_values=diluted_eps_values,
        opcf_values=[],
        capex_values=[],
    )


def test_q4_eps_derived_from_net_income_and_implied_shares() -> None:
    # Regression: DUOL's FY2025 Q4 showed diluted EPS $0.94 ABOVE basic $0.88
    # (arithmetically impossible) because Q4 was derived as FY_EPS − 9M_EPS
    # while the two figures divide by different share counts. Q4 EPS is now
    # Q4 net income over the implied Q4 share count.
    ni = [
        ("2025-01-01", "2025-03-31", 35_135_000, 2025, "Q1"),
        ("2025-04-01", "2025-06-30", 44_781_000, 2025, "Q2"),
        ("2025-07-01", "2025-09-30", 292_195_000, 2025, "Q3"),
        ("2025-01-01", "2025-09-30", 372_111_000, 2025, "Q3"),
        ("2025-01-01", "2025-12-31", 414_065_000, 2025, "FY"),
    ]
    basic_eps = [
        ("2025-01-01", "2025-03-31", 0.78, 2025, "Q1"),
        ("2025-04-01", "2025-06-30", 0.98, 2025, "Q2"),
        ("2025-07-01", "2025-09-30", 6.36, 2025, "Q3"),
        ("2025-01-01", "2025-09-30", 8.17, 2025, "Q3"),
        ("2025-01-01", "2025-12-31", 9.05, 2025, "FY"),
    ]
    diluted_eps = [
        ("2025-01-01", "2025-03-31", 0.72, 2025, "Q1"),
        ("2025-04-01", "2025-06-30", 0.91, 2025, "Q2"),
        ("2025-07-01", "2025-09-30", 5.95, 2025, "Q3"),
        ("2025-01-01", "2025-09-30", 7.63, 2025, "Q3"),
        ("2025-01-01", "2025-12-31", 8.57, 2025, "FY"),
    ]
    companyfacts = _duol_like_companyfacts(
        net_income_values=ni, basic_eps_values=basic_eps, diluted_eps_values=diluted_eps
    )
    basic = {m.end: m for m in quarterly_income_metric(companyfacts, Metric.EPS_BASIC, "1231")}
    diluted = {
        m.end: m for m in quarterly_income_metric(companyfacts, Metric.EPS_DILUTED, "1231")
    }
    q4 = dt.date(2025, 12, 31)
    # Q4 NI 41,954,000 over implied Q4 shares: basic ≈ 0.9047, diluted ≈ 0.8935
    assert round(basic[q4].value, 4) == 0.9047
    assert round(diluted[q4].value, 4) == 0.8935
    assert basic[q4].value > diluted[q4].value  # ranking can never invert


def test_q4_eps_falls_back_to_subtraction_without_ni_facts() -> None:
    # No NetIncomeLoss facts: keep the old subtraction path, but rounded to
    # the inputs' precision (9.05 − 8.17 = 0.88, not 0.8800000000000008).
    companyfacts = _duol_like_companyfacts(
        net_income_values=[],
        basic_eps_values=[
            ("2025-01-01", "2025-09-30", 8.17, 2025, "Q3"),
            ("2025-01-01", "2025-12-31", 9.05, 2025, "FY"),
        ],
        diluted_eps_values=[],
    )
    metrics = {
        m.end: m for m in quarterly_income_metric(companyfacts, Metric.EPS_BASIC, "1231")
    }
    assert metrics[dt.date(2025, 12, 31)].value == 0.88


def test_q4_eps_falls_back_when_eps_zero() -> None:
    # A zero annual EPS would divide by zero in the implied-shares path;
    # fall back to subtraction instead of crashing.
    companyfacts = _duol_like_companyfacts(
        net_income_values=[
            ("2025-01-01", "2025-09-30", 372_111_000, 2025, "Q3"),
            ("2025-01-01", "2025-12-31", 414_065_000, 2025, "FY"),
        ],
        basic_eps_values=[
            ("2025-01-01", "2025-09-30", 8.17, 2025, "Q3"),
            ("2025-01-01", "2025-12-31", 0.0, 2025, "FY"),
        ],
        diluted_eps_values=[],
    )
    metrics = {
        m.end: m for m in quarterly_income_metric(companyfacts, Metric.EPS_BASIC, "1231")
    }
    assert metrics[dt.date(2025, 12, 31)].value == -8.17


def test_fcf_suppressed_for_finance_sic() -> None:
    # SoFi (SIC 6199) files both OpCF and CapEx tags, but FCF is not a
    # meaningful metric for lenders — banks/insurers/REITs already render
    # "—" because they file no CapEx tag. Finance filers suppress explicitly
    # so the KPI card doesn't show a misleading -$4B.
    companyfacts = make_companyfacts(
        revenue_values=[("2025-01-01", "2025-03-31", 1_000_000_000, 2025, "Q1")],
        net_income_values=[("2025-01-01", "2025-03-31", 100_000_000, 2025, "Q1")],
        basic_eps_values=[("2025-01-01", "2025-03-31", 0.10, 2025, "Q1")],
        diluted_eps_values=[("2025-01-01", "2025-03-31", 0.10, 2025, "Q1")],
        opcf_values=[("2025-01-01", "2025-03-31", -2_000_000_000, 2025, "Q1")],
        capex_values=[("2025-01-01", "2025-03-31", 50_000_000, 2025, "Q1")],
    )
    rows = extract_recent_quarterly_financials(
        companyfacts, fiscal_year_end="1231", sic="6199"
    )
    assert len(rows) == 1
    assert rows[0].free_cash_flow is None
    # Operating companies are unaffected.
    rows = extract_recent_quarterly_financials(
        companyfacts, fiscal_year_end="1231", sic="3571"
    )
    assert rows[0].free_cash_flow == -2_050_000_000


def test_mislabeled_q4_stub_relabeled_from_fy() -> None:
    # Regression (defect-hunt round 13, ABBV): the 10-K tags its 91-day Q4
    # Revenues stub fp="FY" (verified against raw SEC JSON — the filer's own
    # label, not our transform). The phantom FY row stole a slot in the
    # 8-quarter slice (ABBV seeded 7 quarters) and collided on
    # (cik, period_end) at upsert. The filer's own quarterly fact is
    # authoritative: relabel it Q4 and drop the derived duplicate.
    companyfacts = make_companyfacts(
        revenue_values=[
            ("2025-01-01", "2025-03-31", 13_340_000_000, 2025, "Q1"),
            ("2025-04-01", "2025-06-30", 15_420_000_000, 2025, "Q2"),
            ("2025-07-01", "2025-09-30", 15_780_000_000, 2025, "Q3"),
            ("2025-01-01", "2025-09-30", 44_540_000_000, 2025, "Q3"),
            ("2025-01-01", "2025-12-31", 61_160_000_000, 2025, "FY"),
            ("2025-10-01", "2025-12-31", 16_618_000_000, 2025, "FY"),  # mislabeled Q4 stub
        ],
        net_income_values=[],
        basic_eps_values=[],
        diluted_eps_values=[],
        opcf_values=[],
        capex_values=[],
    )
    metrics = {
        m.end: m for m in quarterly_income_metric(companyfacts, Metric.REVENUE, "1231")
    }
    q4 = metrics[dt.date(2025, 12, 31)]
    assert q4.fp == "Q4"
    # The filer's own stub fact wins over the FY−9M derivation (16_620_000_000).
    assert q4.value == 16_618_000_000
    assert all(m.fp != "FY" for m in metrics.values())


def test_mislabeled_q4_stub_fixed_on_finance_revenue_path() -> None:
    # Same ABBV-shaped mislabeling, but through _finance_total_revenue (the
    # path REITs like AMT take): without the fix the phantom FY row stole a
    # quarter slot (AMT seeded 7 quarters).
    from tickerlens.data.xbrl import _finance_total_revenue

    # Note: _finance_total_revenue applies an *absolute* freshness check
    # against today, so the fixture uses 2026 dates (the generic-path test
    # above can use 2025 dates because its staleness rule is relative).
    companyfacts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            fact("2026-01-01", "2026-03-31", 2_560_000_000, 2026, "Q1"),
                            fact("2026-04-01", "2026-06-30", 2_630_000_000, 2026, "Q2"),
                            fact("2026-07-01", "2026-09-30", 2_720_000_000, 2026, "Q3"),
                            fact("2026-01-01", "2026-09-30", 7_910_000_000, 2026, "Q3"),
                            fact("2026-01-01", "2026-12-31", 10_650_000_000, 2026, "FY"),
                            # Mislabeled Q4 stub: 92-day fact tagged fp="FY".
                            fact("2026-10-01", "2026-12-31", 2_740_000_000, 2026, "FY"),
                        ]
                    }
                }
            }
        }
    }
    metrics = {m.end: m for m in _finance_total_revenue(companyfacts, "1231")}
    q4 = metrics[dt.date(2026, 12, 31)]
    assert q4.fp == "Q4"
    assert q4.value == 2_740_000_000  # filer's stub, not FY−9M = 2_740_000_000
    assert all(m.fp != "FY" for m in metrics.values())
    assert len(metrics) == 4
