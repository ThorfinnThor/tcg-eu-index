from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from core.r2 import LocalObjectStore
from core.settings import Settings
from ingest.backfill import backfill_archive
from ingest.manifest import manifest_key
from ingest.normalize import GameNormalizationResult


def settings() -> Settings:
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


def test_backfill_continues_and_reports_calendar_gaps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    first_day = date(2026, 8, 9)
    store.write_bytes(manifest_key(first_day), b"fixture", "application/json")

    def fake_normalize(*args: object, **kwargs: object) -> list[GameNormalizationResult]:
        return [
            GameNormalizationResult(
                game="onepiece",
                run_date=first_day.isoformat(),
                status="ok",
                catalogue_products=1,
                catalogue_sets=1,
                catalogue_variants=1,
                price_rows=1,
                classification_coverage=1.0,
                unknown_categories=[],
                changed_outputs=[],
            )
        ]

    monkeypatch.setattr("ingest.backfill.run_normalize", fake_normalize)
    report = backfill_archive(
        store,
        first_day,
        date(2026, 8, 10),
        settings(),
    )

    assert report["status"] == "fail"
    assert report["ok_runs"] == 1
    assert report["errors"] == ["2026-08-10: missing manifest"]
