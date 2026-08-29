from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from core.r2 import sha256_hex
from core.store import ObjectStore

from indexengine.methodology import IndexDefinition, Methodology

DEFAULT_METHODOLOGY = Path("packages/indexengine/methodologies/v1.5.0-preview.2.yaml")


@dataclass(frozen=True)
class CollectorPreviewExportResult:
    generated_for: str
    indexes: int
    variants: int
    changed_files: list[str]


def export_collector_preview(
    store: ObjectStore,
    run_date: date,
    output_root: Path,
    methodology_path: Path = DEFAULT_METHODOLOGY,
) -> CollectorPreviewExportResult:
    """Export a bounded, noindex web projection of private collector singles."""
    methodology = Methodology.load(methodology_path)
    definitions = [
        definition
        for definition in methodology.indexes
        if _is_enabled_single(definition, methodology)
    ]
    changed: list[str] = []
    index_rows: list[dict[str, object]] = []
    variants = 0
    for definition in definitions:
        projection = _projection(store, definition, methodology, run_date)
        index_root = output_root / "collector" / definition.code
        for filename, payload in projection.items():
            if _write_json_if_changed(index_root / filename, payload):
                changed.append(f"collector/{definition.code}/{filename}")
        summary = projection["summary.json"]
        rebalances = projection["rebalances.json"]
        latest = rebalances["rebalances"][-1] if rebalances["rebalances"] else None
        count = int(latest["active_count"]) if latest else 0
        variants += count
        index_rows.append(
            {
                "code": definition.code,
                "name": definition.name,
                "game_key": definition.game_key,
                "status": summary["status"],
                "latest_index_value": summary["latest_index_value"],
                "latest_value_date": summary["latest_value_date"],
                "constituent_count": count,
            }
        )
    index_payload = {
        "schema_version": 1,
        "publication_state": "preview_noindex",
        "generated_for": run_date.isoformat(),
        "methodology_version": methodology.methodology_version,
        "indexes": index_rows,
    }
    if _write_json_if_changed(output_root / "collector" / "index.json", index_payload):
        changed.append("collector/index.json")
    return CollectorPreviewExportResult(
        generated_for=run_date.isoformat(),
        indexes=len(index_rows),
        variants=variants,
        changed_files=changed,
    )


def _projection(
    store: ObjectStore,
    definition: IndexDefinition,
    methodology: Methodology,
    run_date: date,
) -> dict[str, dict[str, Any]]:
    version = methodology.methodology_version
    prefix = f"derived/indexes/{version}/private_shadow/{definition.code}"
    source_manifest = _read_json(store, f"{prefix}/manifest.json")
    _validate_identity(source_manifest, definition.code, version, "manifest")
    if source_manifest.get("public_alias_enabled") is not False:
        raise ValueError(f"{definition.code} source manifest enabled a public alias")
    outputs = source_manifest.get("outputs")
    if not isinstance(outputs, dict):
        raise ValueError(f"{definition.code} source manifest has no outputs")

    source_payloads = {
        "summary.json": _manifest_json(store, outputs, f"{prefix}/summary.json"),
        "history.json": _manifest_json(store, outputs, f"{prefix}/history.json"),
        "rebalances.json": _manifest_json(store, outputs, f"{prefix}/rebalances.json"),
    }
    diagnostics_keys = sorted(
        key
        for key in outputs
        if key.startswith(f"derived/diagnostics/{version}/{definition.code}/daily/")
        and key.endswith(".json")
    )
    if not diagnostics_keys:
        raise ValueError(f"{definition.code} source manifest has no daily diagnostics")
    source_diagnostics = _manifest_json(store, outputs, diagnostics_keys[-1])
    for label, payload in (*source_payloads.items(), ("diagnostics.json", source_diagnostics)):
        _validate_identity(payload, definition.code, version, label)
        if payload.get("generated_for") != run_date.isoformat():
            raise ValueError(f"{definition.code} {label} is stale for {run_date.isoformat()}")

    rebalances = deepcopy(source_payloads["rebalances.json"])
    records = rebalances.get("rebalances")
    if not isinstance(records, list):
        raise ValueError(f"{definition.code} rebalances are invalid")
    if records:
        rebalances["generated_for"] = records[-1]["effective_date"]
    diagnostics = _compact_diagnostics(source_diagnostics)
    public_payloads = {
        "summary.json": source_payloads["summary.json"],
        "history.json": source_payloads["history.json"],
        "rebalances.json": rebalances,
        "diagnostics.json": diagnostics,
    }
    manifest_outputs: dict[str, dict[str, object]] = {}
    for filename, payload in public_payloads.items():
        body = _json_bytes(payload)
        logical_key = (
            f"derived/diagnostics/{version}/{definition.code}/public-preview.json"
            if filename == "diagnostics.json"
            else f"{prefix}/{filename}"
        )
        manifest_outputs[logical_key] = {
            "key": logical_key,
            "sha256": sha256_hex(body),
            "bytes": len(body),
        }
    public_payloads["manifest.json"] = {
        "schema_version": 2,
        "series_id": source_manifest["series_id"],
        "index_code": definition.code,
        "methodology_version": version,
        "data_state": "private_shadow",
        "public_alias_enabled": False,
        "publication_state": "preview_noindex",
        "generated_for": run_date.isoformat(),
        "engine_revision": source_manifest["engine_revision"],
        "source_hashes": source_manifest.get("source_hashes", {}),
        "outputs": manifest_outputs,
    }
    return public_payloads


def _compact_diagnostics(source: dict[str, Any]) -> dict[str, Any]:
    rows = source.get("eligibility")
    if not isinstance(rows, list):
        raise ValueError("collector diagnostics eligibility must be a list")
    count = len(rows)
    summary = {
        "count": count,
        "average_quality": (
            sum(float(row["data_quality_score"]) for row in rows) / count if count else None
        ),
        "average_activity_ratio": (
            sum(float(row["activity_ratio"]) for row in rows) / count if count else None
        ),
        "positive_activity_rows": sum(int(row["activity_days"]) > 0 for row in rows),
    }
    return {
        **source,
        "publication_state": "preview_noindex",
        "eligibility": [],
        "summary": summary,
    }


def _manifest_json(store: ObjectStore, outputs: dict[str, Any], key: str) -> dict[str, Any]:
    metadata = outputs.get(key)
    if not isinstance(metadata, dict):
        raise ValueError(f"source manifest does not reference {key}")
    body = store.read_bytes(key)
    if metadata.get("sha256") != sha256_hex(body):
        raise ValueError(f"source manifest checksum mismatch for {key}")
    return _json_object(body, key)


def _read_json(store: ObjectStore, key: str) -> dict[str, Any]:
    if not store.exists(key):
        raise ValueError(f"missing collector source object {key}")
    return _json_object(store.read_bytes(key), key)


def _json_object(body: bytes, label: str) -> dict[str, Any]:
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError(f"collector source {label} must be a JSON object")
    return payload


def _validate_identity(payload: dict[str, Any], code: str, version: str, label: str) -> None:
    expected = {
        "schema_version": 2,
        "index_code": code,
        "methodology_version": version,
        "data_state": "private_shadow",
        "series_id": f"{code}:{version}:private_shadow",
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise ValueError(f"collector {label} has inconsistent {field}")


def _is_enabled_single(definition: IndexDefinition, methodology: Methodology) -> bool:
    if definition.family is None:
        return False
    family = methodology.families[definition.family]
    return family.universe == "singles" and family.calculation_enabled


def _write_json_if_changed(path: Path, payload: object) -> bool:
    body = _json_bytes(payload)
    if path.exists() and path.read_bytes() == body:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return True


def _json_bytes(payload: object) -> bytes:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        + b"\n"
    )
