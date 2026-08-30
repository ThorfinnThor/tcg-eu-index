from __future__ import annotations

import gzip
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import polars as pl
from core.r2 import sha256_hex
from core.store import ObjectStore

from indexengine.card_images.catalogs import (
    MATCHER_VERSION,
    CatalogCardRecord,
    load_catalog_snapshot,
    match_catalog_identities,
)
from indexengine.card_images.contracts import (
    CanonicalCardIdentity,
    CardImageMatch,
    PublicCardImage,
    public_image_from_match,
)
from indexengine.card_images.policy import load_publication_policy
from indexengine.card_images.readiness import (
    identities_from_public_collector,
    magic_identities_from_public_collector,
)
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


@dataclass(frozen=True)
class CatalogImageRunResult:
    game: str
    provider: str
    dataset_version: str
    snapshot_id: str
    rows: int
    exact_matches: int
    published_images: int
    statuses: dict[str, int]
    changed_keys: tuple[str, ...]


def run_catalog_image_matching(
    store: ObjectStore,
    collector_root: Path,
    dataset_version: str,
    *,
    game: str,
    code: str,
    provider: str,
    snapshot_id: str | None = None,
    policy_path: Path = DEFAULT_POLICY,
) -> CatalogImageRunResult:
    policy = load_publication_policy(policy_path)[provider]
    snapshot = load_catalog_snapshot(store, provider, snapshot_id)
    if snapshot.game != game or game not in policy.games:
        raise ValueError(f"{provider} snapshot/policy does not support {game}")
    identities = identities_from_public_collector(
        collector_root,
        code,
        game,
        source_updated_at=dataset_version,
    )
    matches, assets = match_catalog_identities(
        identities,
        snapshot,
        policy,
        store=store,
        marketplace_set_names=_load_marketplace_set_names(store, game),
    )
    records_by_key: dict[tuple[str, str | None], list[CatalogCardRecord]] = defaultdict(list)
    for record in snapshot.records:
        records_by_key[(record.provider_card_id, record.provider_art_id)].append(record)
    identity_by_key = {identity.source_row_key: identity for identity in identities}
    rows: list[dict[str, object]] = []
    statuses: dict[str, int] = {}
    for match in matches:
        identity = identity_by_key[match.source_row_key]
        public = public_image_from_match(
            match,
            assets.get(match.asset_id) if match.asset_id else None,
        )
        matched_record = _matched_catalog_record(
            records_by_key.get((match.provider_card_id or "", match.provider_art_id), []),
            match,
            identity,
        )
        statuses[public.status] = statuses.get(public.status, 0) + 1
        rows.append(
            {
                "source_row_key": identity.source_row_key,
                "cardmarket_product_id": identity.cardmarket_product_id,
                "finish": identity.finish,
                "set_name": matched_record.set_name if matched_record is not None else None,
                "set_code": matched_record.set_code if matched_record is not None else None,
                "collector_number": (
                    matched_record.collector_number if matched_record is not None else None
                ),
                "provider_card_id": (
                    matched_record.provider_card_id if matched_record is not None else None
                ),
                "image": public.to_dict(),
            }
        )
    rows.sort(key=lambda item: (cast(int, item["cardmarket_product_id"]), str(item["finish"])))
    published = sum(count for status, count in statuses.items() if status in {"exact", "manual"})
    prefix = f"image-matches/{dataset_version}/{game}"
    public_payload = {
        "schema_version": 1,
        "game": game,
        "dataset_version": dataset_version,
        "provider": provider,
        "provider_snapshot_id": snapshot.snapshot_id,
        "matcher_version": MATCHER_VERSION,
        "publication_policy": policy.artwork_publication,
        "rows": rows,
    }
    public_body = _json_bytes(public_payload)
    bodies = {
        f"{prefix}/exact.ndjson": _ndjson(asdict(match) for match in matches),
        f"{prefix}/unresolved.ndjson": _ndjson(
            asdict(match) for match in matches if match.status not in {"exact", "manual"}
        ),
        f"{prefix}/assets.ndjson": _ndjson(asdict(asset) for asset in assets.values()),
        f"public-image-manifests/{dataset_version}-{game}.json": public_body,
        f"derived/card-images/{game}/public-manifest.json": public_body,
    }
    changed: list[str] = []
    for key, body in bodies.items():
        if store.exists(key) and store.read_bytes(key) == body:
            continue
        store.write_bytes(
            key,
            body,
            "application/x-ndjson" if key.endswith(".ndjson") else "application/json",
        )
        changed.append(key)
    return CatalogImageRunResult(
        game=game,
        provider=provider,
        dataset_version=dataset_version,
        snapshot_id=snapshot.snapshot_id,
        rows=len(matches),
        exact_matches=sum(match.status == "exact" for match in matches),
        published_images=published,
        statuses=dict(sorted(statuses.items())),
        changed_keys=tuple(changed),
    )


def _load_marketplace_set_names(
    store: ObjectStore,
    game: str,
) -> dict[int, tuple[str, ...]]:
    """Load full Cardmarket singles baskets for deterministic set inference."""
    key = f"derived/catalogue/{game}/products.parquet"
    if not store.exists(key):
        return {}
    products = pl.read_parquet(BytesIO(store.read_bytes(key)))
    required = ("cm_expansion_id", "product_kind", "name", "display_name")
    if not set(required).issubset(products.columns):
        raise ValueError(f"normalized Cardmarket catalogue {key} lacks set-signature columns")
    names: dict[int, set[str]] = defaultdict(set)
    for row in products.select(required).iter_rows(named=True):
        if row["product_kind"] != "single" or row["cm_expansion_id"] is None:
            continue
        name = row["display_name"] or row["name"]
        if name is not None and str(name).strip():
            names[int(row["cm_expansion_id"])].add(str(name))
    return {expansion_id: tuple(sorted(values)) for expansion_id, values in names.items()}


def _matched_catalog_record(
    records: list[CatalogCardRecord],
    match: CardImageMatch,
    identity: CanonicalCardIdentity,
) -> CatalogCardRecord | None:
    """Recover the exact printing row without guessing among provider reprints."""
    if len(records) == 1:
        return records[0]
    candidates = records
    if identity.collector_number_canonical:
        number = identity.collector_number_canonical.casefold()
        numbered = [
            record
            for record in candidates
            if record.collector_number and record.collector_number.casefold() == number
        ]
        if numbered:
            candidates = numbered
    evidence = {
        key: value
        for item in match.evidence
        if "=" in item
        for key, value in (item.split("=", 1),)
    }
    provider_set_name = evidence.get("provider_set_name")
    provider_set_code = evidence.get("provider_set_code")
    if provider_set_name is not None:
        in_set = [record for record in candidates if (record.set_name or "") == provider_set_name]
        if provider_set_code is not None:
            in_set = [
                record
                for record in in_set
                if (record.set_code or "") == provider_set_code
                or (match.provider == "ygoprodeck" and provider_set_code == "")
            ]
        if in_set:
            candidates = in_set
    return candidates[0] if len(candidates) == 1 else None


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
        content_type = "application/x-ndjson" if key.endswith(".ndjson") else "application/json"
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
) -> dict[tuple[int, str], tuple[str | None, str | None, str | None]]:
    key = f"derived/card-images/{game}/public-manifest.json"
    if not store.exists(key):
        return {}
    payload = json.loads(store.read_bytes(key))
    if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
        raise ValueError(f"{game} public image manifest has no rows")
    result: dict[tuple[int, str], tuple[str | None, str | None, str | None]] = {}
    for raw in payload["rows"]:
        if not isinstance(raw, dict):
            raise ValueError(f"{game} public image manifest has an invalid metadata row")
        key_tuple = (int(raw["cardmarket_product_id"]), str(raw["finish"]))
        if key_tuple in result:
            raise ValueError(f"duplicate public metadata row for {game} {key_tuple}")
        result[key_tuple] = (
            raw.get("set_name") if isinstance(raw.get("set_name"), str) else None,
            raw.get("set_code") if isinstance(raw.get("set_code"), str) else None,
            raw.get("collector_number") if isinstance(raw.get("collector_number"), str) else None,
        )
    return result


def materialize_magic_images(
    store: ObjectStore,
    source_data_root: Path,
) -> MaterializeImagesResult:
    """Add machine-readable image status to the checked-in static projection."""
    collector_root = source_data_root / "collector"
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
        game_images = load_public_card_images(store, game)
        game_metadata = load_public_card_metadata(store, game)
        index_root = collector_root / code
        game_statuses: dict[str, int] = {}
        latest_statuses: dict[str, int] = {}
        latest_rows = 0
        latest_named = 0
        latest_set_names = 0
        latest_collector_numbers = 0
        latest_published = 0
        composition_index = json.loads((index_root / "composition.json").read_text())
        composition_rebalances = composition_index.get("rebalances")
        if not isinstance(composition_rebalances, list) or not composition_rebalances:
            raise ValueError(f"{code} collector composition has no rebalances")
        latest_effective_date = max(
            str(rebalance["effective_date"])
            for rebalance in composition_rebalances
            if isinstance(rebalance, dict) and "effective_date" in rebalance
        )
        credential_games = {"onepiece", "dragonballsuper"}
        default_status = (
            "blocked_credentials" if game in credential_games else "missing_prerequisite"
        )
        for page_path in sorted((index_root / "composition").rglob("*.json")):
            payload = json.loads(page_path.read_text())
            if not isinstance(payload, dict) or not isinstance(payload.get("constituents"), list):
                raise ValueError(f"invalid collector composition page {page_path}")
            is_latest_page = str(payload.get("effective_date")) == latest_effective_date
            page_changed = False
            for member in payload["constituents"]:
                if not isinstance(member, dict):
                    raise ValueError(f"invalid collector constituent in {page_path}")
                key = (int(member["cm_product_id"]), str(member["variant_key"]))
                existing_image = member.get("image")
                if (
                    not game_images
                    and game not in credential_games
                    and isinstance(existing_image, dict)
                ):
                    image = _public_image(existing_image)
                else:
                    image = game_images.get(
                        key,
                        PublicCardImage(
                            status=("provider_missing" if game_images else default_status)  # type: ignore[arg-type]
                        ),
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
                metadata = game_metadata.get(key)
                if metadata is not None:
                    provider_set_name, provider_set_code, provider_collector_number = metadata
                    if provider_set_name and member.get("set_name") != provider_set_name:
                        member["set_name"] = provider_set_name
                        page_changed = True
                    if provider_set_code and member.get("set_code") != provider_set_code:
                        member["set_code"] = provider_set_code
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
                is_published = image.status in {"exact", "manual"} and image.normal_url is not None
                published += is_published
                if is_latest_page:
                    latest_rows += 1
                    latest_named += bool(member.get("name"))
                    latest_set_names += bool(member.get("set_name"))
                    latest_collector_numbers += bool(member.get("collector_number"))
                    latest_published += is_published
                    latest_statuses[image.status] = latest_statuses.get(image.status, 0) + 1
            if page_changed:
                page_path.write_bytes(_compact_json_bytes(payload))
                changed.append(str(page_path.relative_to(source_data_root)))
        summary_path = index_root / "summary.json"
        summary = json.loads(summary_path.read_text())
        product_metadata = summary.get("product_metadata")
        if not isinstance(product_metadata, dict):
            raise ValueError(f"{code} collector summary has no product metadata")
        expected_rows = int(product_metadata.get("constituent_count", -1))
        if latest_rows != expected_rows:
            raise ValueError(
                f"{code} latest composition has {latest_rows} rows, expected {expected_rows}"
            )
        product_metadata["named_count"] = latest_named
        product_metadata["set_name_count"] = latest_set_names
        product_metadata["collector_number_count"] = latest_collector_numbers
        product_metadata["image_count"] = latest_published
        product_metadata["image_status_counts"] = dict(sorted(latest_statuses.items()))
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
        return ImageVariant(
            url=str(value["url"]),
            width=int(value["width"]) if value.get("width") is not None else None,
            height=int(value["height"]) if value.get("height") is not None else None,
            mime_type=(str(value["mime_type"]) if value.get("mime_type") is not None else None),
            storage_mode=value.get("storage_mode", "remote"),
            r2_key=str(value["r2_key"]) if value.get("r2_key") is not None else None,
            content_sha256=(
                str(value["content_sha256"]) if value.get("content_sha256") is not None else None
            ),
        )

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
