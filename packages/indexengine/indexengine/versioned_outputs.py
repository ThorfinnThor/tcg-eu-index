from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, cast

from core.r2 import sha256_hex
from core.store import ObjectStore

from indexengine.card_images.contracts import PublicCardImage
from indexengine.collector_calc import (
    CollectorContribution,
    CollectorDailyValue,
    CollectorRebalance,
)
from indexengine.eligibility import CollectorVariantDiagnostic
from indexengine.methodology import IndexDefinition, Methodology, MethodologyConfigError
from indexengine.product_identity import CollectorProductMetadata


@dataclass(frozen=True)
class CollectorOutputBundle:
    index_code: str
    methodology_version: str
    data_state: str
    series_id: str
    objects: dict[str, bytes]


def build_collector_output_bundle(
    definition: IndexDefinition,
    methodology: Methodology,
    run_date: date,
    rebalances: list[CollectorRebalance],
    daily_values: list[CollectorDailyValue],
    contributions: list[CollectorContribution],
    diagnostics: list[CollectorVariantDiagnostic],
    *,
    product_metadata: dict[int, CollectorProductMetadata] | None = None,
    card_images: dict[tuple[int, str], PublicCardImage] | None = None,
    source_hashes: dict[str, str] | None = None,
    engine_revision: str = "local-working-tree",
) -> CollectorOutputBundle:
    """Build a validated, private schema-v2 output bundle for one collector index."""
    index_prefix, diagnostics_prefix, series_id = _output_paths(definition, methodology)
    if methodology.output is None or methodology.output.public_alias_enabled:
        raise MethodologyConfigError("v1.5 collector outputs cannot enable public aliases")
    if any(item.methodology_version != methodology.methodology_version for item in rebalances):
        raise ValueError("collector rebalance methodology version mismatch")
    if any(item.methodology_version != methodology.methodology_version for item in daily_values):
        raise ValueError("collector daily value methodology version mismatch")

    metadata_by_product = product_metadata or {}
    images_by_variant = card_images or {}
    history = [_json_record(item) for item in daily_values]
    rebalances_payload = [
        {
            "effective_date": item.effective_date.isoformat(),
            "selection_as_of": item.selection_as_of.isoformat(),
            "methodology_version": item.methodology_version,
            "selection_snapshot_sha256": item.selection_snapshot_sha256,
            "eligible_count": item.eligible_count,
            "active_count": len(item.constituents),
            "constituents": [
                _constituent_record(member, metadata_by_product, images_by_variant)
                for member in item.constituents
            ],
        }
        for item in rebalances
    ]
    contribution_records = [_json_record(item) for item in contributions]
    diagnostic_records = [_json_record(item) for item in diagnostics]
    status = (
        "preview"
        if any(item.index_value is not None for item in daily_values)
        else "accumulating"
    )
    history_start = next(
        (item.value_date.isoformat() for item in daily_values if item.index_value is not None),
        None,
    )
    latest = daily_values[-1] if daily_values else None
    latest_members = list(rebalances[-1].constituents) if rebalances else []
    metadata_coverage = _metadata_coverage(
        latest_members,
        metadata_by_product,
        images_by_variant,
    )
    summary = {
        "schema_version": 2,
        "series_id": series_id,
        "index_code": definition.code,
        "methodology_version": methodology.methodology_version,
        "data_state": "private_shadow",
        "public_alias_enabled": False,
        "name": definition.name,
        "game_key": definition.game_key,
        "universe": definition.universe,
        "target_size": None,
        "base_value": definition.base_value,
        "status": status,
        "history_start_date": history_start,
        "latest_value_date": latest.value_date.isoformat() if latest else None,
        "latest_index_value": latest.index_value if latest else None,
        "latest_rebalance": latest.rebalance_effective_date.isoformat() if latest else None,
        "product_metadata": metadata_coverage,
        "generated_for": run_date.isoformat(),
    }
    daily_diagnostics = {
        "schema_version": 2,
        "series_id": series_id,
        "index_code": definition.code,
        "methodology_version": methodology.methodology_version,
        "data_state": "private_shadow",
        "generated_for": run_date.isoformat(),
        "daily": history,
        "eligibility": diagnostic_records,
    }
    source = source_hashes or {}
    objects_without_manifest = {
        f"{index_prefix}/summary.json": _json_bytes(summary),
        f"{index_prefix}/history.json": _json_bytes(
            {
                "schema_version": 2,
                "series_id": series_id,
                "index_code": definition.code,
                "methodology_version": methodology.methodology_version,
                "data_state": "private_shadow",
                "generated_for": run_date.isoformat(),
                "records": history,
            }
        ),
        f"{index_prefix}/rebalances.json": _json_bytes(
            {
                "schema_version": 2,
                "series_id": series_id,
                "index_code": definition.code,
                "methodology_version": methodology.methodology_version,
                "data_state": "private_shadow",
                "cadence": "monthly",
                "generated_for": run_date.isoformat(),
                "rebalances": rebalances_payload,
            }
        ),
        f"{index_prefix}/contributions.json": _json_bytes(
            {
                "schema_version": 2,
                "series_id": series_id,
                "index_code": definition.code,
                "methodology_version": methodology.methodology_version,
                "data_state": "private_shadow",
                "generated_for": run_date.isoformat(),
                "records": contribution_records,
            }
        ),
        f"{diagnostics_prefix}/daily/{run_date.isoformat()}.json": _json_bytes(daily_diagnostics),
    }
    manifest_key = f"{index_prefix}/manifest.json"
    manifest = {
        "schema_version": 2,
        "series_id": series_id,
        "index_code": definition.code,
        "methodology_version": methodology.methodology_version,
        "data_state": "private_shadow",
        "public_alias_enabled": False,
        "generated_for": run_date.isoformat(),
        "engine_revision": engine_revision,
        "source_hashes": source,
        "outputs": {
            key: {
                "key": key,
                "sha256": sha256_hex(body),
                "bytes": len(body),
            }
            for key, body in sorted(objects_without_manifest.items())
        },
    }
    objects = {
        **objects_without_manifest,
        manifest_key: _json_bytes(manifest),
    }
    bundle = CollectorOutputBundle(
        index_code=definition.code,
        methodology_version=methodology.methodology_version,
        data_state="private_shadow",
        series_id=series_id,
        objects=objects,
    )
    validate_collector_output_bundle(bundle)
    return bundle


def write_collector_output_bundle(store: ObjectStore, bundle: CollectorOutputBundle) -> list[str]:
    """Write only the already-versioned private bundle objects and report changed keys."""
    validate_collector_output_bundle(bundle)
    changed: list[str] = []
    for key, body in sorted(bundle.objects.items()):
        if store.exists(key) and store.read_bytes(key) == body:
            continue
        content_type = "application/json"
        store.write_bytes(key, body, content_type)
        changed.append(key)
    return changed


def validate_collector_output_bundle(bundle: CollectorOutputBundle) -> None:
    """Validate object paths, checksums, namespace identity, and schema-v2 contracts."""
    if bundle.data_state != "private_shadow":
        raise ValueError("collector output data_state must be private_shadow")
    if not bundle.series_id.endswith(":private_shadow"):
        raise ValueError("collector output series_id must identify private_shadow")
    if not bundle.objects:
        raise ValueError("collector output bundle is empty")
    manifest_key = next(
        (key for key in bundle.objects if key.endswith("/manifest.json")), None
    )
    if manifest_key is None or not manifest_key.startswith("derived/indexes/"):
        raise ValueError("collector output manifest must be under derived/indexes")
    manifest = _read_json(bundle.objects[manifest_key], manifest_key)
    _validate_identity(manifest, bundle, manifest_key)
    if manifest.get("public_alias_enabled") is not False:
        raise ValueError("collector output cannot enable a public alias")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict) or not outputs:
        raise ValueError("collector output manifest has no outputs")
    for key, metadata in outputs.items():
        if key not in bundle.objects or not isinstance(metadata, dict):
            raise ValueError(f"collector output manifest references missing object {key}")
        if metadata.get("key") != key or metadata.get("sha256") != sha256_hex(bundle.objects[key]):
            raise ValueError(f"collector output checksum mismatch for {key}")
        if not key.startswith("derived/indexes/") and not key.startswith("derived/diagnostics/"):
            raise ValueError(f"collector output escaped its private namespaces: {key}")
        if "/private_shadow/" not in key and key.startswith("derived/indexes/"):
            raise ValueError(f"collector index output is not versioned/private: {key}")

    for key, body in bundle.objects.items():
        if key == manifest_key:
            continue
        payload = _read_json(body, key)
        _validate_identity(payload, bundle, key)
        if payload.get("schema_version") != 2:
            raise ValueError(f"collector output {key} is not schema v2")
        if key.endswith("/history.json") and not isinstance(payload.get("records"), list):
            raise ValueError("collector history records must be a list")
        if key.endswith("/rebalances.json") and payload.get("cadence") != "monthly":
            raise ValueError("collector rebalances must use monthly cadence")


def _output_paths(
    definition: IndexDefinition, methodology: Methodology
) -> tuple[str, str, str]:
    output = methodology.output
    if output is None:
        raise MethodologyConfigError("v1.5 collector output requires output configuration")
    values = {
        "methodology_version": methodology.methodology_version,
        "data_state": "private_shadow",
        "index_code": definition.code,
    }
    try:
        index_prefix = output.index_prefix.format(**values)
        diagnostics_prefix = output.diagnostics_prefix.format(**values)
        series_id = output.series_id.format(**values)
    except KeyError as exc:
        raise MethodologyConfigError(f"output template has unknown placeholder {exc}") from exc
    if not index_prefix.startswith("derived/indexes/"):
        raise MethodologyConfigError("collector index prefix must be under derived/indexes")
    if not diagnostics_prefix.startswith("derived/diagnostics/"):
        raise MethodologyConfigError(
            "collector diagnostics prefix must be under derived/diagnostics"
        )
    if ".." in index_prefix.split("/") or ".." in diagnostics_prefix.split("/"):
        raise MethodologyConfigError("collector output paths cannot contain traversal")
    if not series_id.endswith(":private_shadow"):
        raise MethodologyConfigError("collector series id must identify private_shadow")
    return index_prefix, diagnostics_prefix, series_id


def _validate_identity(payload: dict[str, Any], bundle: CollectorOutputBundle, key: str) -> None:
    for field, expected in (
        ("index_code", bundle.index_code),
        ("methodology_version", bundle.methodology_version),
        ("data_state", "private_shadow"),
        ("series_id", bundle.series_id),
    ):
        if payload.get(field) != expected:
            raise ValueError(f"collector output {key} has an inconsistent {field}")


def _json_record(value: Any) -> dict[str, Any]:
    record = asdict(value)
    return cast(dict[str, Any], json.loads(json.dumps(record, default=_json_default)))


def _constituent_record(
    member: Any,
    product_metadata: dict[int, CollectorProductMetadata],
    card_images: dict[tuple[int, str], PublicCardImage],
) -> dict[str, Any]:
    record = _json_record(member)
    image = card_images.get((int(record["cm_product_id"]), str(record["variant_key"])))
    metadata = product_metadata.get(int(record["cm_product_id"]))
    if metadata is None:
        record.update(
            {
                "name": f"Cardmarket product {record['cm_product_id']}",
                "set_name": None,
                "collector_number": None,
                "cm_expansion_id": None,
                "image_url": None,
                "image_source": None,
                "image": (image or PublicCardImage(status="disabled")).to_dict(),
                "tcgplayer_product_url": None,
                "metadata_status": "missing_catalogue_metadata",
            }
        )
    else:
        record.update(_json_record(metadata))
    public_image = image or PublicCardImage(status="disabled")
    record["image"] = public_image.to_dict()
    if public_image.normal_url:
        record["image_url"] = public_image.normal_url
        record["image_source"] = public_image.provider
    return record


def _metadata_coverage(
    members: list[Any],
    product_metadata: dict[int, CollectorProductMetadata],
    card_images: dict[tuple[int, str], PublicCardImage],
) -> dict[str, Any]:
    records = [product_metadata.get(int(item.cm_product_id)) for item in members]
    images = [
        card_images.get((int(item.cm_product_id), str(item.variant_key)))
        for item in members
    ]
    status_counts: dict[str, int] = {}
    for image in images:
        status = image.status if image else "disabled"
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "constituent_count": len(members),
        "named_count": sum(item is not None and bool(item.name) for item in records),
        "set_name_count": sum(item is not None and item.set_name is not None for item in records),
        "collector_number_count": sum(
            item is not None and item.collector_number is not None for item in records
        ),
        "image_count": sum(
            (image is not None and image.normal_url is not None)
            or (image is None and item is not None and item.image_url is not None)
            for item, image in zip(records, images, strict=True)
        ),
        "image_status_counts": dict(sorted(status_counts.items())),
    }


def _json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        default=_json_default,
    ).encode() + b"\n"


def _json_default(value: object) -> str:
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _read_json(body: bytes, key: str) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"collector output {key} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"collector output {key} must be an object")
    return payload
