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
from indexengine.methodology import IndexDefinition, Methodology
from indexengine.public_export import build_public_membership_contract
from indexengine.selection import Constituent, RemovedConstituent


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode() + b"\n"


def _read_json(store: ObjectStore, key: str) -> dict[str, Any] | None:
    if not store.exists(key):
        return None
    try:
        payload = json.loads(store.read_bytes(key))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _audit_item(audit: dict[str, Any], code: str) -> dict[str, Any] | None:
    indexes = audit.get("cutover", {}).get("indexes", [])
    return next(
        (
            item
            for item in indexes
            if isinstance(item, dict) and item.get("index_code") == code
        ),
        None,
    )


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


def _index_review(
    store: ObjectStore,
    run_date: date,
    methodology: Methodology,
    definition: IndexDefinition,
    audit: dict[str, Any],
) -> dict[str, object]:
    prefix = f"derived/indexes/{definition.code}"
    quality_key = f"{prefix}/quality/{run_date.isoformat()}.json"
    quality = _read_json(store, quality_key)
    manifest = _read_json(store, f"{prefix}/manifest.json")
    audit_item = _audit_item(audit, definition.code)
    available = quality.get("available_archive_days") if quality else None
    required = quality.get("required_lookback_days") if quality else None
    selected = quality.get("selected_constituents") if quality else None
    target = quality.get("target_size") if quality else definition.target_size
    gates = {
        "archive_audit_passed": audit.get("status") == "pass",
        "audit_index_ready": bool(
            audit_item and audit_item.get("state") == "eligible_for_human_review"
        ),
        "quality_receipt_available": quality is not None,
        "quality_status_ready": bool(quality and quality.get("status") == "ready"),
        "lookback_complete": bool(
            isinstance(available, int)
            and isinstance(required, int)
            and available >= required
        ),
        "target_size_filled": bool(
            isinstance(selected, int) and isinstance(target, int) and selected == target
        ),
        "language_scope_resolved": bool(
            quality
            and quality.get("language_scope_status")
            == definition.language_scope_status
            and definition.language_scope_status != "pending_source_field"
        ),
        "calculation_manifest_matches": bool(
            manifest
            and manifest.get("generated_for") == run_date.isoformat()
            and manifest.get("status") == "ready"
            and manifest.get("methodology_version") == methodology.methodology_version
        ),
        "calculation_outputs_verified": _outputs_verified(store, manifest),
    }
    blockers = [name for name, passed in gates.items() if not passed]
    return {
        "code": definition.code,
        "state": "eligible_for_human_review" if not blockers else "blocked",
        "qualityKey": quality_key if quality else None,
        "availableArchiveDays": available,
        "requiredLookbackDays": required,
        "selectedConstituents": selected,
        "targetSize": target,
        "languageScope": definition.language_scope,
        "gates": gates,
        "blockers": blockers,
    }


def build_cutover_review(
    store: ObjectStore,
    run_date: date,
    audit: dict[str, Any],
    methodology: Methodology,
) -> dict[str, object]:
    indexes = [
        _index_review(store, run_date, methodology, definition, audit)
        for definition in methodology.indexes
    ]
    eligible = all(item["state"] == "eligible_for_human_review" for item in indexes)
    return {
        "schemaVersion": 1,
        "generatedFor": run_date.isoformat(),
        "methodologyVersion": methodology.methodology_version,
        "state": "eligible_for_human_review" if eligible else "blocked",
        "candidateGenerated": False,
        "publicationPerformed": False,
        "humanSignoffRequired": True,
        "indexes": indexes,
    }


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


def _assert_safe_output_root(output_root: Path) -> None:
    resolved = output_root.resolve()
    protected = [
        Path("apps/web/source-data").resolve(),
        Path("apps/web/public/data").resolve(),
    ]
    if any(resolved == item or item in resolved.parents for item in protected):
        raise ValueError("cutover candidates must not be written into public source directories")
    if resolved.exists() and any(resolved.iterdir()):
        raise ValueError("cutover output directory must be empty")


def _write_candidate_file(
    output_root: Path,
    relative_path: str,
    payload: object,
    files: list[dict[str, object]],
) -> None:
    body = _json_bytes(payload)
    destination = output_root / "candidate" / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(body)
    files.append(
        {
            "path": f"candidate/{relative_path}",
            "bytes": len(body),
            "sha256": sha256_hex(body),
        }
    )


def _generate_candidate(
    store: ObjectStore,
    run_date: date,
    methodology: Methodology,
    output_root: Path,
) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    for definition in methodology.indexes:
        prefix = f"derived/indexes/{definition.code}"
        rebalance_payload = _read_json(store, f"{prefix}/rebalances.json")
        analytics = _read_json(store, f"{prefix}/analytics.json")
        if rebalance_payload is None or analytics is None:
            raise ValueError(f"missing candidate inputs for {definition.code}")
        products = pl.read_parquet(
            BytesIO(store.read_bytes(f"derived/catalogue/{definition.game_key}/products.parquet"))
        )
        sets = pl.read_parquet(
            BytesIO(store.read_bytes(f"derived/catalogue/{definition.game_key}/sets.parquet"))
        )
        membership = build_public_membership_contract(
            definition.code,
            run_date.isoformat(),
            _rebalances(rebalance_payload),
            products,
            sets,
            data_state="published",
        )
        history = pl.read_parquet(
            BytesIO(store.read_bytes(f"{prefix}/daily-values.parquet"))
        ).to_dicts()
        latest_analytics = (analytics.get("records") or [{}])[-1]
        metadata = {
            "code": definition.code,
            "status": "published",
            "history_start_kind": "published",
            "history_start_date": history[0]["value_date"] if history else None,
            "methodology_version": methodology.methodology_version,
            "breadth": latest_analytics.get("breadth_7d"),
            "volatility_30d": latest_analytics.get("volatility_30d"),
        }
        base = f"indexes/{definition.code}"
        _write_candidate_file(output_root, f"{base}/history.json", history, files)
        _write_candidate_file(
            output_root, f"{base}/constituents.json", membership["constituents"], files
        )
        _write_candidate_file(
            output_root, f"{base}/rebalances.json", membership["rebalances"], files
        )
        _write_candidate_file(output_root, f"{base}/analytics.json", analytics, files)
        _write_candidate_file(output_root, f"{base}/metadata.json", metadata, files)
    return files


def prepare_cutover_candidate(
    store: ObjectStore,
    run_date: date,
    audit: dict[str, Any],
    output_root: Path,
    methodology_path: Path = Path("packages/indexengine/methodology.yaml"),
) -> dict[str, object]:
    _assert_safe_output_root(output_root)
    methodology = Methodology.load(methodology_path)
    review = build_cutover_review(store, run_date, audit, methodology)
    output_root.mkdir(parents=True, exist_ok=True)
    if review["state"] == "eligible_for_human_review":
        files = _generate_candidate(store, run_date, methodology, output_root)
        candidate_manifest = {
            "schemaVersion": 1,
            "generatedFor": run_date.isoformat(),
            "methodologyVersion": methodology.methodology_version,
            "publicationPerformed": False,
            "humanSignoffRequired": True,
            "files": files,
        }
        manifest_body = _json_bytes(candidate_manifest)
        manifest_path = output_root / "candidate" / "manifest.json"
        manifest_path.write_bytes(manifest_body)
        review["candidateGenerated"] = True
        review["candidateManifestSha256"] = sha256_hex(manifest_body)
    (output_root / "cutover-review.json").write_bytes(_json_bytes(review))
    return review
