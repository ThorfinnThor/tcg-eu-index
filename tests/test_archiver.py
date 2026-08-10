from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from core.r2 import LocalObjectStore, gunzip_body, gzip_body
from core.settings import Settings
from ingest.archive import ArchiveConflictError, run_archive, snapshot_key
from ingest.manifest import manifest_key


def price_payload(marker: int = 1) -> bytes:
    records = [
        {"idProduct": item, "avg": 2.5 + marker, "low": 2.0}
        for item in range(1, 1_001)
    ]
    return json.dumps(
        {"version": 1, "createdAt": "2026-08-09T02:00:00Z", "priceGuides": records}
    ).encode()


def catalogue_payload(marker: int = 1) -> bytes:
    return json.dumps(
        {
            "version": 1,
            "createdAt": "2026-08-09T01:00:00Z",
            "products": [
                {
                    "idProduct": 1,
                    "name": f"Card {marker}",
                    "idCategory": 1,
                    "categoryName": "Single",
                }
            ],
        }
    ).encode()


class FakeFetcher:
    def __init__(self, marker: int = 1, invalid_price: bool = False) -> None:
        self.marker = marker
        self.invalid_price = invalid_price
        self.calls = 0

    def fetch(self, url: str) -> tuple[bytes, dict[str, str]]:
        self.calls += 1
        if "price" in url:
            body = (
                b"<html>upstream error</html>"
                if self.invalid_price
                else price_payload(self.marker)
            )
        else:
            body = catalogue_payload(self.marker)
        return body, {"etag": f"fixture-{self.marker}"}


class OfficialFakeFetcher:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def fetch(self, url: str) -> tuple[bytes, dict[str, str]]:
        self.urls.append(url)
        if "priceGuide" in url:
            return price_payload(), {"etag": "price-fixture"}
        product_id = 1 if "products_singles_" in url else 2
        body = {
            "version": 1,
            "createdAt": "2026-08-09T01:00:00Z",
            "products": [{"idProduct": product_id}],
        }
        return json.dumps(body).encode(), {"etag": "catalogue-fixture"}


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
    fetcher = FakeFetcher()
    first = run_archive(
        date(2026, 7, 20), settings(), store=store, fetcher=fetcher, data_dir=tmp_path
    )
    second = run_archive(
        date(2026, 7, 20), settings(), store=store, fetcher=fetcher, data_dir=tmp_path
    )
    assert first == second
    assert fetcher.calls == 2
    assert store.exists(manifest_key(date(2026, 7, 20)))
    raw = gunzip_body(store.read_bytes(first.files[0].key))
    assert json.loads(raw)["priceGuides"][0]["idProduct"] == 1


def test_archive_marks_content_unchanged_from_previous_day(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    run_archive(
        date(2026, 7, 20), settings(), store=store, fetcher=FakeFetcher(), data_dir=tmp_path
    )
    second = run_archive(
        date(2026, 7, 21), settings(), store=store, fetcher=FakeFetcher(), data_dir=tmp_path
    )
    assert all(file.unchanged_from_previous for file in second.files)
    assert all("2026-07-21" in file.key for file in second.files)


def test_archive_detects_changed_content_from_previous_day(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    run_archive(
        date(2026, 7, 20), settings(), store=store, fetcher=FakeFetcher(), data_dir=tmp_path
    )
    second = run_archive(
        date(2026, 7, 21),
        settings(),
        store=store,
        fetcher=FakeFetcher(marker=2),
        data_dir=tmp_path,
    )
    assert not any(file.unchanged_from_previous for file in second.files)


def test_archive_preserves_and_fails_on_immutable_key_conflict(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    run_date = date(2026, 7, 20)
    price_key = snapshot_key("priceguide", "onepiece", run_date)
    store.write_bytes(price_key, gzip_body(b'{"wrong":true}'), "application/gzip")

    with pytest.raises(ArchiveConflictError, match="immutable key conflict"):
        run_archive(run_date, settings(), store=store, fetcher=FakeFetcher(), data_dir=tmp_path)

    assert store.exists(price_key.replace(".json.gz", ".conflict-1.json.gz"))
    assert not store.exists(manifest_key(run_date))


def test_archive_rejects_invalid_source_before_writing(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    run_date = date(2026, 7, 20)
    with pytest.raises(ValueError, match="not valid JSON"):
        run_archive(
            run_date,
            settings(),
            store=store,
            fetcher=FakeFetcher(invalid_price=True),
            data_dir=tmp_path,
        )
    assert not store.exists(snapshot_key("priceguide", "onepiece", run_date))
    assert not store.exists(manifest_key(run_date))


def test_existing_manifest_is_revalidated(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    run_date = date(2026, 7, 20)
    manifest = run_archive(
        run_date, settings(), store=store, fetcher=FakeFetcher(), data_dir=tmp_path
    )
    store.write_bytes(manifest.files[0].key, gzip_body(b'{"priceGuides":[]}'), "application/gzip")
    with pytest.raises(RuntimeError, match="existing archive manifest failed validation"):
        run_archive(run_date, settings(), store=store, fetcher=FakeFetcher(), data_dir=tmp_path)


def test_archive_uses_official_downloads_and_combines_catalogues(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    fetcher = OfficialFakeFetcher()
    configured = replace(
        settings(),
        cm_priceguide_url_template="",
        cm_catalogue_url_template="",
    )
    manifest = run_archive(
        date(2026, 8, 9), configured, store=store, fetcher=fetcher, data_dir=tmp_path
    )
    catalogue_file = next(item for item in manifest.files if item.kind == "catalogue")
    catalogue = json.loads(gunzip_body(store.read_bytes(catalogue_file.key)))
    assert [product["idProduct"] for product in catalogue["products"]] == [1, 2]
    assert catalogue_file.source_created_at == "2026-08-09T01:00:00Z"
    assert len(fetcher.urls) == 3
