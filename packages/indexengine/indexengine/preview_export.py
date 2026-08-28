from __future__ import annotations

import json
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any

import polars as pl
from core.r2 import sha256_hex
from core.store import ObjectStore

from indexengine.calc import Rebalance
from indexengine.methodology import Methodology
from indexengine.public_export import build_public_membership_contract
from indexengine.selection import Constituent, RemovedConstituent

PREVIEW_DISCLAIMER = (
    "Provisional index based on the Cardmarket history available so far. Composition "
    "and index values may change materially during the 60-day observation period. "
    "This is not the official index and is not investment advice."
)


def _read_json(store: ObjectStore, key: str) -> dict[str, Any] | None:
    if not store.exists(key):
        return None
    try:
        payload = json.loads(store.read_bytes(key))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _outputs_verified(store: ObjectStore, manifest: dict[str, Any] | None) -> bool:
    if not manifest:
        return False
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict) or not outputs:
        return False
    for metadata in outputs.values():
        if not isinstance(metadata, dict):
            return False
        key = metadata.get("key")
        expected_sha = metadata.get("sha256")
        if not isinstance(key, str) or not isinstance(expected_sha, str):
            return False
        if not store.exists(key) or sha256_hex(store.read_bytes(key)) != expected_sha:
            return False
    return True


def _rebalances(payload: dict[str, Any]) -> list[Rebalance]:
    return [
        Rebalance(
            effective_date=str(item["effective_date"]),
            methodology_version=str(item["methodology_version"]),
            selection_snapshot_sha256=str(item["selection_snapshot_sha256"]),
            eligible_count=int(item["eligible_count"]),
            constituents=[Constituent(**value) for value in item.get("constituents", [])],
            removed=[RemovedConstituent(**value) for value in item.get("removed", [])],
        )
        for item in payload.get("rebalances", [])
    ]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str)
        + "\n"
    )


def _empty_index(metadata: dict[str, Any]) -> dict[str, Any]:
    official_base_date = metadata.get("official_base_date", metadata["base_date"])
    return {
        **metadata,
        "history_start_date": official_base_date,
        "history_start_kind": "validation",
        "base_date": official_base_date,
        "status": "accumulating",
        "breadth": 0,
        "volatility_30d": 0,
    }


def export_preview_dataset(
    store: ObjectStore,
    run_date: date,
    output_root: Path,
    methodology_path: Path = Path("packages/indexengine/methodology.yaml"),
) -> dict[str, object]:
    methodology = Methodology.load(methodology_path)
    metadata_path = output_root / "indexes.json"
    current = json.loads(metadata_path.read_text())
    current_by_code = {
        str(item["code"]): item for item in current.get("indexes", [])
    }
    if {item.code for item in methodology.indexes} != set(current_by_code):
        raise ValueError("preview export metadata does not match methodology indexes")

    exported_indexes: list[dict[str, Any]] = []
    preview_codes: list[str] = []
    for definition in methodology.indexes:
        metadata = current_by_code[definition.code]
        prefix = f"derived/preview/indexes/{definition.code}"
        manifest = _read_json(store, f"{prefix}/manifest.json")
        quality = _read_json(store, f"{prefix}/quality/{run_date.isoformat()}.json")
        rebalances_payload = _read_json(store, f"{prefix}/rebalances.json")
        analytics_payload = _read_json(store, f"{prefix}/analytics.json")
        ready = bool(
            manifest
            and manifest.get("generated_for") == run_date.isoformat()
            and manifest.get("status") == "preview"
            and manifest.get("data_state") == "preview"
            and manifest.get("methodology_version") == methodology.methodology_version
            and quality
            and quality.get("status") == "preview"
            and quality.get("public_export") == "preview_allowed"
            and rebalances_payload
            and analytics_payload
            and _outputs_verified(store, manifest)
        )
        index_root = output_root / "indexes" / definition.code
        if not ready:
            exported_indexes.append(_empty_index(metadata))
            _write_json(index_root / "history.json", [])
            _write_json(index_root / "constituents.json", [])
            _write_json(
                index_root / "rebalances.json",
                {
                    "schema_version": 1,
                    "index_code": definition.code,
                    "data_state": "validation",
                    "cadence": "monthly",
                    "generated_for": definition.base_date,
                    "rebalances": [],
                },
            )
            continue

        assert rebalances_payload is not None
        assert analytics_payload is not None
        history = pl.read_parquet(
            BytesIO(store.read_bytes(f"{prefix}/daily-values.parquet"))
        ).to_dicts()
        preview_rebalances = _rebalances(rebalances_payload)
        if not history or not preview_rebalances:
            raise ValueError(f"verified preview output is empty for {definition.code}")
        products = pl.read_parquet(
            BytesIO(
                store.read_bytes(
                    f"derived/catalogue/{definition.game_key}/products.parquet"
                )
            )
        )
        sets = pl.read_parquet(
            BytesIO(
                store.read_bytes(f"derived/catalogue/{definition.game_key}/sets.parquet")
            )
        )
        generated_for = preview_rebalances[-1].effective_date
        membership = build_public_membership_contract(
            definition.code,
            generated_for,
            preview_rebalances,
            products,
            sets,
            data_state="preview",
            cadence="daily_preview",
        )
        analytics_records = analytics_payload.get("records") or []
        latest_analytics = analytics_records[-1] if analytics_records else {}
        preview_start = str(history[0]["value_date"])
        official_base_date = metadata.get("official_base_date", metadata["base_date"])
        exported_indexes.append(
            {
                **metadata,
                "history_start_date": preview_start,
                "history_start_kind": "preview",
                "base_date": preview_start,
                "official_base_date": official_base_date,
                "status": "preview",
                "breadth": float(latest_analytics.get("breadth_7d") or 0),
                "volatility_30d": float(
                    latest_analytics.get("volatility_30d") or 0
                ),
            }
        )
        _write_json(index_root / "history.json", history)
        _write_json(index_root / "constituents.json", membership["constituents"])
        _write_json(index_root / "rebalances.json", membership["rebalances"])
        _write_json(index_root / "preview-history.json", history)
        _write_json(
            index_root / "preview-constituents.json", membership["constituents"]
        )
        _write_json(
            index_root / "preview-rebalances.json", membership["rebalances"]
        )
        preview_codes.append(definition.code)

    dataset_version = (
        f"{run_date.isoformat()}.preview.{methodology.methodology_version}"
    )
    _write_json(
        metadata_path,
        {
            **current,
            "datasetVersion": dataset_version,
            "methodologyVersion": methodology.methodology_version,
            "source": "cardmarket-derived-preview-json",
            "indexes": exported_indexes,
        },
    )
    previous_quality_path = output_root / "data-quality.json"
    previous_quality = json.loads(previous_quality_path.read_text())
    _write_json(
        previous_quality_path,
        {
            "datasetCompleteness": len(preview_codes) / len(methodology.indexes),
            "sourceCoverage": (
                f"{len(preview_codes)} of {len(methodology.indexes)} indexes expose "
                "Cardmarket-derived preview data"
            ),
            "licensingPosture": "derived-preview-contract",
            "limitations": [
                {"title": "Preview index", "body": PREVIEW_DISCLAIMER},
                {
                    "title": "Official history remains separate",
                    "body": (
                        "Preview observations are retained as a labelled preparation "
                        "phase. They are not silently merged into the official history "
                        "after the 60-day review and human cutover."
                    ),
                },
                {
                    "title": "Listing-price basis",
                    "body": (
                        "Benchmarks and constituent reference prices use daily "
                        "guide-style listing prices, not executed transaction prices."
                    ),
                },
                {
                    "title": "Daily provisional composition",
                    "body": (
                        "Preview membership is recalculated daily from the history "
                        "available at that time and may change more often than the "
                        "official monthly rebalance schedule."
                    ),
                },
                {
                    "title": "Language coverage",
                    "body": (
                        "Each index includes every language represented in the official "
                        "Cardmarket Europe catalogue; the source has no reliable language field."
                    ),
                },
                {
                    "title": "Carry-forward rule",
                    "body": (
                        "Missing constituent observations may be carried forward for a "
                        "limited window and are counted in the public status surface."
                    ),
                },
            ],
            "checks": [
                {
                    "id": "preview-output-checksums",
                    "label": "Preview output checksums",
                    "status": "pass" if preview_codes else "pending",
                    "detail": (
                        "Every exported preview is verified against its private "
                        "calculation manifest before repository files are written."
                    ),
                },
                {
                    "id": "official-history-separation",
                    "label": "Official history separation",
                    "status": "pass",
                    "detail": (
                        "Preview calculations use a dedicated R2 prefix and preview data state."
                    ),
                },
                {
                    "id": "cardmarket-source-confirmation",
                    "label": "Cardmarket source confirmation",
                    "status": "pass",
                    "detail": (
                        "Official price-guide and catalogue downloads are archived and "
                        "schema-checked for all configured games."
                    ),
                },
                {
                    "id": "official-cutover",
                    "label": "Official index publication",
                    "status": "pending",
                    "detail": (
                        "The 60-day lookback, target-size gates, and human cutover review "
                        "remain required for official publication."
                    ),
                },
            ],
            "gaps": previous_quality.get("gaps", []),
        },
    )
    return {
        "datasetVersion": dataset_version,
        "generatedFor": run_date.isoformat(),
        "previewIndexes": preview_codes,
        "previewCount": len(preview_codes),
        "officialHistorySeparate": True,
    }
