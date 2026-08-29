from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import polars as pl
from core.r2 import LocalObjectStore
from indexengine.collector_audit import (
    build_collector_methodology_audit,
    render_collector_audit_summary,
)
from indexengine.methodology import Methodology
from ingest.manifest import Manifest, ManifestFile

REPO_ROOT = Path(__file__).resolve().parents[1]
V15_PATH = REPO_ROOT / "packages/indexengine/methodologies/v1.5.0-preview.1.yaml"
V152_PATH = REPO_ROOT / "packages/indexengine/methodologies/v1.5.0-preview.2.yaml"


def _write_parquet(store: LocalObjectStore, key: str, frame: pl.DataFrame) -> None:
    buffer = BytesIO()
    frame.write_parquet(buffer)
    store.write_bytes(key, buffer.getvalue(), "application/vnd.apache.parquet")


def _price_row(
    value_date: date,
    product_id: int,
    product_kind: str,
    avg30: float | None,
    avg7: float | None,
    avg1: float | None,
) -> dict[str, object]:
    return {
        "value_date": value_date,
        "game_key": "onepiece",
        "stable_variant_id": f"cardmarket:onepiece:product:{product_id}:nonfoil",
        "cm_product_id": product_id,
        "variant_key": "nonfoil",
        "product_kind": product_kind,
        "price_avg": 20.0,
        "price_low": 18.0,
        "avg1": avg1,
        "avg7": avg7,
        "avg30": avg30,
    }


def _write_manifest(store: LocalObjectStore, value_date: date, unchanged: bool = False) -> None:
    price_file = ManifestFile(
        game="onepiece",
        kind="priceguide",
        key=f"cardmarket/priceguide/onepiece/{value_date.isoformat()}.json.gz",
        sha256_uncompressed="0" * 64,
        size_uncompressed=1,
        fetched_at=f"{value_date.isoformat()}T00:00:00+00:00",
        headers={},
        unchanged_from_previous=unchanged,
    )
    store.write_bytes(
        f"manifests/{value_date.isoformat()}.json",
        Manifest(value_date.isoformat(), [price_file]).to_json_bytes(),
        "application/json",
    )


def test_collector_methodology_audit_is_aggregate_and_keeps_activity_diagnostic(
    tmp_path: Path,
) -> None:
    methodology = Methodology.load(V15_PATH)
    methodology = replace(
        methodology,
        indexes=[item for item in methodology.indexes if item.game_key == "onepiece"],
    )
    store = LocalObjectStore(tmp_path / "r2")
    start = date(2026, 8, 1)
    days = [start + timedelta(days=offset) for offset in range(10)]
    rows = []
    for offset, value_date in enumerate(days):
        rows.extend(
            [
                _price_row(value_date, 1, "single", 12.0, 11.0 + offset, 10.0),
                _price_row(value_date, 2, "single", 9.0, 9.0, 8.0),
                _price_row(value_date, 3, "sealed", 40.0, None, None),
            ]
        )
        _write_manifest(store, value_date, unchanged=offset == 1)
    _write_parquet(store, "derived/prices/onepiece/2026-08.parquet", pl.DataFrame(rows))
    _write_parquet(
        store,
        "derived/catalogue/onepiece/products.parquet",
        pl.DataFrame(
            [
                {
                    "cm_product_id": product_id,
                    "source_date_added": "2020-01-01 00:00:00",
                    "first_seen": days[0].isoformat(),
                }
                for product_id in (1, 2, 3)
            ]
        ),
    )
    store.write_bytes(
        "derived/preview/indexes/OPEU500/rebalances.json",
        json.dumps(
            {
                "rebalances": [
                    {
                        "effective_date": days[7].isoformat(),
                        "constituents": [
                            {"stable_variant_id": "cardmarket:onepiece:product:1:nonfoil"}
                        ],
                    }
                ]
            }
        ).encode(),
        "application/json",
    )
    _write_parquet(
        store,
        "derived/preview/indexes/OPEU500/daily-values.parquet",
        pl.DataFrame(
            [
                {"value_date": value_date.isoformat(), "daily_return": 0.01 * offset}
                for offset, value_date in enumerate(days[7:])
            ]
        ),
    )

    report = build_collector_methodology_audit(store, methodology, days[-1])
    by_code = {item["index_code"]: item for item in report["indexes"]}
    singles = by_code["OPEUCOL"]
    sealed = by_code["OPEUSCOL"]

    assert singles["canonical"]["latest_constituent_count"] == 1
    assert singles["activity_proxy"]["hard_gate_enabled"] is False
    assert singles["activity_proxy"]["counterfactual_candidate_pass_count"] == 1
    assert singles["legacy_comparison"]["collector_member_overlap_ratio"] == 1.0
    assert sealed["canonical"]["latest_constituent_count"] == 1
    assert sealed["alternate"]["latest_constituent_count"] == 0
    assert "avg7_alternate_unavailable" in sealed["review_flags"]
    assert report["decision"]["new_preview_methodology_version_required"] is False
    assert report["decision"]["methodology_correction_required_before_publication"] is False
    assert report["decision"]["publication_state"] == "remain_private_shadow"
    assert report["privacy"]["contains_product_identities"] is False
    serialized = json.dumps(report, sort_keys=True)
    assert "cardmarket:onepiece:product:" not in serialized
    assert "cm_product_id" not in serialized

    summary = render_collector_audit_summary(report)
    assert "OPEUCOL" in summary
    assert "AVG1 remains a Trading Activity Proxy only" in summary


def test_collector_methodology_audit_blocks_missing_sealed_sold_prices(
    tmp_path: Path,
) -> None:
    methodology = Methodology.load(V15_PATH)
    methodology = replace(
        methodology,
        indexes=[item for item in methodology.indexes if item.game_key == "onepiece"],
    )
    store = LocalObjectStore(tmp_path / "r2")
    days = [date(2026, 8, 1) + timedelta(days=offset) for offset in range(8)]
    products = pl.DataFrame(
        [
            {
                "stable_product_id": "cardmarket:onepiece:product:3",
                "game_key": "onepiece",
                "cm_product_id": 3,
                "product_kind": "sealed",
                "first_seen": days[0],
            }
        ]
    )
    _write_parquet(store, "derived/catalogue/onepiece/products.parquet", products)
    prices = pl.DataFrame(
        [_price_row(value_date, 3, "sealed", None, None, None) for value_date in days]
    )
    _write_parquet(store, "derived/prices/onepiece/2026-08.parquet", prices)
    for value_date in days:
        _write_manifest(store, value_date)

    report = build_collector_methodology_audit(store, methodology, days[-1])
    sealed = next(item for item in report["indexes"] if item["index_code"] == "OPEUSCOL")

    assert report["decision"]["new_preview_methodology_version_required"] is True
    assert report["decision"]["methodology_correction_required_before_publication"] is True
    assert report["decision"]["audit_status"] == "preliminary_blocked"
    assert report["decision"]["source_blockers"] == {
        "sealed_indexes_without_positive_avg30": ["OPEUSCOL"]
    }
    assert "sold_price_avg30_source_unavailable" in sealed["review_flags"]


def test_preview2_audit_records_sealed_as_deferred_without_requesting_preview3(
    tmp_path: Path,
) -> None:
    methodology = Methodology.load(V152_PATH)
    methodology = replace(
        methodology,
        indexes=[item for item in methodology.indexes if item.game_key == "onepiece"],
    )
    store = LocalObjectStore(tmp_path / "r2")
    days = [date(2026, 8, 1) + timedelta(days=offset) for offset in range(8)]
    _write_parquet(
        store,
        "derived/catalogue/onepiece/products.parquet",
        pl.DataFrame(
            [
                {
                    "stable_product_id": "cardmarket:onepiece:product:3",
                    "game_key": "onepiece",
                    "cm_product_id": 3,
                    "product_kind": "sealed",
                    "first_seen": days[0],
                }
            ]
        ),
    )
    _write_parquet(
        store,
        "derived/prices/onepiece/2026-08.parquet",
        pl.DataFrame(
            [_price_row(value_date, 3, "sealed", None, None, None) for value_date in days]
        ),
    )
    for value_date in days:
        _write_manifest(store, value_date)

    report = build_collector_methodology_audit(store, methodology, days[-1])
    sealed = next(item for item in report["indexes"] if item["index_code"] == "OPEUSCOL")

    assert sealed["calculation_status"] == "deferred"
    assert sealed["source_status"] == "rolling_sold_price_unavailable"
    assert report["decision"]["new_preview_methodology_version_required"] is False
    assert report["decision"]["methodology_correction_required_before_publication"] is False
    assert report["decision"]["audit_status"] == (
        "preliminary_complete_with_deferred_family"
    )
    assert report["decision"]["deferred_indexes"] == ["OPEUSCOL"]


def test_collector_methodology_audit_requires_avg7_calibration(tmp_path: Path) -> None:
    methodology = Methodology.load(V15_PATH)
    assert methodology.calibration is not None
    methodology = replace(
        methodology,
        calibration=replace(methodology.calibration, alternate_valuation_fields=("avg14",)),
    )

    try:
        build_collector_methodology_audit(
            LocalObjectStore(tmp_path / "r2"), methodology, date(2026, 8, 10)
        )
    except ValueError as exc:
        assert "avg7 calibration" in str(exc)
    else:
        raise AssertionError("expected avg7 calibration validation failure")
