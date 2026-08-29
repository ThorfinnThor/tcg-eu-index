from __future__ import annotations

import json
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import polars as pl
from core.r2 import LocalObjectStore
from core.settings import Settings
from indexengine.collector_run import run_collector_shadow
from ingest.manifest import Manifest, ManifestFile


def _write_parquet(store: LocalObjectStore, key: str, frame: pl.DataFrame) -> None:
    buffer = BytesIO()
    frame.write_parquet(buffer)
    store.write_bytes(key, buffer.getvalue(), "application/vnd.apache.parquet")


def _settings() -> Settings:
    return Settings(
        cm_games=["onepiece"],
        cm_priceguide_url_template="",
        cm_catalogue_url_template="",
        cm_user_agent="tests",
        r2_account_id="",
        r2_access_key_id="",
        r2_secret_access_key="",
        r2_bucket="test",
        supabase_db_url="",
        supabase_url="",
        supabase_anon_key="",
        alert_discord_webhook=None,
    )


def test_runs_enabled_single_family_and_enriches_private_output(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    first = date(2026, 8, 1)
    days = [first + timedelta(days=offset) for offset in range(10)]
    rows = []
    for value_date in days:
        rows.append(
            {
                "value_date": value_date,
                "game_key": "onepiece",
                "stable_variant_id": "cardmarket:onepiece:product:1:nonfoil",
                "cm_product_id": 1,
                "variant_key": "nonfoil",
                "product_kind": "single",
                "avg1": 12.0,
                "avg7": 12.0,
                "avg30": 12.0,
            }
        )
        file = ManifestFile(
            game="onepiece",
            kind="priceguide",
            key=f"cardmarket/priceguide/onepiece/{value_date.isoformat()}.json.gz",
            sha256_uncompressed="a" * 64,
            size_uncompressed=1,
            fetched_at=f"{value_date.isoformat()}T00:00:00+00:00",
            headers={},
            unchanged_from_previous=False,
        )
        store.write_bytes(
            f"manifests/{value_date.isoformat()}.json",
            Manifest(value_date.isoformat(), [file]).to_json_bytes(),
            "application/json",
        )
    _write_parquet(store, "derived/prices/onepiece/2026-08.parquet", pl.DataFrame(rows))
    _write_parquet(
        store,
        "derived/catalogue/onepiece/products.parquet",
        pl.DataFrame(
            [
                {
                    "cm_product_id": 1,
                    "cm_expansion_id": 10,
                    "name": "Roronoa Zoro (OP01-001)",
                    "display_name": "Roronoa Zoro",
                    "collector_number": "OP01-001",
                    "image_url": "https://images.example.test/zoro.jpg",
                    "image_source": "licensed-test-source",
                    "tcgplayer_product_url": "https://www.tcgplayer.com/product/123/zoro",
                    "metadata_status": "complete",
                    "source_date_added": "2020-01-01 00:00:00",
                    "first_seen": first,
                }
            ]
        ),
    )
    _write_parquet(
        store,
        "derived/catalogue/onepiece/sets.parquet",
        pl.DataFrame([{"cm_expansion_id": 10, "name": "Romance Dawn"}]),
    )
    methodology = Path("packages/indexengine/methodologies/v1.5.0-preview.2.yaml")

    results = run_collector_shadow(
        days[-1], _settings(), store=store, methodology_path=methodology
    )

    one_piece = next(item for item in results if item.index_code == "OPEUCOL")
    assert one_piece.status == "preview"
    assert one_piece.constituents == 1
    assert not any(item.index_code.endswith("SCOL") for item in results)
    prefix = "derived/indexes/1.5.0-preview.2/private_shadow/OPEUCOL"
    payload = json.loads(store.read_bytes(f"{prefix}/rebalances.json"))
    member = payload["rebalances"][-1]["constituents"][0]
    assert member["name"] == "Roronoa Zoro"
    assert member["set_name"] == "Romance Dawn"
    assert member["collector_number"] == "OP01-001"
    assert member["image_url"] == "https://images.example.test/zoro.jpg"
    assert member["tcgplayer_product_url"] == "https://www.tcgplayer.com/product/123/zoro"
