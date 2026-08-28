from __future__ import annotations

import json
from datetime import date
from io import BytesIO
from pathlib import Path

import polars as pl
from core.r2 import LocalObjectStore, sha256_hex
from indexengine.cutover import prepare_cutover_candidate


def _methodology(path: Path) -> Path:
    path.write_text(
        """methodology_version: "test-1"
price_field_primary: "price_avg"
price_field_fallback: "price_low"
min_price_eur: {singles: 2.0, sealed: 10.0}
seasoning_days: 90
min_history_days: 60
min_observation_ratio: 0.8
price_floor_observation_ratio: 0.8
max_suspect_zero_ratio: 0.05
daily_return_cap: 0.25
carry_forward_max_days: 5
rebalance: monthly
selection_lookback_days: 60
buffer_retention_multiplier: 1.2
buffer_entry_multiplier: 0.9
indexes:
  - code: TEST100
    name: Test Europe 100
    game_key: testgame
    universe: singles
    target_size: 1
    base_date: "2026-08-01"
    base_value: 1000
    status: accumulating
    language_scope: ["ALL_CARDMARKET_EUROPE"]
"""
    )
    return path


def _parquet_bytes(frame: pl.DataFrame) -> bytes:
    buffer = BytesIO()
    frame.write_parquet(buffer)
    return buffer.getvalue()


def _write_ready_shadow(store: LocalObjectStore, run_date: str) -> None:
    prefix = "derived/indexes/TEST100"
    rebalance = {
        "schema_version": 1,
        "index_code": "TEST100",
        "methodology_version": "test-1",
        "rebalances": [
            {
                "effective_date": run_date,
                "methodology_version": "test-1",
                "selection_snapshot_sha256": "selection-sha",
                "eligible_count": 1,
                "constituents": [
                    {
                        "cm_product_id": 1,
                        "variant_key": "nonfoil",
                        "action": "added",
                        "reason": "entrant selected at liquidity rank 1",
                        "liquidity_score": 0.95,
                        "ref_price": 12.0,
                        "stable_variant_id": "cardmarket:testgame:product:1:nonfoil",
                    }
                ],
                "removed": [],
            }
        ],
    }
    analytics = {
        "schema_version": 1,
        "index_code": "TEST100",
        "methodology_version": "test-1",
        "generated_for": run_date,
        "records": [
            {
                "value_date": run_date,
                "breadth_7d": 1.0,
                "volatility_30d": 0.1,
            }
        ],
    }
    quality = {
        "schema_version": 1,
        "index_code": "TEST100",
        "run_date": run_date,
        "status": "ready",
        "available_archive_days": 60,
        "required_lookback_days": 60,
        "target_size": 1,
        "selected_constituents": 1,
        "language_scope_status": "resolved_all_cardmarket_europe_languages",
    }
    history = pl.DataFrame(
        [
            {
                "value_date": run_date,
                "index_value": 1000.0,
                "daily_return": 0.0,
                "n_constituents_active": 1,
                "n_capped": 0,
                "n_carried_forward": 0,
                "n_stale": 0,
                "whole_market_carried_forward": False,
                "rebalance_effective_date": run_date,
                "calc_version": "test-1",
            }
        ]
    )
    contributions = pl.DataFrame(
        {
            "value_date": [],
            "stable_variant_id": [],
            "cm_product_id": [],
            "variant_key": [],
            "weight": [],
            "used_return": [],
            "contribution": [],
            "flag": [],
        }
    )
    bodies = {
        f"{prefix}/rebalances.json": json.dumps(rebalance).encode(),
        f"{prefix}/daily-values.parquet": _parquet_bytes(history),
        f"{prefix}/contributions.parquet": _parquet_bytes(contributions),
        f"{prefix}/analytics.json": json.dumps(analytics).encode(),
        f"{prefix}/quality/{run_date}.json": json.dumps(quality).encode(),
    }
    for key, body in bodies.items():
        store.write_bytes(key, body)
    manifest = {
        "schema_version": 1,
        "index_code": "TEST100",
        "generated_for": run_date,
        "status": "ready",
        "methodology_version": "test-1",
        "outputs": {
            key: {"key": key, "sha256": sha256_hex(body)} for key, body in bodies.items()
        },
    }
    store.write_bytes(f"{prefix}/manifest.json", json.dumps(manifest).encode())
    products = pl.DataFrame(
        [{"cm_product_id": 1, "name": "Real Card", "cm_expansion_id": 10}]
    )
    sets = pl.DataFrame([{"cm_expansion_id": 10, "name": "Real Set"}])
    store.write_bytes(
        "derived/catalogue/testgame/products.parquet", _parquet_bytes(products)
    )
    store.write_bytes("derived/catalogue/testgame/sets.parquet", _parquet_bytes(sets))


def test_cutover_prepares_review_candidate_without_publishing(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    run_date = "2026-10-10"
    _write_ready_shadow(store, run_date)
    official_prefix = "derived/indexes/TEST100"
    preview_prefix = "derived/preview/indexes/TEST100"
    store.write_bytes(
        f"{preview_prefix}/rebalances.json",
        store.read_bytes(f"{official_prefix}/rebalances.json"),
    )
    store.write_bytes(
        f"{preview_prefix}/daily-values.parquet",
        store.read_bytes(f"{official_prefix}/daily-values.parquet"),
    )
    audit = {
        "status": "pass",
        "cutover": {
            "indexes": [
                {"index_code": "TEST100", "state": "eligible_for_human_review"}
            ]
        },
    }
    output = tmp_path / "review"

    review = prepare_cutover_candidate(
        store,
        date.fromisoformat(run_date),
        audit,
        output,
        _methodology(tmp_path / "methodology.yaml"),
    )

    assert review["state"] == "eligible_for_human_review"
    assert review["candidateGenerated"] is True
    assert review["publicationPerformed"] is False
    constituents = json.loads(
        (output / "candidate/indexes/TEST100/constituents.json").read_text()
    )
    assert constituents[0]["name"] == "Real Card"
    metadata = json.loads(
        (output / "candidate/indexes/TEST100/metadata.json").read_text()
    )
    assert metadata["preview_history_retained_separately"] is True
    assert (output / "candidate/indexes/TEST100/preview-history.json").exists()
    assert (output / "candidate/indexes/TEST100/preview-constituents.json").exists()
    assert (output / "candidate/indexes/TEST100/preview-rebalances.json").exists()
    assert (output / "candidate/manifest.json").exists()
    assert not store.exists("derived/public/TEST100/history.json")


def test_cutover_writes_only_a_blocked_review_when_gates_fail(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "r2")
    output = tmp_path / "blocked-review"

    review = prepare_cutover_candidate(
        store,
        date(2026, 8, 13),
        {"status": "fail", "cutover": {"indexes": []}},
        output,
        _methodology(tmp_path / "methodology.yaml"),
    )

    assert review["state"] == "blocked"
    assert review["candidateGenerated"] is False
    assert (output / "cutover-review.json").exists()
    assert not (output / "candidate").exists()
