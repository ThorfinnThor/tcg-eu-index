from __future__ import annotations

import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import polars as pl
from core.r2 import LocalObjectStore
from core.settings import Settings
from indexengine.calc import run_calc
from indexengine.preview_export import export_preview_dataset
from ingest.manifest import Manifest, ManifestFile


def _write_parquet(store: LocalObjectStore, key: str, frame: pl.DataFrame, path: Path) -> None:
    frame.write_parquet(path)
    store.write_bytes(key, path.read_bytes(), "application/vnd.apache.parquet")


def _preview_store(tmp_path: Path) -> tuple[LocalObjectStore, date]:
    store = LocalObjectStore(tmp_path / "r2")
    first_day = date(2026, 8, 10)
    run_date = first_day + timedelta(days=3)
    rows = []
    for offset in range(4):
        value_date = first_day + timedelta(days=offset)
        for product_id in (1, 2, 3):
            price = 10.0 + product_id + offset
            rows.append(
                {
                    "stable_variant_id": f"cardmarket:onepiece:product:{product_id}:nonfoil",
                    "stable_product_id": f"cardmarket:onepiece:product:{product_id}",
                    "game_key": "onepiece",
                    "cm_product_id": product_id,
                    "cm_category_id": 1,
                    "product_kind": "single",
                    "value_date": value_date,
                    "variant_key": "nonfoil",
                    "price_low": price - 0.5,
                    "price_avg": price,
                    "avg1": price,
                    "avg7": price,
                    "avg30": price,
                }
            )
        manifest_file = ManifestFile(
            game="onepiece",
            kind="priceguide",
            key=f"cardmarket/priceguide/onepiece/{value_date.isoformat()}.json.gz",
            sha256_uncompressed=str(offset) * 64,
            size_uncompressed=1,
            fetched_at=f"{value_date.isoformat()}T00:00:00+00:00",
            headers={},
            unchanged_from_previous=False,
        )
        store.write_bytes(
            f"manifests/{value_date.isoformat()}.json",
            Manifest(value_date.isoformat(), [manifest_file]).to_json_bytes(),
            "application/json",
        )
    _write_parquet(
        store,
        "derived/prices/onepiece/2026-08.parquet",
        pl.DataFrame(rows),
        tmp_path / "prices.parquet",
    )
    products = pl.DataFrame(
        [
            {
                "cm_product_id": product_id,
                "name": f"Real Card {product_id}",
                "cm_expansion_id": 10,
                "source_date_added": "2020-01-01 00:00:00",
                "first_seen": first_day,
            }
            for product_id in (1, 2, 3)
        ]
    )
    _write_parquet(
        store,
        "derived/catalogue/onepiece/products.parquet",
        products,
        tmp_path / "products.parquet",
    )
    _write_parquet(
        store,
        "derived/catalogue/onepiece/sets.parquet",
        pl.DataFrame([{"cm_expansion_id": 10, "name": "Real Set"}]),
        tmp_path / "sets.parquet",
    )
    return store, run_date


def _settings() -> Settings:
    return Settings(
        cm_games=["onepiece"],
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


def test_preview_calculation_does_not_weaken_official_gates(tmp_path: Path) -> None:
    store, run_date = _preview_store(tmp_path)

    results = run_calc(run_date, _settings(), store=store)

    one_piece = next(item for item in results if item.index_code == "OPEU500")
    assert one_piece.status == "accumulating"
    assert one_piece.selected_constituents == 0
    preview_quality = json.loads(
        store.read_bytes(
            f"derived/preview/indexes/OPEU500/quality/{run_date.isoformat()}.json"
        )
    )
    assert preview_quality["status"] == "preview"
    assert preview_quality["selected_constituents"] == 3
    assert preview_quality["days_remaining_before_official_review"] == 56
    assert store.exists("derived/preview/indexes/OPEU500/daily-values.parquet")
    official_values = pl.read_parquet(
        store.root / "derived/indexes/OPEU500/daily-values.parquet"
    )
    preview_values = pl.read_parquet(
        store.root / "derived/preview/indexes/OPEU500/daily-values.parquet"
    )
    assert official_values.is_empty()
    assert preview_values.height == 3
    assert preview_values["index_value"][0] == 1000


def test_preview_export_publishes_only_verified_derived_data(tmp_path: Path) -> None:
    store, run_date = _preview_store(tmp_path)
    run_calc(run_date, _settings(), store=store)
    output_root = tmp_path / "source-data"
    output_root.mkdir()
    shutil.copy("apps/web/source-data/indexes.json", output_root / "indexes.json")
    shutil.copy("apps/web/source-data/data-quality.json", output_root / "data-quality.json")

    result = export_preview_dataset(store, run_date, output_root)

    metadata = json.loads((output_root / "indexes.json").read_text())
    one_piece = next(item for item in metadata["indexes"] if item["code"] == "OPEU500")
    history = json.loads(
        (output_root / "indexes/OPEU500/history.json").read_text()
    )
    constituents = json.loads(
        (output_root / "indexes/OPEU500/constituents.json").read_text()
    )
    rebalances = json.loads(
        (output_root / "indexes/OPEU500/rebalances.json").read_text()
    )
    archived_preview = json.loads(
        (output_root / "indexes/OPEU500/preview-history.json").read_text()
    )
    assert result["officialHistorySeparate"] is True
    assert one_piece["status"] == "preview"
    assert one_piece["name"] == "One Piece Europe 500"
    assert one_piece["target_size"] == 500
    assert one_piece["slug"] == "one-piece-europe-500"
    assert one_piece["history_start_kind"] == "preview"
    assert one_piece["official_base_date"] == "2026-07-20"
    assert history[0]["index_value"] == 1000
    assert archived_preview == history
    assert {item["name"] for item in constituents} == {
        "Real Card 1",
        "Real Card 2",
        "Real Card 3",
    }
    assert {item["set"] for item in constituents} == {"Real Set"}
    assert rebalances["data_state"] == "preview"
    assert rebalances["cadence"] == "daily_preview"
    assert rebalances["generated_for"] == run_date.isoformat()
