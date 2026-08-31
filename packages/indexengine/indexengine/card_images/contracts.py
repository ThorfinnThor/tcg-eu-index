from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import asdict, dataclass
from typing import Literal, cast
from urllib.parse import urlparse

ImageMatchStatus = Literal[
    "exact",
    "manual",
    "probable",
    "ambiguous",
    "missing_prerequisite",
    "provider_missing",
    "provider_error",
    "blocked_legal",
    "blocked_credentials",
    "disabled",
]
MatchMethod = Literal[
    "manual_override",
    "direct_marketplace_id",
    "exact_provider_id",
    "set_number_name_variant",
    "set_number_name_unique",
    "inferred_set_name_unique",
    "set_name_name_unique",
    "attack_text_unique",
    "parsed_identifier_verified",
    "name_candidate_only",
    "none",
]
Finish = Literal[
    "nonfoil",
    "foil",
    "holo",
    "reverse_holo",
    "cold_foil",
    "rainbow_foil",
    "gold_foil",
    "etched",
    "serialized",
    "other",
    "unknown",
]
ArtworkVariant = Literal[
    "base",
    "alt_art",
    "parallel",
    "manga",
    "showcase",
    "enchanted",
    "hyperspace",
    "marvel",
    "extended_art",
    "borderless",
    "serialized",
    "promo",
    "reprint",
    "token",
    "don",
    "other",
    "unknown",
]

PUBLISHABLE_STATUSES = frozenset({"exact", "manual"})


def normalize_card_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    for source in "\u2019\u2018`\u00b4":
        normalized = normalized.replace(source, "'")
    for source in "\u2010\u2011\u2012\u2013\u2014":
        normalized = normalized.replace(source, "-")
    return " ".join(normalized.split())


def source_row_key(
    game: str,
    cardmarket_product_id: int,
    finish: str,
    source_variant_raw: str | None = None,
) -> str:
    raw = "\x1f".join(
        (game, str(cardmarket_product_id), finish, source_variant_raw or "")
    )
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class CanonicalCardIdentity:
    schema_version: int
    game: str
    subgame: str | None
    source_row_key: str
    cardmarket_product_id: int
    cardmarket_name_raw: str
    name_normalized: str
    set_name_raw: str | None
    set_code_raw: str | None
    set_code_canonical: str | None
    set_provider_id: str | None
    collector_number_raw: str | None
    collector_number_canonical: str | None
    language: str | None
    finish: Finish
    source_variant_raw: str | None
    edition: str | None
    artwork_variant: ArtworkVariant | None
    source_updated_at: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("canonical card identity must use schema version 1")
        if self.cardmarket_product_id <= 0:
            raise ValueError("Cardmarket product ID must be positive")
        if not self.source_row_key:
            raise ValueError("source row key is required")


@dataclass(frozen=True)
class ImageVariant:
    url: str
    width: int | None
    height: int | None
    mime_type: str | None
    storage_mode: Literal["remote", "r2"] = "remote"
    r2_key: str | None = None
    content_sha256: str | None = None

    def __post_init__(self) -> None:
        parsed = urlparse(self.url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("card image URLs must use HTTPS")
        if self.width is not None and self.width <= 0:
            raise ValueError("image width must be positive")
        if self.height is not None and self.height <= 0:
            raise ValueError("image height must be positive")
        if self.storage_mode == "r2" and not self.r2_key:
            raise ValueError("R2 image variants require an object key")


@dataclass(frozen=True)
class CardImageFace:
    face: Literal["front", "back", "other"]
    thumb: ImageVariant | None
    normal: ImageVariant | None
    large: ImageVariant | None


@dataclass(frozen=True)
class CardImageAsset:
    schema_version: int
    asset_id: str
    game: str
    provider: str
    provider_card_id: str
    provider_art_id: str | None
    provider_variant_raw: str | None
    language: str | None
    artwork_variant: ArtworkVariant | None
    faces: tuple[CardImageFace, ...]
    provider_record_hash: str
    provider_snapshot_id: str
    first_seen_at: str
    last_verified_at: str
    legal_status: Literal["approved", "pending", "blocked"]


@dataclass(frozen=True)
class CardImageMatch:
    schema_version: int
    source_row_key: str
    asset_id: str | None
    provider: str | None
    provider_card_id: str | None
    provider_art_id: str | None
    status: ImageMatchStatus
    match_method: MatchMethod
    score: int | None
    candidate_count: int
    evidence: tuple[str, ...]
    reason_code: str | None
    matched_at: str
    matcher_version: str
    provider_snapshot_id: str | None

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("card image match must use schema version 1")
        if self.status in PUBLISHABLE_STATUSES and not self.asset_id:
            raise ValueError("publishable card image matches require an asset")
        if self.candidate_count < 0:
            raise ValueError("candidate count cannot be negative")


@dataclass(frozen=True)
class PublicCardImage:
    status: ImageMatchStatus
    provider: str | None = None
    match_method: MatchMethod = "none"
    language: str | None = None
    language_match: Literal["exact", "fallback", "unknown"] | None = None
    artwork_variant: ArtworkVariant | None = None
    front: CardImageFace | None = None
    back: CardImageFace | None = None
    verified_at: str | None = None

    def to_dict(self) -> dict[str, object]:
        if self.status not in PUBLISHABLE_STATUSES:
            return {"status": self.status}
        payload = cast(dict[str, object], json.loads(json.dumps(asdict(self))))
        return cast(dict[str, object], _without_nulls(payload))

    @property
    def normal_url(self) -> str | None:
        return self.front.normal.url if self.front and self.front.normal else None


def public_image_from_match(
    match: CardImageMatch,
    asset: CardImageAsset | None,
) -> PublicCardImage:
    if match.status not in PUBLISHABLE_STATUSES or asset is None:
        return PublicCardImage(status=match.status)
    if asset.legal_status != "approved":
        return PublicCardImage(status="blocked_legal")
    front = next((face for face in asset.faces if face.face == "front"), None)
    back = next((face for face in asset.faces if face.face == "back"), None)
    if front is None or front.normal is None:
        return PublicCardImage(status="provider_error")
    return PublicCardImage(
        status=match.status,
        provider=asset.provider,
        match_method=match.match_method,
        language=asset.language,
        language_match="unknown",
        artwork_variant=asset.artwork_variant,
        front=front,
        back=back,
        verified_at=asset.last_verified_at,
    )


def _without_nulls(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _without_nulls(item)
            for key, item in value.items()
            if item is not None and not (key == "match_method" and item == "none")
        }
    if isinstance(value, list):
        return [_without_nulls(item) for item in value]
    return value
