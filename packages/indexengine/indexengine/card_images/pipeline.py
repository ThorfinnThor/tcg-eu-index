from __future__ import annotations

import gzip
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from core.r2 import sha256_hex
from core.store import ObjectStore

from indexengine.card_images.contracts import PublicCardImage, public_image_from_match
from indexengine.card_images.policy import load_publication_policy
from indexengine.card_images.readiness import magic_identities_from_public_collector
from indexengine.card_images.scryfall import load_scryfall_snapshot, match_magic_identities
from indexengine.collector_preview import repack_existing_collector_preview

DEFAULT_POLICY = Path("packages/indexengine/config/card-images/publication-policy.yaml")


@dataclass(frozen=True)
class MagicImageRunResult:
    dataset_version: str
    snapshot_id: str
    rows: int
    exact_matches: int
    published_images: int
    statuses: dict[str, int]
    changed_keys: tuple[str, ...]


@dataclass(frozen=True)
class MaterializeImagesResult:
    rows: int
    published_images: int
    statuses: dict[str, int]
    changed_files: tuple[str, ...]


def run_magic_image_matching(
    store: ObjectStore,
    collector_root: Path,
    dataset_version: str,
    *,
    snapshot_id: str | None = None,
    policy_path: Path = DEFAULT_POLICY,
) -> MagicImageRunResult:
    policy = load_publication_policy(policy_path)["scryfall"]
    snapshot = load_scryfall_snapshot(store, snapshot_id)
    identities = magic_identities_from_public_collector(
        collector_root,
        source_updated_at=dataset_version,
    )
    matches, assets = match_magic_identities(identities, snapshot, policy)
    records_by_id = {record.provider_card_id: record for record in snapshot.records}
    raw_set_names = _load_raw_set_names(store, snapshot.snapshot_id)
    assets_by_id = assets
    rows: list[dict[str, object]] = []
    statuses: dict[str, int] = {}
    identity_by_key = {identity.source_row_key: identity for identity in identities}
    for match in matches:
        identity = identity_by_key[match.source_row_key]
        public = public_image_from_match(
            match,
            assets_by_id.get(match.asset_id) if match.asset_id else None,
        )
        record = records_by_id.get(match.provider_card_id or "")
        statuses[public.status] = statuses.get(public.status, 0) + 1
        rows.append(
            {
                "source_row_key": identity.source_row_key,
                "cardmarket_product_id": identity.cardmarket_product_id,
                "finish": identity.finish,
                "set_name": (
                    record.set_name
                    if record is not None and record.set_name
                    else raw_set_names.get(match.provider_card_id or "")
                ),
                "collector_number": record.collector_number if record is not None else None,
                "image": public.to_dict(),
            }
        )
    rows.sort(
        key=lambda item: (
            cast(int, item["cardmarket_product_id"]),
            str(item["finish"]),
        )
    )
    published_images = sum(
        count for status, count in statuses.items() if status in {"exact", "manual"}
    )
    match_prefix = f"image-matches/{dataset_version}/magic"
    match_body = _ndjson(asdict(match) for match in matches)
    unresolved_body = _ndjson(
        asdict(match) for match in matches if match.status not in {"exact", "manual"}
    )
    asset_body = _ndjson(asdict(asset) for asset in assets.values())
    public_payload = {
        "schema_version": 1,
        "game": "magic",
        "dataset_version": dataset_version,
        "provider": "scryfall",
        "provider_snapshot_id": snapshot.snapshot_id,
        "matcher_version": "1.0.0",
        "publication_policy": policy.artwork_publication,
        "rows": rows,
    }
    public_body = _json_bytes(public_payload)
    run_manifest = {
        "schema_version": 1,
        "game": "magic",
        "dataset_version": dataset_version,
        "provider_snapshot_id": snapshot.snapshot_id,
        "inputs": {
            "policy_sha256": sha256_hex(policy_path.read_bytes()),
            "snapshot_sha256": snapshot.raw_sha256,
        },
        "outputs": {
            "exact.ndjson": sha256_hex(match_body),
            "unresolved.ndjson": sha256_hex(unresolved_body),
            "assets.ndjson": sha256_hex(asset_body),
            "public-manifest.json": sha256_hex(public_body),
        },
        "counts": {
            "rows": len(matches),
            "exact_matches": sum(match.status == "exact" for match in matches),
            "published_images": published_images,
            "statuses": dict(sorted(statuses.items())),
        },
    }
    bodies = {
        f"{match_prefix}/exact.ndjson": match_body,
        f"{match_prefix}/unresolved.ndjson": unresolved_body,
        f"{match_prefix}/assets.ndjson": asset_body,
        f"{match_prefix}/manifest.json": _json_bytes(run_manifest),
        f"public-image-manifests/{dataset_version}-magic.json": public_body,
        "derived/card-images/magic/public-manifest.json": public_body,
    }
    changed: list[str] = []
    for key, body in bodies.items():
        if store.exists(key) and store.read_bytes(key) == body:
            continue
        content_type = (
            "application/x-ndjson" if key.endswith(".ndjson") else "application/json"
        )
        store.write_bytes(key, body, content_type)
        changed.append(key)
    return MagicImageRunResult(
        dataset_version=dataset_version,
        snapshot_id=snapshot.snapshot_id,
        rows=len(matches),
        exact_matches=sum(match.status == "exact" for match in matches),
        published_images=published_images,
        statuses=dict(sorted(statuses.items())),
        changed_keys=tuple(changed),
    )


def load_public_card_images(
    store: ObjectStore,
    game: str,
) -> dict[tuple[int, str], PublicCardImage]:
    key = f"derived/card-images/{game}/public-manifest.json"
    if not store.exists(key):
        return {}
    payload = json.loads(store.read_bytes(key))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(f"{game} public image manifest has an invalid schema")
    if payload.get("game") != game or not isinstance(payload.get("rows"), list):
        raise ValueError(f"{game} public image manifest has inconsistent identity")
    result: dict[tuple[int, str], PublicCardImage] = {}
    for raw in payload["rows"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("image"), dict):
            raise ValueError(f"{game} public image manifest has an invalid row")
        image = _public_image(raw["image"])
        key_tuple = (int(raw["cardmarket_product_id"]), str(raw["finish"]))
        if key_tuple in result:
            raise ValueError(f"duplicate public image row for {game} {key_tuple}")
        result[key_tuple] = image
    return result


def load_public_card_metadata(
    store: ObjectStore,
    game: str,
) -> dict[tuple[int, str], tuple[str | None, str | None]]:
    key = f"derived/card-images/{game}/public-manifest.json"
    if not store.exists(key):
        return {}
    payload = json.loads(store.read_bytes(key))
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise ValueError(f"{game} public image manifest has no rows")
    result: dict[tuple[int, str], tuple[str | None, str | None]] = {}
    for raw in payload["rows"]:
        if not isinstance(raw, dict):
            raise ValueError(f"{game} public image manifest has an invalid metadata row")
        key_tuple = (int(raw["cardmarket_product_id"]), str(raw["finish"]))
        if key_tuple in result:
            raise ValueError(f"duplicate public metadata row for {game} {key_tuple}")
        result[key_tuple] = (
            raw.get("set_name") if isinstance(raw.get("set_name"), str) else None,
            raw.get("collector_number")
            if isinstance(raw.get("collector_number"), str)
            else None,
        )
    return result


def materialize_magic_images(
    store: ObjectStore,
    source_data_root: Path,
) -> MaterializeImagesResult:
    """Add machine-readable image status to the checked-in static projection."""
    magic_images = load_public_card_images(store, "magic")
    collector_root = source_data_root / "collector"
    magic_metadata = load_public_card_metadata(store, "magic")
    collector_index = json.loads((collector_root / "index.json").read_text())
    indexes = collector_index.get("indexes")
    if not isinstance(indexes, list):
        raise ValueError("collector index has no indexes")
    changed: list[str] = []
    statuses: dict[str, int] = {}
    rows = 0
    published = 0
    for index in sorted(indexes, key=lambda item: str(item["code"])):
        code = str(index["code"])
        if code.endswith("SCOL"):
            continue
        game = str(index["game_key"])
        index_root = collector_root / code
        game_statuses: dict[str, int] = {}
        game_published = 0
        default_status = "blocked_credentials" if game == "riftbound" else "missing_prerequisite"
        for page_path in sorted((index_root / "composition").rglob("*.json")):
            payload = json.loads(page_path.read_text())
            if not isinstance(payload, dict) or not isinstance(
                payload.get("constituents"), list
            ):
                raise ValueError(f"invalid collector composition page {page_path}")
            page_changed = False
            for member in payload["constituents"]:
                if not isinstance(member, dict):
                    raise ValueError(f"invalid collector constituent in {page_path}")
                key = (int(member["cm_product_id"]), str(member["variant_key"]))
                image = (
                    magic_images.get(key, PublicCardImage(status="provider_missing"))
                    if game == "magic"
                    else PublicCardImage(status=default_status)  # type: ignore[arg-type]
                )
                public_payload = image.to_dict()
                if member.get("image") != public_payload:
                    member["image"] = public_payload
                    page_changed = True
                legacy_url = image.normal_url
                legacy_source = image.provider if legacy_url else None
                if member.get("image_url") != legacy_url:
                    member["image_url"] = legacy_url
                    page_changed = True
                if member.get("image_source") != legacy_source:
                    member["image_source"] = legacy_source
                    page_changed = True
                metadata = magic_metadata.get(key)
                if metadata is not None:
                    provider_set_name, provider_collector_number = metadata
                    if provider_set_name and member.get("set_name") != provider_set_name:
                        member["set_name"] = provider_set_name
                        page_changed = True
                    if (
                        provider_collector_number
                        and member.get("collector_number") != provider_collector_number
                    ):
                        member["collector_number"] = provider_collector_number
                        page_changed = True
                statuses[image.status] = statuses.get(image.status, 0) + 1
                game_statuses[image.status] = game_statuses.get(image.status, 0) + 1
                rows += 1
                is_published = (
                    image.status in {"exact", "manual"} and image.normal_url is not None
                )
                published += is_published
                game_published += is_published
            if page_changed:
                page_path.write_bytes(_compact_json_bytes(payload))
                changed.append(str(page_path.relative_to(source_data_root)))
        summary_path = index_root / "summary.json"
        summary = json.loads(summary_path.read_text())
        product_metadata = summary.get("product_metadata")
        if not isinstance(product_metadata, dict):
            raise ValueError(f"{code} collector summary has no product metadata")
        product_metadata["image_count"] = game_published
        product_metadata["image_status_counts"] = dict(sorted(game_statuses.items()))
        summary_body = _compact_json_bytes(summary)
        if summary_path.read_bytes() != summary_body:
            summary_path.write_bytes(summary_body)
            changed.append(str(summary_path.relative_to(source_data_root)))
    repacked = repack_existing_collector_preview(source_data_root)
    changed.extend(repacked.changed_files)
    return MaterializeImagesResult(
        rows=rows,
        published_images=published,
        statuses=dict(sorted(statuses.items())),
        changed_files=tuple(sorted(set(changed))),
    )

def _load_raw_set_names(store: ObjectStore, snapshot_id: str) -> dict[str, str]:
    """Backfill set names for older immutable snapshots without normalized set_name."""
    key = f"provider-snapshots/scryfall/{snapshot_id}/raw.jsonl.gz"
    if not store.exists(key):
        return {}
    result: dict[str, str] = {}
    for line in gzip.decompress(store.read_bytes(key)).splitlines():
        raw = json.loads(line)
        provider_id = raw.get("id")
        set_name = raw.get("set_name")
        if isinstance(provider_id, str) and isinstance(set_name, str) and set_name.strip():
            result[provider_id] = set_name.strip()
    return result


def _public_image(payload: dict[str, Any]) -> PublicCardImage:
    from indexengine.card_images.contracts import CardImageFace, ImageVariant

    def variant(value: object) -> ImageVariant | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("public image variant must be an object")
        return ImageVariant(**value)

    def face(value: object) -> CardImageFace | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("public image face must be an object")
        return CardImageFace(
            face=value["face"],
            thumb=variant(value.get("thumb")),
            normal=variant(value.get("normal")),
            large=variant(value.get("large")),
        )

    return PublicCardImage(
        status=payload["status"],
        provider=payload.get("provider"),
        match_method=payload.get("match_method", "none"),
        language=payload.get("language"),
        language_match=payload.get("language_match"),
        artwork_variant=payload.get("artwork_variant"),
        front=face(payload.get("front")),
        back=face(payload.get("back")),
        verified_at=payload.get("verified_at"),
    )


def _ndjson(records: Iterable[dict[str, Any]]) -> bytes:
    return b"".join(
        json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        + b"\n"
        for record in records
    )


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode() + b"\n"


def _compact_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        + b"\n"
    )
