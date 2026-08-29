from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import polars as pl
import pytest
from core.r2 import LocalObjectStore
from indexengine.activity import score_trading_activity_proxy
from indexengine.activity_audit import build_activity_audit
from indexengine.eligibility import evaluate_collector_eligibility
from indexengine.methodology import Methodology
from indexengine.quality import score_data_quality
from ingest.manifest import Manifest, ManifestFile

REPO_ROOT = Path(__file__).resolve().parents[1]
V15_PATH = REPO_ROOT / "packages/indexengine/methodologies/v1.5.0-preview.1.yaml"


def _row(
    value_date: date,
    product_id: int,
    variant: str,
    avg30: float | None,
    *,
    avg1: float | None = None,
    product_kind: str = "single",
) -> dict[str, object]:
    return {
        "value_date": value_date,
        "game_key": "onepiece",
        "stable_variant_id": f"cardmarket:onepiece:product:{product_id}:{variant}",
        "cm_product_id": product_id,
        "variant_key": variant,
        "product_kind": product_kind,
        "price_avg": 20.0,
        "price_low": 18.0,
        "avg1": avg1,
        "avg7": avg30,
        "avg30": avg30,
    }


def test_data_quality_uses_avg30_without_listing_price_fallback() -> None:
    start = date(2026, 8, 1)
    prices = pl.DataFrame(
        [
            _row(start + timedelta(days=offset), 1, "nonfoil", value)
            for offset, value in enumerate((10.0, 10.0, 12.0, 12.0))
        ]
        + [_row(start + timedelta(days=offset), 2, "nonfoil", None) for offset in range(4)]
    )

    scores = score_data_quality(prices, 4)
    first = scores.filter(pl.col("cm_product_id") == 1).row(0, named=True)
    second = scores.filter(pl.col("cm_product_id") == 2).row(0, named=True)

    assert first["valuation_observation_ratio"] == 1.0
    assert first["selection_price_observation_ratio"] == 1.0
    assert first["price_update_frequency"] == pytest.approx(1 / 3)
    assert first["data_quality_score"] == pytest.approx(0.5 + 0.1 + 0.18)
    assert second["history_days"] == 0
    assert second["valuation_observation_ratio"] == 0.0
    assert second["latest_valuation_price"] is None


def test_activity_proxy_excludes_feed_repeats_and_keeps_repeated_signal_diagnostic() -> None:
    start = date(2026, 8, 1)
    prices = pl.DataFrame(
        [
            _row(start, 1, "nonfoil", 20.0, avg1=12.0),
            _row(start + timedelta(days=1), 1, "nonfoil", 20.0, avg1=99.0),
            _row(start + timedelta(days=2), 1, "nonfoil", 20.0, avg1=12.0),
            _row(start, 2, "nonfoil", 20.0, avg1=0.0),
            _row(start + timedelta(days=2), 2, "nonfoil", 20.0, avg1=None),
        ]
    )

    scores = score_trading_activity_proxy(
        prices,
        [start, start + timedelta(days=2)],
        start + timedelta(days=3),
    )
    active = scores.filter(pl.col("cm_product_id") == 1).row(0, named=True)
    inactive = scores.filter(pl.col("cm_product_id") == 2).row(0, named=True)

    assert active["observable_source_days"] == 2
    assert active["activity_days"] == 2
    assert active["activity_ratio"] == 1.0
    assert active["repeated_positive_signal_days"] == 1
    assert active["last_positive_signal_date"] == start + timedelta(days=2)
    assert active["days_since_positive_signal"] == 1
    assert inactive["activity_days"] == 0
    assert inactive["zero_signal_days"] == 1
    assert inactive["null_or_missing_signal_days"] == 1


def test_collector_eligibility_is_uncapped_variant_level_and_activity_is_not_a_gate() -> None:
    methodology = Methodology.load(V15_PATH)
    definition = methodology.index_by_code("OPEUCOL")
    start = date(2026, 8, 1)
    effective_date = start + timedelta(days=7)
    prices = pl.DataFrame(
        [
            _row(day, product_id, variant, avg30, avg1=None)
            for day in (start + timedelta(days=offset) for offset in range(7))
            for product_id, variant, avg30 in (
                (1, "nonfoil", 10.0),
                (1, "foil", 15.0),
                (2, "nonfoil", 9.99),
                (3, "nonfoil", 11.0),
                (4, "nonfoil", None),
            )
        ]
        + [
            _row(day, 5, "nonfoil", 50.0, product_kind="sealed")
            for day in (start + timedelta(days=offset) for offset in range(7))
        ]
    )
    products = pl.DataFrame(
        [
            {
                "cm_product_id": product_id,
                "source_date_added": added,
                "first_seen": added,
            }
            for product_id, added in (
                (1, "2020-01-01"),
                (2, "2020-01-01"),
                (3, "2026-08-01"),
                (4, "2020-01-01"),
                (5, "2020-01-01"),
            )
        ]
    )
    calendar = [start + timedelta(days=offset) for offset in range(7)]

    result = evaluate_collector_eligibility(
        prices,
        products,
        definition,
        methodology,
        effective_date,
        calendar_dates=calendar,
        unchanged_dates={start + timedelta(days=1)},
        data_state="shadow",
    )

    assert [item.identity for item in result.eligible_variants] == [
        (1, "foil"),
        (1, "nonfoil"),
    ]
    assert all(item.activity_ratio == 0.0 for item in result.eligible_variants)
    assert result.required_history_days == 7
    assert result.quality_calendar_days == 7
    assert result.activity_observable_days == 6
    assert result.excluded_unchanged_days == 1
    by_identity = {item.identity: item for item in result.diagnostics}
    assert by_identity[(2, "nonfoil")].exclusion_reasons == ("latest_avg30_below_threshold",)
    assert "seasoning_days" in by_identity[(3, "nonfoil")].exclusion_reasons
    assert "latest_avg30_not_positive" in by_identity[(4, "nonfoil")].exclusion_reasons
    assert (5, "nonfoil") not in by_identity

    reversed_result = evaluate_collector_eligibility(
        prices.reverse(),
        products.reverse(),
        definition,
        methodology,
        effective_date,
        calendar_dates=list(reversed(calendar)),
        unchanged_dates={start + timedelta(days=1)},
        data_state="shadow",
    )
    assert reversed_result.snapshot_sha256 == result.snapshot_sha256


def test_official_history_gate_is_not_relaxed_by_shadow_availability() -> None:
    methodology = Methodology.load(V15_PATH)
    definition = methodology.index_by_code("OPEUCOL")
    start = date(2026, 8, 1)
    effective_date = start + timedelta(days=7)
    prices = pl.DataFrame(
        [_row(start + timedelta(days=offset), 1, "nonfoil", 10.0, avg1=10.0) for offset in range(7)]
    )
    products = pl.DataFrame(
        [{"cm_product_id": 1, "source_date_added": "2020-01-01", "first_seen": start}]
    )

    result = evaluate_collector_eligibility(
        prices,
        products,
        definition,
        methodology,
        effective_date,
        calendar_dates=[start + timedelta(days=offset) for offset in range(7)],
        data_state="official",
    )

    assert result.required_history_days == 60
    assert result.eligible_variants == ()
    assert result.diagnostics[0].exclusion_reasons == ("history_days",)


def test_private_activity_audit_uses_real_archive_calendar_semantics(tmp_path: Path) -> None:
    methodology = Methodology.load(V15_PATH)
    methodology = replace(
        methodology,
        indexes=[item for item in methodology.indexes if item.game_key == "onepiece"],
    )
    store = LocalObjectStore(tmp_path / "r2")
    start = date(2026, 8, 1)
    days = [start + timedelta(days=offset) for offset in range(3)]
    prices = pl.DataFrame(
        [
            _row(days[0], 1, "nonfoil", 20.0, avg1=10.0),
            _row(days[1], 1, "nonfoil", 20.0, avg1=99.0),
            _row(days[2], 1, "nonfoil", 20.0, avg1=10.0),
            _row(days[0], 2, "nonfoil", 40.0, avg1=0.0, product_kind="sealed"),
            _row(days[1], 2, "nonfoil", 40.0, avg1=99.0, product_kind="sealed"),
            _row(days[2], 2, "nonfoil", 40.0, avg1=None, product_kind="sealed"),
        ]
    )
    buffer = BytesIO()
    prices.write_parquet(buffer)
    store.write_bytes(
        "derived/prices/onepiece/2026-08.parquet",
        buffer.getvalue(),
        "application/vnd.apache.parquet",
    )
    for index, value_date in enumerate(days):
        price_file = ManifestFile(
            game="onepiece",
            kind="priceguide",
            key=f"cardmarket/priceguide/onepiece/{value_date.isoformat()}.json.gz",
            sha256_uncompressed="0" * 64,
            size_uncompressed=1,
            fetched_at=f"{value_date.isoformat()}T00:00:00+00:00",
            headers={},
            unchanged_from_previous=index == 1,
        )
        store.write_bytes(
            f"manifests/{value_date.isoformat()}.json",
            Manifest(value_date.isoformat(), [price_file]).to_json_bytes(),
            "application/json",
        )

    report = build_activity_audit(store, methodology, days[-1])
    game = report["games"][0]

    assert game["observable_source_days"] == 2
    assert game["excluded_unchanged_snapshots"] == 1
    assert game["universes"]["singles"]["positive_signal_rate"] == 1.0
    assert game["universes"]["singles"]["repeated_positive_signal_rate"] == 0.5
    assert game["universes"]["sealed"]["zero_signal_rate"] == 0.5
    assert report["semantics"]["hard_eligibility_gate_supported"] is False
