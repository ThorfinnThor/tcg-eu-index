from __future__ import annotations

from datetime import date, timedelta

import polars as pl
from indexengine.calc import calculate_daily_values
from indexengine.methodology import IndexDefinition, Methodology
from indexengine.selection import Constituent


def methodology() -> Methodology:
    return Methodology(
        methodology_version="test",
        price_field_primary="price_avg",
        price_field_fallback="price_low",
        min_price_eur={"singles": 2.0, "sealed": 10.0},
        seasoning_days=0,
        min_history_days=0,
        min_observation_ratio=0.0,
        daily_return_cap=0.25,
        carry_forward_max_days=1,
        rebalance="monthly",
        selection_lookback_days=5,
        indexes=[],
    )


def definition() -> IndexDefinition:
    return IndexDefinition(
        code="TEST",
        name="Test",
        game_key="onepiece",
        universe="singles",
        target_size=2,
        base_date="2026-07-20",
        base_value=1000,
        status="accumulating",
        language_scope=["EN"],
    )


def test_daily_calc_caps_and_carries_forward() -> None:
    start = date(2026, 7, 20)
    rows = []
    prices = {
        1: [10, 20, None, 25],
        2: [10, 9, 9, 9],
    }
    for product_id, series in prices.items():
        for offset, price in enumerate(series):
            rows.append(
                {
                    "value_date": start + timedelta(days=offset),
                    "cm_product_id": product_id,
                    "variant_key": "nonfoil",
                    "product_kind": "single",
                    "price_avg": price,
                    "price_low": price,
                }
            )
    constituents = [
        Constituent(1, "nonfoil", "added", "fixture", 1, 10),
        Constituent(2, "nonfoil", "added", "fixture", 1, 10),
    ]
    values, contributions = calculate_daily_values(
        pl.DataFrame(rows),
        definition(),
        methodology(),
        constituents,
    )
    assert values[0].index_value == 1000
    assert round(values[1].daily_return, 6) == 0.075
    assert values[1].n_capped == 1
    assert values[2].n_carried_forward == 1
    assert contributions
