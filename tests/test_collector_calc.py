from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest
from indexengine.collector_calc import (
    CollectorMember,
    CollectorRebalance,
    build_monthly_collector_rebalances,
    calculate_collector_chain_linked,
    collector_rebalance_from_eligibility,
)
from indexengine.eligibility import CollectorEligibilityResult, CollectorVariantDiagnostic
from indexengine.methodology import Methodology, MethodologyConfigError

METHODOLOGY_PATH = Path("packages/indexengine/methodologies/v1.5.0-preview.1.yaml")


def methodology() -> Methodology:
    return Methodology.load(METHODOLOGY_PATH)


def member(product_id: int, selection_price: float, variant: str = "nonfoil") -> CollectorMember:
    return CollectorMember(
        cm_product_id=product_id,
        variant_key=variant,
        stable_variant_id=f"cardmarket:onepiece:product:{product_id}:{variant}",
        selection_price=selection_price,
    )


def rebalance(
    effective_date: date,
    selection_as_of: date,
    constituents: tuple[CollectorMember, ...],
    marker: str,
) -> CollectorRebalance:
    return CollectorRebalance(
        effective_date=effective_date,
        selection_as_of=selection_as_of,
        methodology_version="1.5.0-preview.1",
        selection_snapshot_sha256=marker * 64,
        eligible_count=len(constituents),
        constituents=constituents,
    )


def price_row(value_date: date, product_id: int, avg30: float | None) -> dict[str, object]:
    return {
        "value_date": value_date,
        "game_key": "onepiece",
        "product_kind": "single",
        "cm_product_id": product_id,
        "variant_key": "nonfoil",
        "avg30": avg30,
        "price_avg": 9999.0,
        "price_low": 9998.0,
    }


def diagnostic(
    product_id: int, variant: str, reference_price: float
) -> CollectorVariantDiagnostic:
    return CollectorVariantDiagnostic(
        cm_product_id=product_id,
        variant_key=variant,
        stable_variant_id=f"cardmarket:onepiece:product:{product_id}:{variant}",
        eligible=True,
        exclusion_reasons=(),
        reference_price=reference_price,
        history_days=60,
        valuation_observation_ratio=1.0,
        selection_price_observation_ratio=1.0,
        suspect_zero_ratio=0.0,
        price_update_frequency=1.0,
        inverse_dispersion=1.0,
        data_quality_score=1.0,
        activity_days=0,
        activity_ratio=0.0,
        observable_activity_days=0,
        last_positive_avg1_date=None,
        days_since_positive_avg1=None,
        repeated_positive_avg1_days=0,
    )


def test_golden_collector_calculation_drifts_caps_carries_suspends_and_rebalances() -> None:
    jan31 = date(2026, 1, 31)
    feb1 = date(2026, 2, 1)
    feb2 = date(2026, 2, 2)
    feb3 = date(2026, 2, 3)
    feb4 = date(2026, 2, 4)
    feb10 = date(2026, 2, 10)
    feb11 = date(2026, 2, 11)
    feb28 = date(2026, 2, 28)
    mar1 = date(2026, 3, 1)
    calendar = [jan31, feb1, feb2, feb3, feb4, feb10, feb11, feb28, mar1]
    rows = [
        price_row(feb1, 1, 10.0),
        price_row(feb1, 2, 10.0),
        price_row(feb2, 1, 12.0),
        price_row(feb2, 2, 10.0),
        price_row(feb3, 1, 12.0),
        price_row(feb3, 2, 12.0),
        price_row(feb4, 1, 24.0),
        price_row(feb4, 2, None),
        price_row(feb10, 1, 24.0),
        price_row(feb10, 2, None),
        price_row(feb11, 1, 24.0),
        price_row(feb11, 2, 6.0),
        price_row(feb28, 1, None),
        price_row(feb28, 2, 6.0),
        price_row(mar1, 2, 6.0),
        price_row(mar1, 3, 20.0),
    ]
    first = rebalance(feb1, jan31, (member(1, 10.0), member(2, 10.0)), "a")
    second = rebalance(mar1, feb28, (member(2, 6.0), member(3, 10.0)), "b")
    config = methodology()
    definition = config.index_by_code("OPEUCOL")

    values, contributions = calculate_collector_chain_linked(
        pl.DataFrame(rows),
        definition,
        config,
        [first, second],
        calendar,
    )

    assert [item.value_date for item in values] == calendar[1:]
    assert [item.index_value for item in values] == pytest.approx(
        [1000.0, 1100.0, 1200.0, 1350.0, 1350.0, 1200.0, 1200.0, 1350.0]
    )
    by_day = {item.value_date: item for item in values}
    feb2_rows = [item for item in contributions if item.value_date == feb2]
    assert [item.weight_before for item in feb2_rows] == pytest.approx([0.5, 0.5])
    assert [item.weight_after for item in feb2_rows] == pytest.approx([6 / 11, 5 / 11])
    feb3_rows = [item for item in contributions if item.value_date == feb3]
    assert [item.weight_before for item in feb3_rows] == pytest.approx([6 / 11, 5 / 11])
    assert [item.weight_after for item in feb3_rows] == pytest.approx([0.5, 0.5])

    assert by_day[feb4].capped_count == 1
    assert by_day[feb4].capped_weight_share == pytest.approx(0.5)
    assert by_day[feb4].carried_count == 1
    assert by_day[feb4].carried_weight_share == pytest.approx(0.5)
    assert by_day[feb10].suspended_count == 1
    assert by_day[feb10].suspended_weight_share == pytest.approx(4 / 9)
    suspended = next(
        item for item in contributions if item.value_date == feb10 and item.cm_product_id == 2
    )
    assert suspended.price_state == "suspended_stale"
    assert suspended.used_return == 0
    assert suspended.weight_before == pytest.approx(4 / 9)
    assert suspended.weight_after == pytest.approx(4 / 9)

    resumed = next(
        item for item in contributions if item.value_date == feb11 and item.cm_product_id == 2
    )
    assert resumed.raw_return == pytest.approx(-0.5)
    assert resumed.used_return == pytest.approx(-0.25)
    assert resumed.capped
    assert by_day[feb11].daily_return == pytest.approx(-1 / 9)
    assert len([item for item in contributions if item.value_date == feb10]) == 2

    march_rows = [item for item in contributions if item.value_date == mar1]
    assert [(item.cm_product_id, item.target_weight) for item in march_rows] == [
        (2, 0.5),
        (3, 0.5),
    ]
    assert [item.weight_after for item in march_rows] == pytest.approx([4 / 9, 5 / 9])
    assert by_day[mar1].rebalance_effective_date == mar1
    assert by_day[mar1].selection_as_of == feb28


def test_collector_calculation_uses_avg30_only_and_keeps_both_variants() -> None:
    jan31 = date(2026, 1, 31)
    feb1 = date(2026, 2, 1)
    feb2 = date(2026, 2, 2)
    config = methodology()
    definition = config.index_by_code("OPEUCOL")
    foil = member(1, 20.0, "foil")
    nonfoil = member(1, 10.0, "nonfoil")
    basket = rebalance(feb1, jan31, (foil, nonfoil), "c")
    prices = pl.DataFrame(
        [
            {
                **price_row(value_date, 1, avg30),
                "variant_key": variant,
            }
            for value_date, variant, avg30 in (
                (feb1, "foil", 20.0),
                (feb1, "nonfoil", 10.0),
                (feb2, "foil", None),
                (feb2, "nonfoil", 11.0),
            )
        ]
    )

    values, contributions = calculate_collector_chain_linked(
        prices,
        definition,
        config,
        [basket],
        [jan31, feb1, feb2],
    )

    assert values[-1].daily_return == pytest.approx(0.05)
    feb2_rows = [item for item in contributions if item.value_date == feb2]
    assert {(item.cm_product_id, item.variant_key) for item in feb2_rows} == {
        (1, "foil"),
        (1, "nonfoil"),
    }
    foil_row = next(item for item in feb2_rows if item.variant_key == "foil")
    assert foil_row.price_state == "carried_forward"
    assert foil_row.used_return == 0
    assert foil_row.valuation_price == 20.0


def test_collector_calculation_reports_an_empty_universe_without_an_index_value() -> None:
    jan31 = date(2026, 1, 31)
    feb1 = date(2026, 2, 1)
    config = methodology()
    definition = config.index_by_code("OPEUCOL")
    empty = rebalance(feb1, jan31, (), "d")
    prices = pl.DataFrame(
        schema={
            "value_date": pl.Date,
            "cm_product_id": pl.Int64,
            "variant_key": pl.String,
            "avg30": pl.Float64,
        }
    )

    values, contributions = calculate_collector_chain_linked(
        prices,
        definition,
        config,
        [empty],
        [jan31, feb1],
    )

    assert len(values) == 1
    assert values[0].status == "empty_eligible_universe"
    assert values[0].index_value is None
    assert values[0].daily_return is None
    assert contributions == []


def test_whole_market_unchanged_snapshot_is_zero_return_and_does_not_reset_prices() -> None:
    jan31 = date(2026, 1, 31)
    feb1 = date(2026, 2, 1)
    feb2 = date(2026, 2, 2)
    feb3 = date(2026, 2, 3)
    config = methodology()
    definition = config.index_by_code("OPEUCOL")
    basket = rebalance(feb1, jan31, (member(1, 10.0), member(2, 10.0)), "g")
    prices = pl.DataFrame(
        [
            price_row(feb1, 1, 10.0),
            price_row(feb1, 2, 10.0),
            price_row(feb2, 1, 20.0),
            price_row(feb2, 2, 5.0),
            price_row(feb3, 1, 20.0),
            price_row(feb3, 2, 5.0),
        ]
    )

    values, contributions = calculate_collector_chain_linked(
        prices,
        definition,
        config,
        [basket],
        [jan31, feb1, feb2, feb3],
        unchanged_dates={feb2},
    )

    by_day = {item.value_date: item for item in values}
    assert by_day[feb2].daily_return == 0
    assert by_day[feb2].whole_market_carried_forward
    assert by_day[feb2].carried_weight_share == pytest.approx(1.0)
    assert {
        item.price_state for item in contributions if item.value_date == feb2
    } == {"snapshot_unchanged"}
    assert by_day[feb3].daily_return == pytest.approx(0.0)
    assert by_day[feb3].capped_count == 2
    feb3_rows = [item for item in contributions if item.value_date == feb3]
    assert [item.raw_return for item in feb3_rows] == pytest.approx([1.0, -0.5])
    assert [item.used_return for item in feb3_rows] == pytest.approx([0.25, -0.25])


def test_eligibility_result_freezes_selection_prices_and_variant_identities() -> None:
    effective_date = date(2026, 2, 1)
    foil = diagnostic(1, "foil", 25.0)
    nonfoil = diagnostic(1, "nonfoil", 10.0)
    result = CollectorEligibilityResult(
        index_code="OPEUCOL",
        methodology_version="1.5.0-preview.1",
        effective_date=effective_date,
        data_state="shadow",
        required_history_days=7,
        quality_calendar_days=7,
        activity_observable_days=6,
        excluded_unchanged_days=1,
        diagnostics=(nonfoil, foil),
        eligible_variants=(nonfoil, foil),
        snapshot_sha256="h" * 64,
    )

    frozen = collector_rebalance_from_eligibility(
        result,
        selection_as_of=date(2026, 1, 31),
    )

    assert frozen.selection_snapshot_sha256 == "h" * 64
    assert [(item.variant_key, item.selection_price) for item in frozen.constituents] == [
        ("foil", 25.0),
        ("nonfoil", 10.0),
    ]
    assert frozen.eligible_count == 2


def test_shadow_scheduler_starts_after_seven_days_then_uses_monthly_first_day() -> None:
    january = [date(2026, 1, 1) + timedelta(days=offset) for offset in range(9)]
    feb2 = date(2026, 2, 2)
    calendar = [*january, feb2]
    config = methodology()
    definition = config.index_by_code("OPEUCOL")
    prices = pl.DataFrame(
        [
            {
                **price_row(value_date, 1, 9.0 if value_date < january[-2] else 12.0),
                "avg1": 12.0,
                "stable_variant_id": "cardmarket:onepiece:product:1:nonfoil",
            }
            for value_date in calendar
        ]
    )
    products = pl.DataFrame(
        [
            {
                "cm_product_id": 1,
                "source_date_added": "2020-01-01 00:00:00",
                "first_seen": "2026-01-01",
            }
        ]
    )

    rebalances = build_monthly_collector_rebalances(
        prices,
        products,
        definition,
        config,
        calendar,
        data_state="shadow",
    )

    assert [item.effective_date for item in rebalances] == [january[-1], feb2]
    assert [item.selection_as_of for item in rebalances] == [january[-2], january[-1]]
    assert [item.eligible_count for item in rebalances] == [1, 1]


def test_collector_rebalance_calendar_and_schema_contract_are_enforced() -> None:
    jan31 = date(2026, 1, 31)
    feb1 = date(2026, 2, 1)
    feb2 = date(2026, 2, 2)
    mar1 = date(2026, 3, 1)
    config = methodology()
    definition = config.index_by_code("OPEUCOL")
    first = rebalance(feb1, jan31, (member(1, 10.0),), "e")
    late_second = rebalance(date(2026, 3, 2), mar1, (member(1, 10.0),), "f")
    prices = pl.DataFrame([price_row(feb1, 1, 10.0), price_row(feb2, 1, 10.0)])

    with pytest.raises(ValueError, match="first observable source day"):
        calculate_collector_chain_linked(
            prices,
            definition,
            config,
            [first, late_second],
            [jan31, feb1, feb2, mar1, date(2026, 3, 2)],
        )

    invalid_calculation = replace(config.calculation, price_fallback="price_low")
    invalid_config = replace(config, calculation=invalid_calculation)
    with pytest.raises(MethodologyConfigError, match="unsupported collector calculation contract"):
        calculate_collector_chain_linked(
            prices,
            definition,
            invalid_config,
            [first],
            [jan31, feb1, feb2],
        )
