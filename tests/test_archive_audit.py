from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from core.r2 import LocalObjectStore
from core.settings import Settings
from ingest.archive import run_archive
from ingest.audit import audit_archive


class AuditFakeFetcher:
    def fetch(self, url: str) -> tuple[bytes, dict[str, str]]:
        payload = (
            {
                "version": 1,
                "createdAt": "2026-07-20T00:00:00Z",
                "priceGuides": [{"idProduct": item} for item in range(1, 1_001)],
            }
            if "price" in url
            else {
                "version": 1,
                "createdAt": "2026-07-20T00:00:00Z",
                "products": [{"idProduct": 1}],
            }
        )
        return json.dumps(payload).encode(), {}


def audit_settings() -> Settings:
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


def test_archive_audit_reports_gaps_and_samples_files(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    run_archive(
        date(2026, 7, 20),
        audit_settings(),
        store=store,
        fetcher=AuditFakeFetcher(),
        data_dir=tmp_path,
    )
    run_archive(
        date(2026, 7, 21),
        audit_settings(),
        store=store,
        fetcher=AuditFakeFetcher(),
        data_dir=tmp_path,
    )

    report = audit_archive(
        store,
        date(2026, 7, 20),
        date(2026, 7, 22),
        ["onepiece"],
        sample_rate=0.25,
        seed="fixture",
    )
    assert report["status"] == "fail"
    assert report["manifest_count"] == 2
    assert report["verified_file_count"] == 1
    assert "2026-07-22: missing manifest" in report["errors"]


def test_archive_audit_passes_complete_range(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    run_archive(
        date(2026, 7, 20),
        audit_settings(),
        store=store,
        fetcher=AuditFakeFetcher(),
        data_dir=tmp_path,
    )
    report = audit_archive(
        store,
        date(2026, 7, 20),
        date(2026, 7, 20),
        ["onepiece"],
        sample_rate=1.0,
        seed="fixture",
    )
    assert report["status"] == "pass"
    assert report["verified_file_count"] == 2
    assert report["errors"] == []


def test_archive_audit_reports_malformed_manifest_metadata(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    run_archive(
        date(2026, 7, 20),
        audit_settings(),
        store=store,
        fetcher=AuditFakeFetcher(),
        data_dir=tmp_path,
    )
    manifest_path = tmp_path / "r2" / "manifests" / "2026-07-20.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files"][0]["fetched_at"] = 123
    manifest_path.write_text(json.dumps(manifest))

    report = audit_archive(
        store,
        date(2026, 7, 20),
        date(2026, 7, 20),
        ["onepiece"],
        sample_rate=1.0,
        seed="fixture",
    )
    assert report["status"] == "fail"
    assert any("invalid fetched_at" in error for error in report["errors"])


def test_archive_audit_rejects_manifest_stored_under_wrong_date(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    run_archive(
        date(2026, 7, 20),
        audit_settings(),
        store=store,
        fetcher=AuditFakeFetcher(),
        data_dir=tmp_path,
    )
    original = tmp_path / "r2" / "manifests" / "2026-07-20.json"
    wrong_date = tmp_path / "r2" / "manifests" / "2026-07-21.json"
    wrong_date.write_bytes(original.read_bytes())

    report = audit_archive(
        store,
        date(2026, 7, 21),
        date(2026, 7, 21),
        ["onepiece"],
        sample_rate=1.0,
        seed="fixture",
    )
    assert report["status"] == "fail"
    assert "2026-07-21: manifest run_date is '2026-07-20'" in report["errors"]
