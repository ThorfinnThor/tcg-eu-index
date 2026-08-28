from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest
from core.r2 import LocalObjectStore
from core.settings import Settings
from indexengine.analytics import calculate_analytics
from indexengine.calc import Rebalance, _archive_calendar, calculate_chain_linked, run_calc
from indexengine.methodology import IndexDefinition, Methodology
from indexengine.public_export import build_public_membership_contract
from indexengine.selection import Constituent, RemovedConstituent, select_constituents
from ingest.manifest import Manifest, ManifestFile


def methodology(**overrides: object) -> Methodology:
    value = Methodology(
        methodology_version="test",
        price_field_primary="price_avg",
        price_field_fallback="price_low",
        min_price_eur={"singles": 2.0, "sealed": 10.0},
        seasoning_days=0,
        min_history_days=0,
        min_observation_ratio=0.0,
        price_floor_observation_ratio=0.0,
        max_suspect_zero_ratio=0.05,
        daily_return_cap=0.25,
        carry_forward_max_days=1,
        rebalance="monthly",
        selection_lookback_days=5,
        selection_rank="reference_price_descending",
        ranking_price_field="avg30",
        indexes=[],
    )
    return replace(value, **overrides)


def definition(target_size: int = 5) -> IndexDefinition:
    return IndexDefinition(
        code="TEST",
        name="Test",
        game_key="onepiece",
        universe="singles",
        target_size=target_size,
        base_date="2026-07-20",
        base_value=1000,
        status="accumulating",
        language_scope=["EN"],
    )


def constituent(product_id: int) -> Constituent:
    return Constituent(
        product_id,
        "nonfoil",
        "added",
        "golden fixture",
        1.0,
        10.0,
        f"cardmarket:onepiece:product:{product_id}:nonfoil",
    )


def test_selection_uses_complete_calendar_window_and_price_floor() -> None:
    start = date(2026, 7, 20)
    rows = []
    series = {
        1: [10.0, 11.0, 12.0, 13.0],
        2: [9.0, 9.0, 9.0, 9.0],
        3: [1.0, 1.0, 1.0, 1.0],
    }
    for product_id, prices in series.items():
        for offset, price in enumerate(prices):
            rows.append(
                {
                    "value_date": start + timedelta(days=offset),
                    "stable_variant_id": (
                        f"cardmarket:onepiece:product:{product_id}:nonfoil"
                    ),
                    "cm_product_id": product_id,
                    "variant_key": "nonfoil",
                    "product_kind": "single",
                    "price_avg": price,
                    "price_low": price - 0.5,
                    "avg30": price,
                }
            )
    products = pl.DataFrame(
        [
            {
                "cm_product_id": product_id,
                "source_date_added": "2020-01-01 00:00:00",
                "first_seen": "2026-07-20",
            }
            for product_id in series
        ]
    )
    config = methodology(
        selection_lookback_days=4,
        min_history_days=4,
        min_observation_ratio=1.0,
        price_floor_observation_ratio=1.0,
    )

    result = select_constituents(
        pl.DataFrame(rows),
        products,
        definition(target_size=2),
        config,
        start + timedelta(days=4),
    )

    assert [item.cm_product_id for item in result.constituents] == [1, 2]
    assert result.eligible_count == 2
    assert len(result.snapshot_sha256) == 64

    buffered = select_constituents(
        pl.DataFrame(rows),
        products,
        definition(target_size=2),
        config,
        start + timedelta(days=4),
        incumbents={(1, "nonfoil"), (3, "nonfoil")},
    )
    assert [item.cm_product_id for item in buffered.constituents] == [1, 2]
    assert buffered.removed[0].cm_product_id == 3
    assert "eligibility gates" in buffered.removed[0].reason


def test_selection_ranks_by_reference_price_and_keeps_one_variant_per_product() -> None:
    effective_date = date(2026, 8, 2)
    prices = pl.DataFrame(
        [
            {
                "value_date": date(2026, 8, 1),
                "stable_variant_id": stable_id,
                "cm_product_id": product_id,
                "variant_key": variant,
                "product_kind": "single",
                "price_avg": ref_price,
                "price_low": ref_price,
                "avg30": ref_price,
            }
            for product_id, variant, ref_price, stable_id in (
                (1, "nonfoil", 20.0, "cardmarket:onepiece:product:1:nonfoil"),
                (1, "foil", 80.0, "cardmarket:onepiece:product:1:foil"),
                (2, "nonfoil", 50.0, "cardmarket:onepiece:product:2:nonfoil"),
                (3, "nonfoil", 10.0, "cardmarket:onepiece:product:3:nonfoil"),
            )
        ]
    )
    products = pl.DataFrame(
        [
            {
                "cm_product_id": product_id,
                "source_date_added": "2020-01-01 00:00:00",
                "first_seen": "2026-08-01",
            }
            for product_id in (1, 2, 3)
        ]
    )

    result = select_constituents(
        prices,
        products,
        definition(target_size=2),
        methodology(selection_lookback_days=1),
        effective_date,
    )

    assert [(item.cm_product_id, item.variant_key) for item in result.constituents] == [
        (1, "foil"),
        (2, "nonfoil"),
    ]
    assert [item.ref_price for item in result.constituents] == [80.0, 50.0]
    assert result.eligible_count == 3
    assert "reference-price rank 1" in result.constituents[0].reason


def test_golden_chain_linked_index_covers_caps_carry_suspension_and_rebalance() -> None:
    start = date(2026, 7, 20)
    series: dict[int, list[float | None]] = {
        1: [10, 20, 20, 20, 20, 20, 15, 15, 15, 15],
        2: [10, 10, None, None, 10, 10, 10, 10, 10, 10],
        3: [10] * 10,
        4: [10] * 10,
        5: [10] * 10,
        6: [10] * 10,
    }
    rows = []
    for product_id, prices in series.items():
        for offset, price in enumerate(prices):
            rows.append(
                {
                    "value_date": start + timedelta(days=offset),
                    "stable_variant_id": (
                        f"cardmarket:onepiece:product:{product_id}:nonfoil"
                    ),
                    "cm_product_id": product_id,
                    "variant_key": "nonfoil",
                    "product_kind": "single",
                    "price_avg": price,
                    "price_low": price,
                }
            )
    first = Rebalance(
        start.isoformat(),
        "test",
        "first",
        5,
        [constituent(product_id) for product_id in range(1, 6)],
        [],
    )
    second = Rebalance(
        (start + timedelta(days=5)).isoformat(),
        "test",
        "second",
        5,
        [constituent(product_id) for product_id in (1, 2, 3, 4, 6)],
        [
            RemovedConstituent(
                5,
                "nonfoil",
                "removed",
                "golden fixture rebalance removal",
                "cardmarket:onepiece:product:5:nonfoil",
            )
        ],
    )

    values, contributions = calculate_chain_linked(
        pl.DataFrame(rows),
        definition(),
        methodology(),
        [first, second],
        [start + timedelta(days=offset) for offset in range(10)],
    )

    expected = [1000.0, 1050.0, 1050.0, 1050.0, 1050.0, 1050.0, 997.5, 997.5, 997.5, 997.5]
    assert [item.index_value for item in values] == pytest.approx(expected, abs=1e-9)
    assert values[1].n_capped == 1
    assert values[2].n_carried_forward == 1
    assert values[3].n_stale == 1
    assert values[5].index_value == values[4].index_value
    assert not any(
        item.cm_product_id == 5 and item.value_date >= second.effective_date
        for item in contributions
    )
    assert any(
        item.cm_product_id == 6 and item.value_date == second.effective_date
        for item in contributions
    )

    products = pl.DataFrame(
        [{"cm_product_id": product_id, "name": f"Card {product_id}"} for product_id in series]
    )
    analytics = calculate_analytics(values, contributions, products)
    day_two = analytics[1]
    one_day = next(item for item in day_two.windows if item.window == "1d")
    assert day_two.breadth_7d == pytest.approx(0.2)
    assert one_day.top_movers[0].cm_product_id == 1
    assert one_day.top_movers[0].value == pytest.approx(0.25)
    assert one_day.contribution_leaders[0].value == pytest.approx(0.05)
    assert analytics[6].drawdown == pytest.approx(-0.05)
    assert analytics[6].volatility_30d is not None
    assert analytics[6].volatility_observations == 7


def test_analytics_excludes_whole_market_unchanged_day_from_rankings() -> None:
    start = date(2026, 7, 20)
    rows = [
        {
            "value_date": start + timedelta(days=offset),
            "stable_variant_id": "cardmarket:onepiece:product:1:nonfoil",
            "cm_product_id": 1,
            "variant_key": "nonfoil",
            "product_kind": "single",
            "price_avg": price,
            "price_low": price,
        }
        for offset, price in enumerate((10.0, 20.0))
    ]
    rebalance = Rebalance(
        start.isoformat(),
        "test",
        "unchanged",
        1,
        [constituent(1)],
        [],
    )
    values, contributions = calculate_chain_linked(
        pl.DataFrame(rows),
        definition(target_size=1),
        methodology(),
        [rebalance],
        [start, start + timedelta(days=1)],
        {start + timedelta(days=1)},
    )

    analytics = calculate_analytics(
        values,
        contributions,
        pl.DataFrame([{"cm_product_id": 1, "name": "Card 1"}]),
    )
    latest = analytics[-1]
    one_day = next(item for item in latest.windows if item.window == "1d")
    assert latest.whole_market_carried_forward
    assert latest.daily_return == 0
    assert one_day.observation_dates == 0
    assert one_day.excluded_whole_market_dates == 1
    assert one_day.top_movers == []
    assert one_day.contribution_leaders == []


def settings() -> Settings:
    return Settings(
        cm_games=["onepiece", "pokemon"],
        cm_priceguide_url_template="",
        cm_catalogue_url_template="",
        cm_user_agent="tests",
        r2_account_id="",
        r2_access_key_id="",
        r2_secret_access_key="",
        r2_bucket="tcg-raw",
        supabase_db_url="",
        supabase_url="",
        supabase_anon_key="",
        alert_discord_webhook=None,
    )


def test_archive_calendar_counts_only_days_containing_the_game(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    first_day = date(2026, 8, 10)
    second_day = first_day + timedelta(days=1)

    def price_file(game: str, value_date: date, unchanged: bool = False) -> ManifestFile:
        return ManifestFile(
            game=game,
            kind="priceguide",
            key=f"cardmarket/priceguide/{game}/{value_date.isoformat()}.json.gz",
            sha256_uncompressed="0" * 64,
            size_uncompressed=1,
            fetched_at=f"{value_date.isoformat()}T00:00:00+00:00",
            headers={},
            unchanged_from_previous=unchanged,
        )

    store.write_bytes(
        f"manifests/{first_day.isoformat()}.json",
        Manifest(first_day.isoformat(), [price_file("onepiece", first_day)]).to_json_bytes(),
        "application/json",
    )
    store.write_bytes(
        f"manifests/{second_day.isoformat()}.json",
        Manifest(
            second_day.isoformat(),
            [price_file("onepiece", second_day), price_file("pokemon", second_day, True)],
        ).to_json_bytes(),
        "application/json",
    )
    prices = pl.DataFrame({"value_date": [second_day]})

    dates, unchanged = _archive_calendar(store, "pokemon", second_day, prices)

    assert dates == [second_day]
    assert unchanged == {second_day}


def test_shadow_run_is_private_accumulating_and_idempotent(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    run_date = date(2026, 8, 10)
    for game in ("onepiece", "pokemon"):
        prices = pl.DataFrame(
            [
                {
                    "stable_variant_id": f"cardmarket:{game}:product:1:nonfoil",
                    "stable_product_id": f"cardmarket:{game}:product:1",
                    "game_key": game,
                    "cm_product_id": 1,
                    "cm_category_id": 1,
                    "product_kind": "single",
                    "value_date": run_date,
                    "variant_key": "nonfoil",
                    "price_low": 9.0,
                    "price_avg": 10.0,
                    "avg1": 10.0,
                    "avg7": 10.0,
                    "avg30": 10.0,
                }
            ]
        )
        price_buffer = Path(tmp_path / f"{game}-prices.parquet")
        prices.write_parquet(price_buffer)
        store.write_bytes(
            f"derived/prices/{game}/2026-08.parquet",
            price_buffer.read_bytes(),
            "application/vnd.apache.parquet",
        )
        products = pl.DataFrame(
            [
                {
                    "cm_product_id": 1,
                    "source_date_added": "2020-01-01 00:00:00",
                    "first_seen": run_date.isoformat(),
                }
            ]
        )
        product_buffer = Path(tmp_path / f"{game}-products.parquet")
        products.write_parquet(product_buffer)
        store.write_bytes(
            f"derived/catalogue/{game}/products.parquet",
            product_buffer.read_bytes(),
            "application/vnd.apache.parquet",
        )

    first = run_calc(run_date, settings(), store=store)
    first_bytes = {key: store.read_bytes(key) for key in store.list_keys("derived/indexes")}
    second = run_calc(run_date, settings(), store=store)
    second_bytes = {key: store.read_bytes(key) for key in store.list_keys("derived/indexes")}

    assert {item.status for item in first} == {"accumulating"}
    assert {item.available_days for item in first} == {1}
    assert all(item.changed_outputs for item in first)
    assert all(item.changed_outputs == [] for item in second)
    assert first_bytes == second_bytes
    assert all(item.analytics_days == 0 for item in first)
    assert all(
        store.exists(f"derived/indexes/{code}/analytics.json")
        for code in ("OPEU500", "OPEUSLD", "PKEU500", "PKEUSLD")
    )
    assert store.list_keys("derived/public") == []


def test_public_membership_contract_preserves_removal_and_reentry_history() -> None:
    first = Rebalance(
        "2026-08-01",
        "1.0.0",
        "first",
        2,
        [constituent(1), constituent(2)],
        [],
    )
    second = Rebalance(
        "2026-09-01",
        "1.0.0",
        "second",
        2,
        [
            replace(constituent(1), action="retained", reason="incumbent retained"),
            constituent(3),
        ],
        [
            RemovedConstituent(
                2,
                "nonfoil",
                "removed",
                "outside top price rank",
                "cardmarket:onepiece:product:2:nonfoil",
            )
        ],
    )
    third = Rebalance(
        "2026-10-01",
        "1.0.0",
        "third",
        2,
        [
            replace(constituent(1), action="retained", reason="incumbent retained"),
            constituent(2),
        ],
        [
            RemovedConstituent(
                3,
                "nonfoil",
                "removed",
                "failed eligibility gates",
                "cardmarket:onepiece:product:3:nonfoil",
            )
        ],
    )
    products = pl.DataFrame(
        [
            {"cm_product_id": product_id, "name": f"Card {product_id}", "cm_expansion_id": 10}
            for product_id in (1, 2, 3)
        ]
    )
    sets = pl.DataFrame([{"cm_expansion_id": 10, "name": "Test Set"}])

    contract = build_public_membership_contract(
        "OPEU100",
        "2026-10-01",
        [first, second, third],
        products,
        sets,
        data_state="published",
    )

    intervals = [
        item for item in contract["constituents"] if item["cm_product_id"] == 2
    ]
    assert len(intervals) == 2
    assert intervals[0]["removed_at"] == "2026-09-01"
    assert intervals[1]["member_since"] == "2026-10-01"
    rebalance_history = contract["rebalances"]
    assert rebalance_history["data_state"] == "published"
    assert rebalance_history["rebalances"][1]["changes"] == [
        {
            "cm_product_id": 3,
            "variant_key": "nonfoil",
            "action": "added",
            "reason": "golden fixture",
        },
        {
            "cm_product_id": 2,
            "variant_key": "nonfoil",
            "action": "removed",
            "reason": "outside top price rank",
        },
    ]
