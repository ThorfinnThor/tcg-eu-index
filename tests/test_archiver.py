from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

from core.r2 import LocalObjectStore, gunzip_body
from core.settings import Settings
from ingest.archive import run_archive
from ingest.manifest import manifest_key


class FakeFetcher:
    def fetch(self, url: str) -> tuple[bytes, dict[str, str]]:
        body = (
            [{"idProduct": 1, "avg": 2.5, "low": 2.0}]
            if "price" in url
            else [{"idProduct": 1, "name": "Card", "category": "single"}]
        )
        return json.dumps(body).encode(), {"etag": "fixture"}


class OfficialFakeFetcher:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def fetch(self, url: str) -> tuple[bytes, dict[str, str]]:
        self.urls.append(url)
        if "priceGuide" in url:
            body = {"version": 1, "createdAt": "2026-08-09", "priceGuides": []}
        else:
            product_id = 1 if "products_singles_" in url else 2
            body = {
                "version": 1,
                "createdAt": "2026-08-09",
                "products": [{"idProduct": product_id}],
            }
        return json.dumps(body).encode(), {"etag": "fixture"}


def settings() -> Settings:
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


def test_archive_is_idempotent(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    first = run_archive(
        date(2026, 7, 20),
        settings(),
        store=store,
        fetcher=FakeFetcher(),
        data_dir=tmp_path,
    )
    second = run_archive(
        date(2026, 7, 20),
        settings(),
        store=store,
        fetcher=FakeFetcher(),
        data_dir=tmp_path,
    )
    assert first == second
    assert store.exists(manifest_key(date(2026, 7, 20)))
    raw = gunzip_body(store.read_bytes(first.files[0].key))
    assert json.loads(raw)[0]["idProduct"] == 1


def test_archive_uses_official_downloads_and_combines_catalogues(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    fetcher = OfficialFakeFetcher()
    configured = replace(
        settings(),
        cm_priceguide_url_template="",
        cm_catalogue_url_template="",
    )
    manifest = run_archive(
        date(2026, 8, 9),
        configured,
        store=store,
        fetcher=fetcher,
        data_dir=tmp_path,
    )
    catalogue_file = next(item for item in manifest.files if item.kind == "catalogue")
    catalogue = json.loads(gunzip_body(store.read_bytes(catalogue_file.key)))
    assert [product["idProduct"] for product in catalogue["products"]] == [1, 2]
    assert len(fetcher.urls) == 3
