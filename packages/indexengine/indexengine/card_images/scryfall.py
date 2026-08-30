from __future__ import annotations

import gzip
import hashlib
import json
import re
import time
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from io import BytesIO
from typing import Any, Protocol, cast

import requests
from core.r2 import gzip_body, sha256_hex
from core.store import ObjectStore

from indexengine.card_images.contracts import (
    CanonicalCardIdentity,
    CardImageAsset,
    CardImageFace,
    CardImageMatch,
    ImageVariant,
    normalize_card_name,
)
from indexengine.card_images.policy import ProviderPolicy

SCRYFALL_BULK_URL = "https://api.scryfall.com/bulk-data"
SCRYFALL_IMAGE_HOST = "cards.scryfall.io"
ADAPTER_VERSION = "1.0.0"
MATCHER_VERSION = "1.0.0"
MINIMUM_MAGIC_RECORDS = 20_000


class HttpResponse(Protocol):
    content: bytes
    headers: dict[str, str]
    status_code: int

    def raise_for_status(self) -> None: ...


class HttpClient(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: int,
    ) -> HttpResponse: ...


@dataclass(frozen=True)
class ScryfallCardRecord:
    provider: str
    game: str
    provider_card_id: str
    cardmarket_id: int
    name_raw: str
    name_normalized: str
    set_code: str | None
    collector_number: str | None
    language: str | None
    layout: str | None
    faces: tuple[CardImageFace, ...]
    raw_record_hash: str


@dataclass(frozen=True)
class ScryfallSnapshot:
    snapshot_id: str
    fetched_at: str
    source_url: str
    source_updated_at: str
    source_etag: str | None
    raw_sha256: str
    records: tuple[ScryfallCardRecord, ...]


@dataclass(frozen=True)
class ScryfallSyncResult:
    snapshot_id: str
    record_count: int
    changed_keys: tuple[str, ...]


def sync_scryfall_snapshot(
    store: ObjectStore,
    *,
    client: HttpClient | None = None,
    user_agent: str = "tcg-eu-index/0.1 card-images",
    now: datetime | None = None,
) -> ScryfallSyncResult:
    """Fetch and atomically activate a validated Scryfall bulk snapshot."""
    session = cast(HttpClient, client or requests.Session())
    headers = {"Accept": "application/json", "User-Agent": user_agent}
    listing_response = _get_with_retry(
        session,
        SCRYFALL_BULK_URL,
        headers=headers,
        timeout=20,
    )
    listing = json.loads(listing_response.content)
    bulk = _default_cards_entry(listing)
    source_url = _bulk_download_url(bulk)
    source_updated_at = str(bulk["updated_at"])
    snapshot_id = _snapshot_id(source_updated_at)
    prefix = f"provider-snapshots/scryfall/{snapshot_id}"
    manifest_key = f"{prefix}/manifest.json"
    latest_key = "provider-snapshots/scryfall/latest.json"
    if store.exists(manifest_key):
        manifest = _json_object(store.read_bytes(manifest_key), manifest_key)
        return ScryfallSyncResult(snapshot_id, int(manifest["record_count"]), ())

    response = _get_with_retry(session, source_url, headers=headers, timeout=180)
    raw = response.content
    records = parse_scryfall_bulk(raw, source_url)
    if len(records) < MINIMUM_MAGIC_RECORDS:
        raise ValueError(
            f"Scryfall snapshot has only {len(records)} Cardmarket-linked records"
        )
    fetched_at = (now or datetime.now(UTC)).isoformat()
    snapshot = ScryfallSnapshot(
        snapshot_id=snapshot_id,
        fetched_at=fetched_at,
        source_url=source_url,
        source_updated_at=source_updated_at,
        source_etag=_header(response.headers, "etag"),
        raw_sha256=sha256_hex(raw),
        records=tuple(records),
    )
    normalized = normalized_snapshot_bytes(snapshot)
    manifest = {
        "schema_version": 1,
        "snapshot_id": snapshot.snapshot_id,
        "provider": "scryfall",
        "fetched_at": snapshot.fetched_at,
        "source_url": snapshot.source_url,
        "source_updated_at": snapshot.source_updated_at,
        "source_etag": snapshot.source_etag,
        "raw_sha256": snapshot.raw_sha256,
        "normalized_sha256": sha256_hex(normalized),
        "record_count": len(snapshot.records),
        "adapter_version": ADAPTER_VERSION,
    }
    bodies = {
        f"{prefix}/raw.jsonl.gz": raw,
        f"{prefix}/normalized.ndjson.gz": gzip_body(normalized),
        manifest_key: _json_bytes(manifest),
    }
    changed: list[str] = []
    for key, body in bodies.items():
        if store.exists(key):
            if store.read_bytes(key) != body:
                raise ValueError(f"immutable Scryfall snapshot conflict at {key}")
            continue
        content_type = "application/gzip" if key.endswith(".gz") else "application/json"
        store.write_bytes(key, body, content_type)
        changed.append(key)
    latest = _json_bytes(
        {
            "schema_version": 1,
            "provider": "scryfall",
            "snapshot_id": snapshot.snapshot_id,
            "manifest_key": manifest_key,
            "activated_at": fetched_at,
        }
    )
    if not store.exists(latest_key) or store.read_bytes(latest_key) != latest:
        store.write_bytes(latest_key, latest, "application/json")
        changed.append(latest_key)
    return ScryfallSyncResult(snapshot_id, len(records), tuple(changed))


def load_scryfall_snapshot(store: ObjectStore, snapshot_id: str | None = None) -> ScryfallSnapshot:
    if snapshot_id is None:
        latest = _json_object(
            store.read_bytes("provider-snapshots/scryfall/latest.json"),
            "Scryfall latest pointer",
        )
        snapshot_id = str(latest["snapshot_id"])
    prefix = f"provider-snapshots/scryfall/{snapshot_id}"
    manifest = _json_object(store.read_bytes(f"{prefix}/manifest.json"), "Scryfall manifest")
    normalized_gzip = store.read_bytes(f"{prefix}/normalized.ndjson.gz")
    normalized = gzip.decompress(normalized_gzip)
    if sha256_hex(normalized) != manifest["normalized_sha256"]:
        raise ValueError("Scryfall normalized snapshot checksum mismatch")
    records = tuple(
        _record_from_dict(json.loads(line))
        for line in normalized.splitlines()
        if line.strip()
    )
    if len(records) != int(manifest["record_count"]):
        raise ValueError("Scryfall normalized snapshot record count mismatch")
    return ScryfallSnapshot(
        snapshot_id=str(manifest["snapshot_id"]),
        fetched_at=str(manifest["fetched_at"]),
        source_url=str(manifest["source_url"]),
        source_updated_at=str(manifest["source_updated_at"]),
        source_etag=_optional_text(manifest.get("source_etag")),
        raw_sha256=str(manifest["raw_sha256"]),
        records=records,
    )


def parse_scryfall_bulk(raw: bytes, source_url: str) -> list[ScryfallCardRecord]:
    records: list[ScryfallCardRecord] = []
    for card in _iter_bulk_records(raw, source_url):
        cardmarket_id = card.get("cardmarket_id")
        if not isinstance(cardmarket_id, int) or cardmarket_id <= 0:
            continue
        record = _normalize_scryfall_card(card)
        if record is not None:
            records.append(record)
    records.sort(key=lambda item: (item.cardmarket_id, item.provider_card_id))
    return records


def normalized_snapshot_bytes(snapshot: ScryfallSnapshot) -> bytes:
    lines = [
        json.dumps(asdict(record), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        for record in snapshot.records
    ]
    return ("\n".join(lines) + "\n").encode()


def match_magic_identities(
    identities: list[CanonicalCardIdentity],
    snapshot: ScryfallSnapshot,
    policy: ProviderPolicy,
    *,
    matched_at: str | None = None,
) -> tuple[list[CardImageMatch], dict[str, CardImageAsset]]:
    by_cardmarket_id: dict[int, list[ScryfallCardRecord]] = defaultdict(list)
    for record in snapshot.records:
        by_cardmarket_id[record.cardmarket_id].append(record)
    timestamp = matched_at or snapshot.fetched_at
    matches: list[CardImageMatch] = []
    assets: dict[str, CardImageAsset] = {}
    for identity in identities:
        if identity.game != "magic":
            matches.append(_unresolved(identity, "disabled", "GAME_NOT_SUPPORTED", timestamp))
            continue
        candidates = by_cardmarket_id.get(identity.cardmarket_product_id, [])
        if len(candidates) > 1:
            candidates = _disambiguate(identity, candidates)
        if not candidates:
            matches.append(
                _unresolved(identity, "provider_missing", "CM_ID_NOT_FOUND", timestamp)
            )
            continue
        if len(candidates) != 1:
            matches.append(
                _unresolved(
                    identity,
                    "ambiguous",
                    "MULTIPLE_CM_ID_CANDIDATES",
                    timestamp,
                    candidate_count=len(candidates),
                )
            )
            continue
        candidate = candidates[0]
        asset = _asset(candidate, snapshot, policy, timestamp)
        assets[asset.asset_id] = asset
        matches.append(
            CardImageMatch(
                schema_version=1,
                source_row_key=identity.source_row_key,
                asset_id=asset.asset_id,
                provider="scryfall",
                provider_card_id=candidate.provider_card_id,
                provider_art_id=None,
                status="exact",
                match_method="direct_marketplace_id",
                score=100,
                candidate_count=1,
                evidence=(f"cardmarket_id={identity.cardmarket_product_id}",),
                reason_code=None,
                matched_at=timestamp,
                matcher_version=MATCHER_VERSION,
                provider_snapshot_id=snapshot.snapshot_id,
            )
        )
    matches.sort(key=lambda item: item.source_row_key)
    return matches, dict(sorted(assets.items()))


def _asset(
    record: ScryfallCardRecord,
    snapshot: ScryfallSnapshot,
    policy: ProviderPolicy,
    timestamp: str,
) -> CardImageAsset:
    asset_id = hashlib.sha256(
        f"scryfall\x1f{record.provider_card_id}\x1fbase".encode()
    ).hexdigest()
    return CardImageAsset(
        schema_version=1,
        asset_id=asset_id,
        game="magic",
        provider="scryfall",
        provider_card_id=record.provider_card_id,
        provider_art_id=None,
        provider_variant_raw=record.layout,
        language=record.language,
        artwork_variant="base",
        faces=record.faces,
        provider_record_hash=record.raw_record_hash,
        provider_snapshot_id=snapshot.snapshot_id,
        first_seen_at=timestamp,
        last_verified_at=timestamp,
        legal_status=policy.legal_status,
    )


def _unresolved(
    identity: CanonicalCardIdentity,
    status: str,
    reason: str,
    timestamp: str,
    *,
    candidate_count: int = 0,
) -> CardImageMatch:
    return CardImageMatch(
        schema_version=1,
        source_row_key=identity.source_row_key,
        asset_id=None,
        provider="scryfall" if status != "disabled" else None,
        provider_card_id=None,
        provider_art_id=None,
        status=status,  # type: ignore[arg-type]
        match_method="none",
        score=None,
        candidate_count=candidate_count,
        evidence=(),
        reason_code=reason,
        matched_at=timestamp,
        matcher_version=MATCHER_VERSION,
        provider_snapshot_id=None,
    )


def _disambiguate(
    identity: CanonicalCardIdentity,
    candidates: list[ScryfallCardRecord],
) -> list[ScryfallCardRecord]:
    reduced = candidates
    if identity.set_code_canonical:
        reduced = [
            item
            for item in reduced
            if item.set_code
            and item.set_code.casefold() == identity.set_code_canonical.casefold()
        ]
    if len(reduced) > 1 and identity.collector_number_canonical:
        reduced = [
            item
            for item in reduced
            if item.collector_number == identity.collector_number_canonical
        ]
    if len(reduced) > 1:
        named = [item for item in reduced if item.name_normalized == identity.name_normalized]
        if named:
            reduced = named
    return reduced


def _normalize_scryfall_card(card: dict[str, Any]) -> ScryfallCardRecord | None:
    provider_id = card.get("id")
    name = card.get("name")
    if not isinstance(provider_id, str) or not isinstance(name, str):
        return None
    faces = _image_faces(card)
    if not faces:
        return None
    raw_hash = sha256_hex(
        json.dumps(card, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    )
    return ScryfallCardRecord(
        provider="scryfall",
        game="magic",
        provider_card_id=provider_id,
        cardmarket_id=int(card["cardmarket_id"]),
        name_raw=name,
        name_normalized=normalize_card_name(name),
        set_code=_optional_text(card.get("set")),
        collector_number=_optional_text(card.get("collector_number")),
        language=_optional_text(card.get("lang")),
        layout=_optional_text(card.get("layout")),
        faces=faces,
        raw_record_hash=raw_hash,
    )


def _image_faces(card: dict[str, Any]) -> tuple[CardImageFace, ...]:
    image_uris = card.get("image_uris")
    if isinstance(image_uris, dict):
        face = _face("front", image_uris)
        return (face,) if face.normal else ()
    raw_faces = card.get("card_faces")
    if not isinstance(raw_faces, list):
        return ()
    result: list[CardImageFace] = []
    for index, raw_face in enumerate(raw_faces):
        if not isinstance(raw_face, dict) or not isinstance(raw_face.get("image_uris"), dict):
            continue
        face = _face("front" if index == 0 else "back", raw_face["image_uris"])
        if face.normal:
            result.append(face)
    return tuple(result)


def _face(face: str, uris: dict[str, Any]) -> CardImageFace:
    return CardImageFace(
        face=face,  # type: ignore[arg-type]
        thumb=_variant(uris.get("small"), 146, 204),
        normal=_variant(uris.get("normal"), 488, 680),
        large=_variant(uris.get("large"), 672, 936),
    )


def _variant(value: object, width: int, height: int) -> ImageVariant | None:
    url = _optional_text(value)
    if url is None:
        return None
    if not url.startswith(f"https://{SCRYFALL_IMAGE_HOST}/"):
        raise ValueError("Scryfall image escaped the approved host")
    return ImageVariant(url, width, height, "image/jpeg")


def _iter_bulk_records(raw: bytes, source_url: str) -> Iterator[dict[str, Any]]:
    if source_url.endswith(".gz") or raw.startswith(b"\x1f\x8b"):
        with gzip.GzipFile(fileobj=BytesIO(raw)) as stream:
            for line in stream:
                if line.strip():
                    payload = json.loads(line)
                    if isinstance(payload, dict):
                        yield payload
        return
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("Scryfall bulk payload must be a JSON array or gzipped JSONL")
    yield from (item for item in payload if isinstance(item, dict))


def _default_cards_entry(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Scryfall bulk listing has an invalid shape")
    matches = [
        item
        for item in payload["data"]
        if isinstance(item, dict) and item.get("type") == "default_cards"
    ]
    if len(matches) != 1:
        raise ValueError("Scryfall bulk listing has no unique default_cards entry")
    return matches[0]


def _bulk_download_url(entry: dict[str, Any]) -> str:
    value = entry.get("jsonl_download_uri") or entry.get("download_uri")
    url = _optional_text(value)
    if url is None or not re.match(r"^https://data\.scryfall\.io/", url):
        raise ValueError("Scryfall bulk download URL is missing or untrusted")
    return url


def _snapshot_id(updated_at: str) -> str:
    compact = re.sub(r"[^0-9]", "", updated_at)[:14]
    if len(compact) != 14:
        raise ValueError("Scryfall updated_at is invalid")
    return f"scryfall-{compact}"


def _record_from_dict(payload: dict[str, Any]) -> ScryfallCardRecord:
    faces = tuple(
        CardImageFace(
            face=face["face"],
            thumb=_image_variant_from_dict(face.get("thumb")),
            normal=_image_variant_from_dict(face.get("normal")),
            large=_image_variant_from_dict(face.get("large")),
        )
        for face in payload["faces"]
    )
    return ScryfallCardRecord(
        provider=str(payload["provider"]),
        game=str(payload["game"]),
        provider_card_id=str(payload["provider_card_id"]),
        cardmarket_id=int(payload["cardmarket_id"]),
        name_raw=str(payload["name_raw"]),
        name_normalized=str(payload["name_normalized"]),
        set_code=_optional_text(payload.get("set_code")),
        collector_number=_optional_text(payload.get("collector_number")),
        language=_optional_text(payload.get("language")),
        layout=_optional_text(payload.get("layout")),
        faces=faces,
        raw_record_hash=str(payload["raw_record_hash"]),
    )


def _image_variant_from_dict(payload: object) -> ImageVariant | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError("Scryfall image variant must be an object")
    return ImageVariant(
        url=str(payload["url"]),
        width=int(payload["width"]) if payload.get("width") is not None else None,
        height=int(payload["height"]) if payload.get("height") is not None else None,
        mime_type=_optional_text(payload.get("mime_type")),
        storage_mode=payload.get("storage_mode", "remote"),
        r2_key=_optional_text(payload.get("r2_key")),
        content_sha256=_optional_text(payload.get("content_sha256")),
    )


def _header(headers: dict[str, str], name: str) -> str | None:
    return next((str(value) for key, value in headers.items() if key.casefold() == name), None)


def _get_with_retry(
    client: HttpClient,
    url: str,
    *,
    headers: dict[str, str],
    timeout: int,
) -> HttpResponse:
    last_error: Exception | None = None
    for attempt, delay in enumerate((0.0, 1.0, 3.0, 10.0)):
        if delay:
            time.sleep(delay)
        try:
            response = client.get(url, headers=headers, timeout=timeout)
            if response.status_code == 429 or response.status_code >= 500:
                retry_after = _header(response.headers, "retry-after")
                if retry_after and attempt < 3:
                    time.sleep(min(max(float(retry_after), 0.0), 60.0))
                    continue
            response.raise_for_status()
            return response
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt == 3:
                break
    raise RuntimeError(f"failed to fetch Scryfall snapshot {url}: {last_error}")


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _json_object(body: bytes, label: str) -> dict[str, Any]:
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode() + b"\n"
