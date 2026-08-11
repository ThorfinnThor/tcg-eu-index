from __future__ import annotations

import json
from datetime import date
from io import BytesIO
from pathlib import Path

import polars as pl
import pytest
from core.r2 import LocalObjectStore
from core.settings import Settings
from ingest.archive import run_archive
from ingest.cardmarket import catalogue_urls, combine_catalogues, priceguide_url
from ingest.normalize import (
    load_category_map,
    normalize_catalogue,
    normalize_prices,
    run_normalize,
    stable_product_id,
    stable_variant_id,
)


def payload(key: str, records: list[dict[str, object]]) -> bytes:
    return json.dumps(
        {"version": 1, "createdAt": "2026-08-09T02:49:05+0200", key: records}
    ).encode()


@pytest.mark.parametrize(
    ("game", "game_id"),
    [
        ("magic", 1),
        ("yugioh", 3),
        ("pokemon", 6),
        ("dragonballsuper", 13),
        ("fleshandblood", 16),
        ("digimon", 17),
        ("onepiece", 18),
        ("lorcana", 19),
        ("starwarsunlimited", 21),
        ("riftbound", 22),
    ],
)
def test_official_download_urls_use_verified_game_ids(game: str, game_id: int) -> None:
    assert priceguide_url(game).endswith(f"/priceGuide/price_guide_{game_id}.json")
    assert catalogue_urls(game)[0].endswith(
        f"/productList/products_singles_{game_id}.json"
    )
    assert catalogue_urls(game)[1].endswith(
        f"/productList/products_nonsingles_{game_id}.json"
    )


def test_combine_catalogues_preserves_both_product_groups() -> None:
    combined = combine_catalogues(
        [
            payload("products", [{"idProduct": 1}]),
            payload("products", [{"idProduct": 2}]),
        ]
    )
    assert [row["idProduct"] for row in json.loads(combined)["products"]] == [1, 2]


def test_normalize_official_catalogue_schema() -> None:
    raw = payload(
        "products",
        [
            {
                "idProduct": 690368,
                "name": "Roronoa Zoro (OP01-001)",
                "idCategory": 1621,
                "categoryName": "One Piece Single",
                "idExpansion": 5229,
                "idMetacard": 415369,
                "dateAdded": "2022-12-28 22:11:43",
            }
        ],
    )
    result = normalize_catalogue("onepiece", raw, date(2026, 8, 9), load_category_map())
    assert result.products[0]["product_kind"] == "single"
    assert result.products[0]["raw_category"] == "One Piece Single"
    assert result.products[0]["stable_product_id"] == "cardmarket:onepiece:product:690368"
    assert result.products[0]["cm_metacard_id"] == 415369
    assert result.sets[0]["cm_expansion_id"] == 5229
    assert result.variants == []
    assert result.unknown_categories == set()


def test_normalize_one_piece_foil_prices() -> None:
    raw = payload(
        "priceGuides",
        [
            {
                "idProduct": 690368,
                "avg": 2.48,
                "low": 0.5,
                "avg1": 2.5,
                "avg7": 2.85,
                "avg30": 2.77,
                "avg-foil": 9.5,
                "low-foil": 8.0,
                "avg1-foil": 9.1,
                "avg7-foil": 9.2,
                "avg30-foil": 9.3,
            }
        ],
    )
    rows = normalize_prices("onepiece", raw, date(2026, 8, 9)).to_dicts()
    assert rows[0]["variant_key"] == "nonfoil"
    assert rows[1]["stable_product_id"] == stable_product_id("onepiece", 690368)
    assert rows[1]["stable_variant_id"] == stable_variant_id("onepiece", 690368, "foil")
    assert rows[1]["variant_key"] == "foil"
    assert rows[1]["value_date"] == date(2026, 8, 9)
    assert rows[1]["price_low"] == 8.0
    assert rows[1]["price_avg"] == 9.5
    assert rows[1]["avg1"] == 9.1
    assert rows[1]["avg7"] == 9.2
    assert rows[1]["avg30"] == 9.3


def test_normalize_pokemon_holo_prices_to_internal_foil_variant() -> None:
    raw = payload(
        "priceGuides",
        [{"idProduct": 100, "avg": 3.2, "low": 2.0, "avg-holo": 5.4, "low-holo": 4.8}],
    )
    rows = normalize_prices("pokemon", raw, date(2026, 8, 9)).to_dicts()
    assert rows[1]["variant_key"] == "foil"
    assert rows[1]["price_avg"] == 5.4


def test_normalize_holo_only_product_does_not_create_empty_nonfoil_row() -> None:
    raw = payload(
        "priceGuides",
        [{"idProduct": 101, "idCategory": 1, "avg-holo": 8.2, "low-holo": 7.0}],
    )
    rows = normalize_prices("pokemon", raw, date(2026, 8, 9)).to_dicts()
    assert len(rows) == 1
    assert rows[0]["variant_key"] == "foil"
    assert rows[0]["price_avg"] == 8.2


def test_normalize_keeps_low_only_family_for_methodology_fallback() -> None:
    raw = payload(
        "priceGuides",
        [{"idProduct": 101, "idCategory": 1, "avg": None, "low": 7.0}],
    )
    rows = normalize_prices("onepiece", raw, date(2026, 8, 9)).to_dicts()
    assert len(rows) == 1
    assert rows[0]["variant_key"] == "nonfoil"
    assert rows[0]["price_avg"] is None
    assert rows[0]["price_low"] == 7.0


def test_normalize_accepts_mixed_integer_and_decimal_prices() -> None:
    records = [
        {"idProduct": product_id, "idCategory": 1, "avg": product_id, "low": product_id}
        for product_id in range(1, 102)
    ]
    records.append({"idProduct": 102, "idCategory": 1, "avg": 2.5, "low": 0.1})
    rows = normalize_prices(
        "onepiece", payload("priceGuides", records), date(2026, 8, 9)
    )
    assert rows.schema["price_avg"] == pl.Float64
    assert rows.filter(pl.col("cm_product_id") == 102)["price_low"][0] == 0.1


class PipelineFetcher:
    def fetch(self, url: str) -> tuple[bytes, dict[str, str]]:
        if "price" in url:
            records = [
                {
                    "idProduct": product_id,
                    "idCategory": 1621,
                    "avg": float(product_id),
                    "low": float(product_id) - 0.5,
                    "avg1": float(product_id),
                    "avg7": float(product_id),
                    "avg30": float(product_id),
                    "avg-foil": 12.0 if product_id == 1 else None,
                    "low-foil": 11.0 if product_id == 1 else None,
                }
                for product_id in range(1, 1_001)
            ]
            return payload("priceGuides", records), {}
        records = [
            {
                "idProduct": product_id,
                "name": f"Card {product_id}",
                "idCategory": 1621,
                "categoryName": "One Piece Single",
                "idExpansion": 5229,
                "idMetacard": 10_000 + product_id,
                "dateAdded": "2022-12-28 22:11:43",
            }
            for product_id in range(1, 1_001)
        ]
        return payload("products", records), {}


def pipeline_settings() -> Settings:
    return Settings(
        cm_games=["onepiece"],
        cm_priceguide_url_template="https://example.test/{game}/price",
        cm_catalogue_url_template="https://example.test/{game}/catalogue",
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


def test_production_normalization_outputs_are_complete_and_idempotent(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    run_date = date(2026, 8, 9)
    run_archive(
        run_date,
        pipeline_settings(),
        store=store,
        fetcher=PipelineFetcher(),
        data_dir=tmp_path / "data",
    )

    first = run_normalize(run_date, pipeline_settings(), store=store)
    first_bytes = {key: store.read_bytes(key) for key in store.list_keys("derived")}
    second = run_normalize(run_date, pipeline_settings(), store=store)
    second_bytes = {key: store.read_bytes(key) for key in store.list_keys("derived")}

    assert first[0].catalogue_products == 1_000
    assert first[0].catalogue_variants == 1_001
    assert first[0].price_rows == 1_001
    assert first[0].classification_coverage == 1.0
    assert first[0].changed_outputs
    assert second[0].changed_outputs == []
    assert first_bytes == second_bytes

    products = pl.read_parquet(
        BytesIO(store.read_bytes("derived/catalogue/onepiece/products.parquet"))
    )
    variants = pl.read_parquet(
        BytesIO(store.read_bytes("derived/catalogue/onepiece/variants.parquet"))
    )
    prices = pl.read_parquet(BytesIO(store.read_bytes("derived/prices/onepiece/2026-08.parquet")))
    assert products.height == 1_000
    assert variants.height == 1_001
    assert prices.height == 1_001
    foil = prices.filter(
        (pl.col("cm_product_id") == 1) & (pl.col("variant_key") == "foil")
    ).to_dicts()[0]
    assert foil["product_kind"] == "single"
    assert foil["stable_variant_id"] == "cardmarket:onepiece:product:1:foil"

    run_note = json.loads(
        store.read_bytes("derived/ingest_runs/2026-08-09-onepiece.json")
    )
    assert run_note["status"] == "ok"
    assert run_note["classification_coverage"] == 1.0


def test_category_quality_gate_does_not_publish_completion_markers(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    run_date = date(2026, 8, 9)
    category_map = tmp_path / "category-map.yaml"
    category_map.write_text("single:\n  - A category that is not present\n")
    run_archive(
        run_date,
        pipeline_settings(),
        store=store,
        fetcher=PipelineFetcher(),
        data_dir=tmp_path / "data",
    )

    with pytest.raises(RuntimeError, match="below 99%"):
        run_normalize(
            run_date,
            pipeline_settings(),
            store=store,
            category_map_path=category_map,
        )

    quality_key = "derived/quality/category-coverage/2026-08-09-onepiece.json"
    quality = json.loads(store.read_bytes(quality_key))
    assert quality["status"] == "fail"
    assert quality["classification_coverage"] == 0.0
    assert not store.exists("derived/catalogue/onepiece/manifest.json")
    assert not store.exists("derived/ingest_runs/2026-08-09-onepiece.json")
