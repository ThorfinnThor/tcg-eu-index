from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from core.r2 import LocalObjectStore
from core.settings import Settings
from ingest.archive import run_archive
from ingest.audit import audit_archive, render_audit_summary


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
    assert report["r2"]["storage"]["object_count"] == 3
    assert report["r2"]["storage"]["categories"]["raw_snapshots"]["object_count"] == 2
    assert report["r2"]["operations"]["class_a"]["projected_operations"] == 31_000
    assert report["r2"]["operations"]["class_b"]["projected_operations"] == 124_000
    assert report["cutover"]["state"] == "accumulating"
    assert report["cutover"]["first_full_observation_date_if_gapless"] == "2026-09-17"
    assert report["cutover"]["first_monthly_rebalance_date_if_gapless"] == "2026-10-01"


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


def test_archive_audit_reports_index_cutover_readiness(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    run_archive(
        date(2026, 7, 20),
        audit_settings(),
        store=store,
        fetcher=AuditFakeFetcher(),
        data_dir=tmp_path,
    )
    quality_key = "derived/indexes/OPEU100/quality/2026-07-20.json"
    store.write_bytes(
        quality_key,
        json.dumps(
            {
                "run_date": "2026-07-20",
                "status": "ready",
                "available_archive_days": 60,
                "required_lookback_days": 60,
                "target_size": 100,
                "selected_constituents": 100,
                "language_scope_status": "resolved",
            }
        ).encode(),
        "application/json",
    )

    report = audit_archive(
        store,
        date(2026, 7, 20),
        date(2026, 7, 20),
        ["onepiece"],
        sample_rate=1.0,
        seed="fixture",
        index_codes=["OPEU100"],
    )

    readiness = report["cutover"]["indexes"][0]
    assert report["status"] == "pass"
    assert report["cutover"]["state"] == "eligible_for_human_review"
    assert readiness["quality_key"] == quality_key
    assert readiness["blocking_gates"] == []
    summary = render_audit_summary(report)
    assert "| OPEU100 | eligible_for_human_review | 60 | 0 | 100 / 100 | resolved |" in summary
    assert "Operation counts are conservative workflow projections" in summary


def test_archive_audit_warns_before_projected_operation_limit(tmp_path: Path) -> None:
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
        scheduled_attempts_per_day=104,
    )

    assert report["status"] == "pass"
    assert report["r2"]["operations"]["class_a"]["status"] == "warning"
    assert report["r2"]["operations"]["class_b"]["status"] == "within_free_tier"
    assert "R2 class_a projection status is warning" in report["warnings"]


def test_archive_audit_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    store_root = tmp_path / "r2"
    run_archive(
        date(2026, 7, 20),
        audit_settings(),
        store=LocalObjectStore(store_root),
        fetcher=AuditFakeFetcher(),
        data_dir=tmp_path,
    )
    json_output = tmp_path / "audit.json"
    markdown_output = tmp_path / "audit.md"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_archive.py",
            "--store-root",
            str(store_root),
            "--since",
            "2026-07-20",
            "--until",
            "2026-07-20",
            "--games",
            "onepiece",
            "--output",
            str(json_output),
            "--summary-output",
            str(markdown_output),
        ],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(json_output.read_text())["r2"]["storage"]["object_count"] == 3
    assert "# Cardmarket archive audit" in markdown_output.read_text()
