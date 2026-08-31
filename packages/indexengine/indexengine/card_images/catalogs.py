from __future__ import annotations

import gzip
import hashlib
import html as html_lib
import io
import json
import os
import re
import tarfile
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any, Protocol, cast
from urllib.parse import urljoin

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
from indexengine.card_images.overrides import ManualCardImageOverride
from indexengine.card_images.policy import ProviderPolicy

ADAPTER_VERSION = "1.5.0"
MATCHER_VERSION = "1.2.0"
SITE_URL = "https://tcg-eu-index-web.shuu9599.workers.dev"

PROVIDER_GAMES = {
    "tcgdex": "pokemon",
    "ygoprodeck": "yugioh",
    "digimon": "digimon",
    "lorcast": "lorcana",
    "swudb": "starwarsunlimited",
    "fab_dataset": "fleshandblood",
    "riot_riftbound": "riftbound",
    "bandai_onepiece": "onepiece",
    "optcg": "onepiece",
    "dragonball": "dragonballsuper",
}

PUBLIC_PROVIDERS = (
    "tcgdex",
    "ygoprodeck",
    "digimon",
    "lorcast",
    "swudb",
    "fab_dataset",
    "riot_riftbound",
    "bandai_onepiece",
)

SWU_SET_CODES = (
    "ASH",
    "ASHOP",
    "C24",
    "C25",
    "ESOR",
    "G25",
    "GG",
    "IBH",
    "J24",
    "J25",
    "JTL",
    "JTLOP",
    "LAW",
    "LAWOP",
    "LAWP",
    "LOF",
    "LOFOP",
    "P25",
    "P26",
    "PSHD",
    "PSOR",
    "SEC",
    "SECOP",
    "SHD",
    "SHDOP",
    "SOR",
    "SOROP",
    "SOROPJ",
    "SS1",
    "SS1J",
    "SS2",
    "SS2J",
    "TASH",
    "TS26",
    "TSOR",
    "TWI",
)


class HttpResponse(Protocol):
    content: bytes
    headers: dict[str, str]
    status_code: int

    def raise_for_status(self) -> None: ...


class HttpClient(Protocol):
    def get(self, url: str, **kwargs: Any) -> HttpResponse: ...


@dataclass(frozen=True)
class CatalogCardRecord:
    provider: str
    game: str
    provider_card_id: str
    provider_art_id: str | None
    cardmarket_id: int | None
    cardmarket_expansion_id: int | None
    name_raw: str
    name_normalized: str
    set_code: str | None
    set_name: str | None
    collector_number: str | None
    language: str | None
    variant_raw: str | None
    faces: tuple[CardImageFace, ...]
    raw_record_hash: str


@dataclass(frozen=True)
class CatalogSnapshot:
    provider: str
    game: str
    snapshot_id: str
    fetched_at: str
    source_url: str
    source_version: str
    raw_sha256: str
    records: tuple[CatalogCardRecord, ...]


@dataclass(frozen=True)
class CatalogSyncResult:
    provider: str
    snapshot_id: str
    record_count: int
    changed_keys: tuple[str, ...]


def sync_catalog_snapshot(
    store: ObjectStore,
    provider: str,
    *,
    client: HttpClient | None = None,
    now: datetime | None = None,
) -> CatalogSyncResult:
    if provider not in PROVIDER_GAMES:
        raise ValueError(f"unsupported public catalogue provider: {provider}")
    session = cast(HttpClient, client or requests.Session())
    fetched_at = (now or datetime.now(UTC)).isoformat()
    source_url, source_version, raw, records = _fetch_provider(provider, session)
    minimum = {"tcgdex": 5_000, "ygoprodeck": 10_000, "digimon": 3_000}.get(provider, 100)
    if len(records) < minimum:
        raise ValueError(f"{provider} snapshot has only {len(records)} normalized records")
    raw_hash = sha256_hex(raw)
    safe_version = re.sub(r"[^A-Za-z0-9]+", "", source_version)[-24:] or "snapshot"
    adapter_tag = ADAPTER_VERSION.replace(".", "")
    snapshot_id = f"{provider}-{safe_version}-a{adapter_tag}-{raw_hash[:10]}"
    prefix = f"provider-snapshots/{provider}/{snapshot_id}"
    manifest_key = f"{prefix}/manifest.json"
    if store.exists(manifest_key):
        manifest = _json_object(store.read_bytes(manifest_key))
        return CatalogSyncResult(
            provider,
            snapshot_id,
            int(manifest["record_count"]),
            (),
        )
    snapshot = CatalogSnapshot(
        provider=provider,
        game=PROVIDER_GAMES[provider],
        snapshot_id=snapshot_id,
        fetched_at=fetched_at,
        source_url=source_url,
        source_version=source_version,
        raw_sha256=raw_hash,
        records=tuple(sorted(records, key=_record_sort_key)),
    )
    normalized = _ndjson(asdict(record) for record in snapshot.records)
    manifest = {
        "schema_version": 1,
        "provider": provider,
        "game": snapshot.game,
        "snapshot_id": snapshot_id,
        "fetched_at": fetched_at,
        "source_url": source_url,
        "source_version": source_version,
        "raw_sha256": raw_hash,
        "normalized_sha256": sha256_hex(normalized),
        "record_count": len(records),
        "adapter_version": ADAPTER_VERSION,
    }
    bodies = {
        f"{prefix}/raw.bin.gz": gzip_body(raw),
        f"{prefix}/normalized.ndjson.gz": gzip_body(normalized),
        manifest_key: _json_bytes(manifest),
    }
    changed: list[str] = []
    for key, body in bodies.items():
        if store.exists(key):
            if store.read_bytes(key) != body:
                raise ValueError(f"immutable {provider} snapshot conflict at {key}")
            continue
        store.write_bytes(
            key, body, "application/gzip" if key.endswith(".gz") else "application/json"
        )
        changed.append(key)
    latest_key = f"provider-snapshots/{provider}/latest.json"
    latest = _json_bytes(
        {
            "schema_version": 1,
            "provider": provider,
            "snapshot_id": snapshot_id,
            "manifest_key": manifest_key,
            "activated_at": fetched_at,
        }
    )
    if not store.exists(latest_key) or store.read_bytes(latest_key) != latest:
        store.write_bytes(latest_key, latest, "application/json")
        changed.append(latest_key)
    return CatalogSyncResult(provider, snapshot_id, len(records), tuple(changed))


def load_catalog_snapshot(
    store: ObjectStore, provider: str, snapshot_id: str | None = None
) -> CatalogSnapshot:
    if snapshot_id is None:
        latest = _json_object(store.read_bytes(f"provider-snapshots/{provider}/latest.json"))
        snapshot_id = str(latest["snapshot_id"])
    prefix = f"provider-snapshots/{provider}/{snapshot_id}"
    manifest = _json_object(store.read_bytes(f"{prefix}/manifest.json"))
    normalized = gzip.decompress(store.read_bytes(f"{prefix}/normalized.ndjson.gz"))
    if sha256_hex(normalized) != manifest["normalized_sha256"]:
        raise ValueError(f"{provider} normalized snapshot checksum mismatch")
    records = tuple(
        _record_from_dict(json.loads(line)) for line in normalized.splitlines() if line.strip()
    )
    if len(records) != int(manifest["record_count"]):
        raise ValueError(f"{provider} normalized snapshot record count mismatch")
    return CatalogSnapshot(
        provider=provider,
        game=str(manifest["game"]),
        snapshot_id=str(manifest["snapshot_id"]),
        fetched_at=str(manifest["fetched_at"]),
        source_url=str(manifest["source_url"]),
        source_version=str(manifest["source_version"]),
        raw_sha256=str(manifest["raw_sha256"]),
        records=records,
    )


def match_catalog_identities(
    identities: list[CanonicalCardIdentity],
    snapshot: CatalogSnapshot,
    policy: ProviderPolicy,
    *,
    store: ObjectStore | None = None,
    matched_at: str | None = None,
    marketplace_set_names: Mapping[int, Iterable[str]] | None = None,
    manual_overrides: Mapping[str, ManualCardImageOverride] | None = None,
) -> tuple[list[CardImageMatch], dict[str, CardImageAsset]]:
    by_market: dict[int, list[CatalogCardRecord]] = defaultdict(list)
    by_market_set_name: dict[tuple[int, str], list[CatalogCardRecord]] = defaultdict(list)
    by_provider_set_name: dict[
        tuple[tuple[str, str], str], list[CatalogCardRecord]
    ] = defaultdict(list)
    by_number_name: dict[tuple[str, str], list[CatalogCardRecord]] = defaultdict(list)
    by_name: dict[str, list[CatalogCardRecord]] = defaultdict(list)
    for record in snapshot.records:
        if record.cardmarket_id:
            by_market[record.cardmarket_id].append(record)
        if record.cardmarket_expansion_id:
            by_market_set_name[
                (record.cardmarket_expansion_id, _loose_name(record.name_raw))
            ].append(record)
        provider_set = _provider_set_key(record)
        if any(provider_set):
            by_provider_set_name[(provider_set, _loose_name(record.name_raw))].append(record)
        if record.collector_number:
            by_number_name[(record.collector_number.casefold(), record.name_normalized)].append(
                record
            )
        by_name[record.name_normalized].append(record)
    inferred_market_sets = _infer_marketplace_sets(
        identities,
        snapshot.records,
        marketplace_set_names=marketplace_set_names,
    )
    timestamp = matched_at or snapshot.fetched_at
    matches: list[CardImageMatch] = []
    assets: dict[str, CardImageAsset] = {}
    mirror_cache: dict[str, ImageVariant] = {}
    existing_mirror_keys = (
        set(store.list_keys(f"card-images/{snapshot.provider}/"))
        if store is not None and policy.may_hotlink is False and policy.may_mirror
        else set()
    )
    for identity in identities:
        override = (manual_overrides or {}).get(identity.source_row_key)
        if override is not None:
            match, asset = _match_manual_override(
                identity,
                override,
                snapshot,
                policy,
                timestamp,
                store=store,
                mirror_cache=mirror_cache,
                existing_mirror_keys=existing_mirror_keys,
            )
            assets[asset.asset_id] = asset
            matches.append(match)
            continue
        candidates: list[CatalogCardRecord]
        method = "none"
        evidence: tuple[str, ...] = ()
        if identity.cardmarket_product_id in by_market:
            candidates = by_market[identity.cardmarket_product_id]
            method = "direct_marketplace_id"
            evidence = (f"cardmarket_id={identity.cardmarket_product_id}",)
        elif (
            identity.set_provider_id
            and identity.set_provider_id.isdigit()
            and (
                int(identity.set_provider_id),
                _loose_name(identity.cardmarket_name_raw),
            )
            in by_market_set_name
        ):
            marketplace_set_id = int(identity.set_provider_id)
            candidates = by_market_set_name.get(
                (marketplace_set_id, _loose_name(identity.cardmarket_name_raw)), []
            )
            method = "set_number_name_unique"
            evidence = (
                f"cardmarket_expansion_id={marketplace_set_id}",
                f"name={_loose_name(identity.cardmarket_name_raw)}",
            )
        elif (
            identity.set_provider_id
            and identity.set_provider_id.isdigit()
            and int(identity.set_provider_id) in inferred_market_sets
            and (
                inferred_market_sets[int(identity.set_provider_id)][0],
                _loose_name(identity.cardmarket_name_raw),
            )
            in by_provider_set_name
        ):
            marketplace_set_id = int(identity.set_provider_id)
            provider_set, overlap, runner_up = inferred_market_sets[marketplace_set_id]
            candidates = by_provider_set_name.get(
                (provider_set, _loose_name(identity.cardmarket_name_raw)), []
            )
            method = "inferred_set_name_unique"
            evidence = (
                f"cardmarket_expansion_id={marketplace_set_id}",
                f"provider_set_code={provider_set[0]}",
                f"provider_set_name={provider_set[1]}",
                f"set_signature_overlap={overlap}",
                f"set_signature_runner_up={runner_up}",
                f"name={_loose_name(identity.cardmarket_name_raw)}",
            )
        elif identity.collector_number_canonical:
            key = (identity.collector_number_canonical.casefold(), identity.name_normalized)
            candidates = by_number_name.get(key, [])
            method = "parsed_identifier_verified"
            evidence = (
                f"collector_number={identity.collector_number_canonical}",
                f"name={identity.name_normalized}",
            )
        else:
            candidates = by_name.get(identity.name_normalized, [])
            method = "name_candidate_only"
            evidence = (f"name={identity.name_normalized}",)
        candidates = _refine_candidates(identity, _dedupe_candidates(candidates))
        if not candidates:
            matches.append(
                _unresolved(identity, snapshot, "provider_missing", "NO_CANDIDATE", timestamp)
            )
            continue
        if len(candidates) != 1:
            matches.append(
                _unresolved(
                    identity,
                    snapshot,
                    "ambiguous",
                    "MULTIPLE_PRINTING_OR_ART_CANDIDATES",
                    timestamp,
                    candidate_count=len(candidates),
                )
            )
            continue
        # Name-only matches are exact only when the provider catalogue itself has one
        # printing/art record for the complete marketplace display name.
        candidate = candidates[0]
        asset = _asset(
            candidate,
            snapshot,
            policy,
            timestamp,
            store=store,
            mirror_cache=mirror_cache,
            existing_mirror_keys=existing_mirror_keys,
        )
        assets[asset.asset_id] = asset
        matches.append(
            CardImageMatch(
                schema_version=1,
                source_row_key=identity.source_row_key,
                asset_id=asset.asset_id,
                provider=snapshot.provider,
                provider_card_id=candidate.provider_card_id,
                provider_art_id=candidate.provider_art_id,
                status="exact",
                match_method=method,  # type: ignore[arg-type]
                score=(
                    100
                    if method == "direct_marketplace_id"
                    else 92 if method == "inferred_set_name_unique" else 95
                ),
                candidate_count=1,
                evidence=evidence,
                reason_code=None,
                matched_at=timestamp,
                matcher_version=MATCHER_VERSION,
                provider_snapshot_id=snapshot.snapshot_id,
            )
        )
    return sorted(matches, key=lambda item: item.source_row_key), dict(sorted(assets.items()))


def _match_manual_override(
    identity: CanonicalCardIdentity,
    override: ManualCardImageOverride,
    snapshot: CatalogSnapshot,
    policy: ProviderPolicy,
    timestamp: str,
    *,
    store: ObjectStore | None,
    mirror_cache: dict[str, ImageVariant],
    existing_mirror_keys: set[str],
) -> tuple[CardImageMatch, CardImageAsset]:
    if override.game != identity.game or override.provider != snapshot.provider:
        raise ValueError("manual card-image override targets the wrong game or provider")
    if (
        override.cardmarket_product_id != identity.cardmarket_product_id
        or override.finish != identity.finish
    ):
        raise ValueError("manual card-image override targets the wrong source row")
    candidates = [
        record
        for record in snapshot.records
        if record.provider_card_id == override.provider_card_id
        and record.provider_art_id == override.provider_art_id
    ]
    if not candidates:
        raise ValueError(
            "manual card-image override references a provider card/art ID "
            "that is absent from the active snapshot"
        )
    if any(not _manual_override_name_matches(identity, candidate) for candidate in candidates):
        raise ValueError("manual card-image override card name does not match the source row")
    if identity.collector_number_canonical and any(
        not candidate.collector_number
        or candidate.collector_number.casefold()
        != identity.collector_number_canonical.casefold()
        for candidate in candidates
    ):
        raise ValueError("manual card-image override collector number does not match")
    face_signatures = {
        tuple(
            (
                face.face,
                face.thumb.url if face.thumb else None,
                face.normal.url if face.normal else None,
                face.large.url if face.large else None,
            )
            for face in candidate.faces
        )
        for candidate in candidates
    }
    if len(face_signatures) != 1:
        raise ValueError("manual card-image override resolves to conflicting image assets")
    candidate = sorted(candidates, key=_record_sort_key)[0]
    asset = _asset(
        candidate,
        snapshot,
        policy,
        timestamp,
        store=store,
        mirror_cache=mirror_cache,
        existing_mirror_keys=existing_mirror_keys,
    )
    return (
        CardImageMatch(
            schema_version=1,
            source_row_key=identity.source_row_key,
            asset_id=asset.asset_id,
            provider=snapshot.provider,
            provider_card_id=candidate.provider_card_id,
            provider_art_id=candidate.provider_art_id,
            status="manual",
            match_method="manual_override",
            score=100,
            candidate_count=len(candidates),
            evidence=(
                f"cardmarket_id={identity.cardmarket_product_id}",
                f"provider_card_id={candidate.provider_card_id}",
                f"provider_art_id={candidate.provider_art_id or ''}",
                f"reviewed_at={override.reviewed_at}",
                *override.evidence,
            ),
            reason_code=None,
            matched_at=timestamp,
            matcher_version=MATCHER_VERSION,
            provider_snapshot_id=snapshot.snapshot_id,
        ),
        asset,
    )


def _infer_marketplace_sets(
    identities: list[CanonicalCardIdentity],
    records: tuple[CatalogCardRecord, ...],
    *,
    marketplace_set_names: Mapping[int, Iterable[str]] | None = None,
) -> dict[int, tuple[tuple[str, str], int, int]]:
    """Infer a provider set from direct product links or a corroborated signature.

    Cardmarket's public product catalogue supplies expansion IDs but no expansion
    names. A direct Cardmarket product ID establishes the provider set for that
    expansion when every direct record agrees. Otherwise, a single card name is
    never enough because reprints are common: signature inference requires at
    least three shared names, a two-name lead over the next provider set, and 60%
    coverage of the observable expansion basket. The full Cardmarket singles
    catalogue should be supplied when available; collector-only baskets are
    retained as a safe fallback for local and historical runs.
    """
    expansion_by_product = {
        identity.cardmarket_product_id: int(identity.set_provider_id)
        for identity in identities
        if identity.set_provider_id and identity.set_provider_id.isdigit()
    }
    direct_set_products: dict[int, dict[tuple[str, str], set[int]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for record in records:
        if record.cardmarket_id is None or record.cardmarket_id not in expansion_by_product:
            continue
        provider_set = _provider_set_key(record)
        if any(provider_set):
            direct_set_products[expansion_by_product[record.cardmarket_id]][provider_set].add(
                record.cardmarket_id
            )
    inferred: dict[int, tuple[tuple[str, str], int, int]] = {}
    for expansion_id, provider_sets in direct_set_products.items():
        if len(provider_sets) == 1:
            provider_set, product_ids = next(iter(provider_sets.items()))
            inferred[expansion_id] = (provider_set, len(product_ids), 0)

    marketplace_names: dict[int, set[str]] = defaultdict(set)
    for expansion_id, names in (marketplace_set_names or {}).items():
        marketplace_names[int(expansion_id)].update(
            normalized for name in names if (normalized := _loose_name(str(name)))
        )
    for identity in identities:
        if identity.set_provider_id and identity.set_provider_id.isdigit():
            marketplace_names[int(identity.set_provider_id)].add(
                _loose_name(identity.cardmarket_name_raw)
            )
    provider_names: dict[tuple[str, str], set[str]] = defaultdict(set)
    for record in records:
        provider_set = _provider_set_key(record)
        if any(provider_set):
            provider_names[provider_set].add(_loose_name(record.name_raw))
    for expansion_id, names in marketplace_names.items():
        if expansion_id in inferred:
            continue
        scored = sorted(
            (
                (len(names & candidate_names), provider_set)
                for provider_set, candidate_names in provider_names.items()
                if names & candidate_names
            ),
            reverse=True,
        )
        if not scored:
            continue
        overlap, provider_set = scored[0]
        runner_up = scored[1][0] if len(scored) > 1 else 0
        provider_size = len(provider_names[provider_set])
        if _signature_is_corroborated(
            records[0].provider if records else "",
            overlap,
            runner_up,
            len(names),
            provider_size,
        ):
            inferred[expansion_id] = (provider_set, overlap, runner_up)
    return inferred


def _signature_is_corroborated(
    provider: str,
    overlap: int,
    runner_up: int,
    marketplace_size: int,
    provider_size: int,
) -> bool:
    """Accept only signatures that are both distinctive and sufficiently complete."""
    if overlap < 3 or overlap < runner_up + 2:
        return False
    if overlap / marketplace_size >= 0.6:
        return True
    # Cardmarket promotional and parallel-art expansions can contain many more
    # products than a provider's base set. Cross-validation against existing
    # exact rows showed this provider-side rule adds coverage without changing
    # any known Yu-Gi-Oh!, Lorcana, or Flesh and Blood set assignments.
    return (
        provider in {"ygoprodeck", "lorcast", "fab_dataset"}
        and overlap >= 8
        and overlap >= runner_up + 4
        and overlap / provider_size >= 0.5
        and (runner_up == 0 or overlap / runner_up >= 1.5)
    )


def _provider_set_key(record: CatalogCardRecord) -> tuple[str, str]:
    # YGOPRODeck's set_code is the full printed number (for example
    # BACH-EN025), not a set-level identifier. Grouping by it would make every
    # printing look like a one-card set and prevent corroborated set inference.
    if record.provider == "ygoprodeck":
        return "", record.set_name or ""
    return record.set_code or "", record.set_name or ""


def _fetch_provider(
    provider: str, session: HttpClient
) -> tuple[str, str, bytes, list[CatalogCardRecord]]:
    if provider == "tcgdex":
        meta = _json_object(
            _get(session, "https://api.github.com/repos/tcgdex/cards-database/releases/latest")
        )
        raw = _get(session, str(meta["tarball_url"]), timeout=240)
        return str(meta["html_url"]), str(meta["tag_name"]), raw, parse_tcgdex_tarball(raw)
    if provider == "fab_dataset":
        commit = _json_object(
            _get(
                session,
                "https://api.github.com/repos/the-fab-cube/flesh-and-blood-cards/commits/main",
            )
        )
        sha = str(commit["sha"])
        base = f"https://raw.githubusercontent.com/the-fab-cube/flesh-and-blood-cards/{sha}/json/english"
        flattened = _get(session, f"{base}/card-flattened.json", timeout=180)
        sets = _get(session, f"{base}/set.json", timeout=60)
        raw = _json_bytes({"cards": json.loads(flattened), "sets": json.loads(sets)})
        return str(commit["html_url"]), sha, raw, parse_fab_payload(raw)
    if provider == "riot_riftbound":
        url = "https://playriftbound.com/en-us/card-gallery/"
        raw = _get(session, url, timeout=180)
        return url, _today_version(), raw, parse_riot_riftbound_page(raw)
    if provider == "bandai_onepiece":
        url = "https://en.onepiece-cardgame.com/cardlist/"
        listing = _get(session, url, timeout=120).decode("utf-8", errors="replace")
        packs = _bandai_onepiece_packs(listing)
        bandai_cards: list[dict[str, str]] = []
        for pack_id, pack_name in packs:
            time.sleep(0.05)
            pack_page = _get(session, f"{url}?series={pack_id}", timeout=120).decode(
                "utf-8", errors="replace"
            )
            bandai_cards.extend(
                _bandai_onepiece_page_cards(pack_page, pack_id, pack_name)
            )
        raw = _json_bytes({"packs": packs, "cards": bandai_cards})
        return url, _today_version(), raw, parse_bandai_onepiece_payload(raw)
    if provider == "ygoprodeck":
        url = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
        raw = _get(session, url, timeout=240)
        return url, _today_version(), raw, parse_ygoprodeck_payload(raw)
    if provider == "digimon":
        url = "https://digimoncard.io/api-public/search.php?series=Digimon%20Card%20Game"
        raw = _get(session, url, timeout=240)
        return url, _today_version(), raw, parse_digimon_payload(raw)
    if provider == "lorcast":
        sets_url = "https://api.lorcast.com/v0/sets"
        sets_payload = _json_object(_get(session, sets_url))
        cards: list[object] = []
        for raw_set in cast(list[dict[str, Any]], sets_payload["results"]):
            time.sleep(0.1)
            cards.extend(json.loads(_get(session, f"{sets_url}/{raw_set['code']}/cards")))
        raw = _json_bytes({"sets": sets_payload["results"], "cards": cards})
        return sets_url, _today_version(), raw, parse_lorcast_payload(raw)
    if provider == "swudb":
        base = "https://api.swu-db.com/cards"
        cards = []
        failed_set_codes = []
        for code in SWU_SET_CODES:
            time.sleep(0.1)
            try:
                response = json.loads(_get(session, f"{base}/{code}?format=json", timeout=60))
            except requests.RequestException:
                failed_set_codes.append(code)
                continue
            cards.extend(response if isinstance(response, list) else response.get("data", []))
        raw = _json_bytes(
            {
                "set_codes": SWU_SET_CODES,
                "failed_set_codes": failed_set_codes,
                "cards": cards,
            }
        )
        return "https://www.swu-db.com/api", _today_version(), raw, parse_swudb_payload(raw)
    if provider == "optcg":
        api_key = os.environ.get("OPTCG_API_KEY")
        if not api_key:
            raise ValueError("OPTCG_API_KEY is required to sync the One Piece catalogue")
        url = "https://optcg-api.arjunbansal-ai.workers.dev/cards/all"
        raw = _get(session, url, timeout=180, headers={"X-API-Key": api_key})
        return url, _today_version(), raw, parse_optcg_payload(raw)
    if provider == "dragonball":
        api_key = os.environ.get("APITCG_API_KEY")
        if not api_key:
            raise ValueError("APITCG_API_KEY is required to sync Dragon Ball catalogues")
        url = "https://api.apitcg.com/api/products"
        products: list[dict[str, Any]] = []
        for subgame in (
            "dragon-ball-super-fusion-world",
            "dragon-ball-super-masters",
        ):
            page = 1
            while True:
                page_url = f"{url}?tcg={subgame}&type=card&limit=100&page={page}"
                payload = _json_object(
                    _get(session, page_url, timeout=60, headers={"X-API-Key": api_key})
                )
                batch = payload.get("data")
                if not isinstance(batch, list):
                    raise ValueError("API TCG returned an invalid product page")
                products.extend({**item, "_subgame": subgame} for item in batch)
                if len(batch) < 100:
                    break
                page += 1
        raw = _json_bytes({"products": products})
        return "https://docs.apitcg.com/", _today_version(), raw, parse_apitcg_payload(raw)
    raise AssertionError(provider)


def parse_tcgdex_tarball(raw: bytes) -> list[CatalogCardRecord]:
    records: list[CatalogCardRecord] = []
    set_info: dict[tuple[str, str], tuple[str, str, int | None]] = {}
    card_files: list[tuple[str, str, bytes]] = []
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile() or not member.name.endswith(".ts"):
                continue
            if "/data-asia/" in member.name:
                catalogue = "data-asia"
            elif "/data/" in member.name:
                catalogue = "data"
            else:
                continue
            relative = member.name.split(f"/{catalogue}/", 1)[1]
            parts = PurePosixPath(relative).parts
            if len(parts) not in {2, 3}:
                continue
            body_stream = archive.extractfile(member)
            if body_stream is None:
                continue
            body = body_stream.read()
            if len(parts) == 2:
                text = body.decode(errors="replace")
                set_id = _ts_string(text, "id")
                set_name = _ts_display_name(text)
                if set_id and set_name:
                    set_info[(catalogue, f"{parts[0]}/{PurePosixPath(parts[1]).stem}")] = (
                        set_id,
                        set_name,
                        _ts_cardmarket_id(text),
                    )
            else:
                card_files.append((catalogue, relative, body))
    for catalogue, relative, body in card_files:
        path = PurePosixPath(relative)
        info = set_info.get((catalogue, f"{path.parts[0]}/{path.parts[1]}"))
        if info is None:
            continue
        set_id, set_name, market_set_id = info
        number = path.stem
        text = body.decode(errors="replace")
        name = _ts_display_name(text) or f"{set_id} {number}"
        market_ids = {int(item) for item in re.findall(r"cardmarket\s*:\s*(\d+)", text)}
        if catalogue == "data-asia" and not market_ids:
            continue
        # Keep the complete provider catalogue. Direct Cardmarket IDs are the
        # strongest match, but cards without one are still required for safe
        # expansion-signature and set/number matching.
        market_ids_or_none: list[int | None] = []
        market_ids_or_none.extend(sorted(market_ids))
        if not market_ids_or_none:
            market_ids_or_none.append(None)
        for market_id in market_ids_or_none:
            image = (
                f"https://images.pokemontcg.io/{set_id}/{number}.png"
                if catalogue == "data"
                else None
            )
            records.append(
                _record(
                    provider="tcgdex",
                    game="pokemon",
                    provider_card_id=f"{set_id}-{number}",
                    provider_art_id=None,
                    cardmarket_id=market_id,
                    cardmarket_expansion_id=market_set_id,
                    name=name,
                    set_code=set_id,
                    set_name=set_name,
                    number=number,
                    language="en" if catalogue == "data" else "ja",
                    variant=None,
                    image_url=image,
                    raw={
                        "catalogue": catalogue,
                        "path": relative,
                        "cardmarket_id": market_id,
                    },
                    mime_type="image/png",
                )
            )
    return records


def parse_ygoprodeck_payload(raw: bytes) -> list[CatalogCardRecord]:
    payload = _json_object(raw)
    result: list[CatalogCardRecord] = []
    for card in cast(list[dict[str, Any]], payload.get("data", [])):
        name = _text(card.get("name"))
        provider_id = _text(card.get("id"))
        sets = cast(
            list[Any], card.get("card_sets") if isinstance(card.get("card_sets"), list) else []
        )
        images = cast(
            list[Any], card.get("card_images") if isinstance(card.get("card_images"), list) else []
        )
        if not name or not provider_id:
            continue
        for card_set in sets or [{}]:
            if not isinstance(card_set, dict):
                continue
            for image in images:
                if not isinstance(image, dict) or not _text(image.get("image_url")):
                    continue
                result.append(
                    _record(
                        provider="ygoprodeck",
                        game="yugioh",
                        provider_card_id=provider_id,
                        provider_art_id=_text(image.get("id")),
                        cardmarket_id=None,
                        name=name,
                        set_code=_text(card_set.get("set_code")),
                        set_name=_text(card_set.get("set_name")),
                        number=_text(card_set.get("set_code")),
                        language="en",
                        variant=_text(card_set.get("set_rarity")),
                        image_url=str(image["image_url"]),
                        raw={"id": card.get("id"), "set": card_set, "image": image},
                        mime_type="image/jpeg",
                    )
                )
    return result


def parse_digimon_payload(raw: bytes) -> list[CatalogCardRecord]:
    payload = json.loads(raw)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for card in payload if isinstance(payload, list) else []:
        if isinstance(card, dict) and _text(card.get("id")) and _text(card.get("name")):
            grouped[(str(card["id"]), normalize_card_name(str(card["name"])))].append(card)
    result = []
    for (number, _), cards in grouped.items():
        card = cards[0]
        names = {str(item["name"]) for item in cards}
        if len(names) != 1:
            continue
        set_names = {
            name for item in cards for name in item.get("set_name", []) if isinstance(name, str)
        }
        result.append(
            _record(
                provider="digimon",
                game="digimon",
                provider_card_id=number,
                provider_art_id=None,
                cardmarket_id=None,
                name=str(card["name"]),
                set_code=number.split("-", 1)[0],
                set_name=next(iter(set_names)) if len(set_names) == 1 else None,
                number=number,
                language="en",
                variant=None,
                image_url=f"https://images.digimoncard.io/images/cards/{number}.jpg",
                raw={
                    "id": number,
                    "name": card["name"],
                    "prints": len(cards),
                    "sets": sorted(set_names),
                },
                mime_type="image/jpeg",
            )
        )
    return result


def parse_lorcast_payload(raw: bytes) -> list[CatalogCardRecord]:
    payload = _json_object(raw)
    result = []
    for card in cast(list[dict[str, Any]], payload.get("cards", [])):
        name = _lorcana_name(card)
        uris = (
            card.get("image_uris", {}).get("digital", {})
            if isinstance(card.get("image_uris"), dict)
            else {}
        )
        card_set = cast(
            dict[str, Any], card.get("set") if isinstance(card.get("set"), dict) else {}
        )
        if not name or not _text(card.get("id")) or not _text(uris.get("normal")):
            continue
        result.append(
            _record(
                provider="lorcast",
                game="lorcana",
                provider_card_id=str(card["id"]),
                provider_art_id=None,
                cardmarket_id=None,
                name=name,
                set_code=_text(card_set.get("code")),
                set_name=_text(card_set.get("name")),
                number=_text(card.get("collector_number")),
                language=_text(card.get("lang")),
                variant=_text(card.get("rarity")),
                image_url=str(uris["normal"]),
                raw=card,
                mime_type="image/avif",
                thumb_url=_text(uris.get("small")),
                large_url=_text(uris.get("large")),
            )
        )
    return result


def parse_swudb_payload(raw: bytes) -> list[CatalogCardRecord]:
    payload = _json_object(raw)
    result = []
    for card in cast(list[dict[str, Any]], payload.get("cards", [])):
        name = _swu_name(card)
        art = _text(card.get("FrontArt"))
        set_code = _text(card.get("Set"))
        number = _text(card.get("Number"))
        if not name or not art or not set_code or not number:
            continue
        result.append(
            _record(
                provider="swudb",
                game="starwarsunlimited",
                provider_card_id=f"{set_code}-{number}",
                provider_art_id=_text(card.get("cid")),
                cardmarket_id=None,
                name=name,
                set_code=set_code,
                set_name=set_code,
                number=number,
                language="en",
                variant=_text(card.get("VariantType")),
                image_url=art,
                raw=card,
                mime_type="image/png",
                back_url=_text(card.get("BackArt")),
            )
        )
    return result


def parse_fab_payload(raw: bytes) -> list[CatalogCardRecord]:
    payload = _json_object(raw)
    set_names = {
        str(item["id"]): str(item["name"])
        for item in cast(list[dict[str, Any]], payload.get("sets", []))
        if _text(item.get("id")) and _text(item.get("name"))
    }
    result = []
    for printing in cast(list[dict[str, Any]], payload.get("cards", [])):
        name = _text(printing.get("name"))
        color = _text(printing.get("color"))
        if color in {"Red", "Yellow", "Blue"}:
            name = f"{name} ({color})" if name else None
        image = _text(printing.get("image_url"))
        provider_id = _text(printing.get("printing_unique_id"))
        number = _text(printing.get("id"))
        set_code = _text(printing.get("set_id"))
        if not name or not image or not provider_id:
            continue
        result.append(
            _record(
                provider="fab_dataset",
                game="fleshandblood",
                provider_card_id=provider_id,
                provider_art_id=None,
                cardmarket_id=None,
                name=name,
                set_code=set_code,
                set_name=set_names.get(set_code or ""),
                number=number,
                language="en",
                variant="/".join(
                    filter(None, (_text(printing.get("edition")), _text(printing.get("foiling"))))
                ),
                image_url=image,
                raw=printing,
                mime_type="image/png",
            )
        )
    return result


def parse_riot_riftbound_page(raw: bytes) -> list[CatalogCardRecord]:
    """Parse the official Riot card gallery embedded Next.js catalogue."""
    text = raw.decode("utf-8", errors="replace")
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        text,
        re.DOTALL,
    )
    if match is None:
        raise ValueError("Riftbound card gallery has no __NEXT_DATA__ payload")
    payload = json.loads(match.group(1))
    card_lists: list[list[dict[str, Any]]] = []

    def find_cards(value: object) -> None:
        if isinstance(value, list):
            cards = [item for item in value if isinstance(item, dict)]
            if cards and all("publicCode" in item and "cardImage" in item for item in cards):
                card_lists.append(cast(list[dict[str, Any]], cards))
                return
            for item in value:
                find_cards(item)
        elif isinstance(value, dict):
            for item in value.values():
                find_cards(item)

    find_cards(payload)
    if not card_lists:
        raise ValueError("Riftbound card gallery contains no card catalogue")
    cards = max(card_lists, key=len)
    result: list[CatalogCardRecord] = []
    for card in cards:
        provider_id = _text(card.get("id"))
        name = _text(card.get("name"))
        public_code = _text(card.get("publicCode"))
        card_set = cast(dict[str, Any], card.get("set") or {})
        set_value = cast(dict[str, Any], card_set.get("value") or {})
        card_image = cast(dict[str, Any], card.get("cardImage") or {})
        image_url = _text(card_image.get("url"))
        if not provider_id or not name or not public_code or not image_url:
            continue
        rarity = cast(dict[str, Any], card.get("rarity") or {})
        rarity_value = cast(dict[str, Any], rarity.get("value") or {})
        result.append(
            _record(
                provider="riot_riftbound",
                game="riftbound",
                provider_card_id=provider_id,
                provider_art_id=provider_id,
                cardmarket_id=None,
                name=name,
                set_code=_text(set_value.get("id")),
                set_name=_text(set_value.get("label")),
                number=public_code,
                language="en",
                variant=_text(rarity_value.get("label")),
                image_url=image_url,
                raw=card,
                mime_type=_text(card_image.get("mimeType")) or "image/png",
            )
        )
    return result


def parse_bandai_onepiece_payload(raw: bytes) -> list[CatalogCardRecord]:
    """Parse the normalized official Bandai ONE PIECE card-list payload."""
    payload = _json_object(raw)
    result: list[CatalogCardRecord] = []
    for card in cast(list[dict[str, Any]], payload.get("cards", [])):
        provider_id = _text(card.get("id"))
        name = _text(card.get("name"))
        image_url = _text(card.get("image_url"))
        if not provider_id or not name or not image_url:
            continue
        result.append(
            _record(
                provider="bandai_onepiece",
                game="onepiece",
                provider_card_id=provider_id,
                provider_art_id=provider_id,
                cardmarket_id=None,
                name=name,
                set_code=_text(card.get("set_code")),
                set_name=_text(card.get("set_name")),
                number=_base_onepiece_number(provider_id),
                language="en",
                variant=_text(card.get("variant")),
                image_url=image_url,
                raw=card,
                mime_type="image/png",
            )
        )
    return result


def _bandai_onepiece_packs(page: str) -> list[tuple[str, str]]:
    packs = {
        pack_id: _html_text(label)
        for pack_id, label in re.findall(
            r'<option[^>]+value=["\'](569\d+)["\'][^>]*>(.*?)</option>',
            page,
            flags=re.IGNORECASE | re.DOTALL,
        )
    }
    if not packs:
        raise ValueError("Bandai ONE PIECE card list contains no product series")
    return sorted(packs.items())


def _bandai_onepiece_page_cards(
    page: str, pack_id: str, pack_name: str
) -> list[dict[str, str]]:
    set_match = re.search(r"\[([A-Z]+-?\d+)\]", pack_name)
    set_code = set_match.group(1) if set_match else ""
    cards: list[dict[str, str]] = []
    for provider_id, body in re.findall(
        r'<dl[^>]+class=["\'][^"\']*modalCol[^"\']*["\'][^>]+id=["\']([^"\']+)["\'][^>]*>(.*?)</dl>',
        page,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        name_match = re.search(
            r'<div[^>]+class=["\'][^"\']*cardName[^"\']*["\'][^>]*>(.*?)</div>',
            body,
            flags=re.IGNORECASE | re.DOTALL,
        )
        image_match = re.search(
            r'<img[^>]+(?:data-src|src)=["\']([^"\']+)["\']',
            body,
            flags=re.IGNORECASE,
        )
        name = _html_text(name_match.group(1)) if name_match else ""
        if not name or image_match is None:
            continue
        base_number = _base_onepiece_number(provider_id)
        variant = provider_id[len(base_number) :].lstrip("_")
        cards.append(
            {
                "id": provider_id,
                "name": name,
                "set_code": set_code,
                "set_name": pack_name,
                "variant": variant,
                "image_url": urljoin(
                    "https://en.onepiece-cardgame.com/cardlist/", image_match.group(1)
                ),
                "pack_id": pack_id,
            }
        )
    return cards


def _html_text(value: str) -> str:
    decoded = html_lib.unescape(value)
    return " ".join(re.sub(r"<[^>]+>", " ", decoded).split())


def parse_optcg_payload(raw: bytes) -> list[CatalogCardRecord]:
    payload = json.loads(raw)
    cards = payload if isinstance(payload, list) else payload.get("data", [])
    result = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        provider_id = _text(card.get("id"))
        name = _text(card.get("name"))
        image = _text(card.get("image_url"))
        if not provider_id or not name or not image:
            continue
        raw_sets = card.get("sets") if isinstance(card.get("sets"), list) else []
        first_set = raw_sets[0] if raw_sets and isinstance(raw_sets[0], dict) else {}
        result.append(
            _record(
                provider="optcg",
                game="onepiece",
                provider_card_id=provider_id,
                provider_art_id=provider_id,
                cardmarket_id=None,
                name=name,
                set_code=_text(first_set.get("id")),
                set_name=_text(first_set.get("label")),
                number=_base_onepiece_number(provider_id),
                language="en",
                variant=_text(card.get("variant_type")),
                image_url=image,
                raw=card,
                mime_type="image/png",
            )
        )
    return result


def parse_apitcg_payload(raw: bytes) -> list[CatalogCardRecord]:
    payload = _json_object(raw)
    result = []
    for product in cast(list[dict[str, Any]], payload.get("products", [])):
        provider_id = _text(product.get("_id"))
        name = _text(product.get("name"))
        code = _text(product.get("code"))
        product_set = cast(
            dict[str, Any],
            product.get("set") if isinstance(product.get("set"), dict) else {},
        )
        images = cast(
            list[Any],
            product.get("images") if isinstance(product.get("images"), list) else [],
        )
        image = cast(dict[str, Any], images[0] if images and isinstance(images[0], dict) else {})
        normal = _text(image.get("medium")) or _text(image.get("large"))
        if not provider_id or not name or not normal:
            continue
        result.append(
            _record(
                provider="dragonball",
                game="dragonballsuper",
                provider_card_id=provider_id,
                provider_art_id=None,
                cardmarket_id=None,
                name=name,
                set_code=_text(product_set.get("code")),
                set_name=_text(product_set.get("name")),
                number=code,
                language="en",
                variant=_text(product.get("_subgame")),
                image_url=normal,
                raw=product,
                mime_type="image/jpeg",
                thumb_url=_text(image.get("small")),
                large_url=_text(image.get("large")),
            )
        )
    return result


def _asset(
    record: CatalogCardRecord,
    snapshot: CatalogSnapshot,
    policy: ProviderPolicy,
    timestamp: str,
    *,
    store: ObjectStore | None,
    mirror_cache: dict[str, ImageVariant],
    existing_mirror_keys: set[str],
) -> CardImageAsset:
    faces = record.faces
    if policy.may_hotlink is False and policy.may_mirror:
        if store is None:
            raise ValueError(f"{record.provider} requires an object store for mirrored images")
        faces = tuple(
            _mirror_face(store, record, face, mirror_cache, existing_mirror_keys)
            for face in faces
        )
    asset_id = hashlib.sha256(
        f"{record.provider}\x1f{record.provider_card_id}\x1f{record.provider_art_id or ''}".encode()
    ).hexdigest()
    return CardImageAsset(
        schema_version=1,
        asset_id=asset_id,
        game=record.game,
        provider=record.provider,
        provider_card_id=record.provider_card_id,
        provider_art_id=record.provider_art_id,
        provider_variant_raw=record.variant_raw,
        language=record.language,
        artwork_variant="unknown",
        faces=faces,
        provider_record_hash=record.raw_record_hash,
        provider_snapshot_id=snapshot.snapshot_id,
        first_seen_at=timestamp,
        last_verified_at=timestamp,
        legal_status=policy.legal_status,
    )


def _mirror_face(
    store: ObjectStore,
    record: CatalogCardRecord,
    face: CardImageFace,
    cache: dict[str, ImageVariant],
    existing_keys: set[str],
) -> CardImageFace:
    def mirror(variant: ImageVariant | None, _label: str) -> ImageVariant | None:
        if variant is None:
            return None
        extension = ".jpg" if variant.mime_type == "image/jpeg" else ".png"
        art = record.provider_art_id or "base"
        source_hash = hashlib.sha256(variant.url.encode()).hexdigest()[:12]
        filename = f"{record.provider_card_id}-{art}-{face.face}-{source_hash}{extension}"
        key = f"card-images/{record.provider}/{filename}"
        if key in cache:
            return cache[key]
        if key not in existing_keys:
            response = requests.get(variant.url, timeout=60)
            response.raise_for_status()
            store.write_bytes(
                key, response.content, variant.mime_type or "application/octet-stream"
            )
            existing_keys.add(key)
        mirrored = ImageVariant(
            url=f"{SITE_URL}/api/card-images/{key.removeprefix('card-images/')}",
            width=variant.width,
            height=variant.height,
            mime_type=variant.mime_type,
            storage_mode="r2",
            r2_key=key,
        )
        cache[key] = mirrored
        return mirrored

    return CardImageFace(
        face=face.face,
        thumb=mirror(face.thumb, "thumb"),
        normal=mirror(face.normal, "normal"),
        large=mirror(face.large, "large"),
    )


def _record(
    *,
    provider: str,
    game: str,
    provider_card_id: str,
    provider_art_id: str | None,
    cardmarket_id: int | None,
    name: str,
    set_code: str | None,
    set_name: str | None,
    number: str | None,
    language: str | None,
    variant: str | None,
    image_url: str | None,
    raw: object,
    mime_type: str,
    thumb_url: str | None = None,
    large_url: str | None = None,
    back_url: str | None = None,
    cardmarket_expansion_id: int | None = None,
) -> CatalogCardRecord:
    faces: list[CardImageFace] = []
    if image_url:
        faces.append(
            CardImageFace(
                face="front",
                thumb=_variant(thumb_url or image_url, mime_type),
                normal=_variant(image_url, mime_type),
                large=_variant(large_url or image_url, mime_type),
            )
        )
    if back_url:
        faces.append(
            CardImageFace(
                face="back",
                thumb=_variant(back_url, mime_type),
                normal=_variant(back_url, mime_type),
                large=_variant(back_url, mime_type),
            )
        )
    return CatalogCardRecord(
        provider=provider,
        game=game,
        provider_card_id=provider_card_id,
        provider_art_id=provider_art_id,
        cardmarket_id=cardmarket_id,
        cardmarket_expansion_id=cardmarket_expansion_id,
        name_raw=name,
        name_normalized=normalize_card_name(name),
        set_code=set_code,
        set_name=set_name,
        collector_number=number,
        language=language,
        variant_raw=variant,
        faces=tuple(faces),
        raw_record_hash=sha256_hex(_json_bytes(raw)),
    )


def _variant(url: str, mime_type: str) -> ImageVariant:
    return ImageVariant(url=url, width=None, height=None, mime_type=mime_type)


def _dedupe_candidates(records: list[CatalogCardRecord]) -> list[CatalogCardRecord]:
    unique: dict[tuple[str, str | None, str | None, str | None], CatalogCardRecord] = {}
    for record in records:
        key = (
            record.provider_card_id,
            record.provider_art_id,
            record.set_code,
            record.collector_number,
        )
        unique[key] = record
    return sorted(unique.values(), key=_record_sort_key)


def _refine_candidates(
    identity: CanonicalCardIdentity, records: list[CatalogCardRecord]
) -> list[CatalogCardRecord]:
    if len(records) <= 1:
        return records
    loose_name = _loose_name(identity.cardmarket_name_raw)
    named = [record for record in records if _loose_name(record.name_raw) == loose_name]
    if named:
        records = named
    if len(records) > 1 and identity.collector_number_canonical:
        numbered = [
            record
            for record in records
            if record.collector_number
            and record.collector_number.casefold() == identity.collector_number_canonical.casefold()
        ]
        if numbered:
            records = numbered
    return records


def _unresolved(
    identity: CanonicalCardIdentity,
    snapshot: CatalogSnapshot,
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
        provider=snapshot.provider,
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
        provider_snapshot_id=snapshot.snapshot_id,
    )


def _get(
    session: HttpClient,
    url: str,
    *,
    timeout: int = 60,
    headers: dict[str, str] | None = None,
) -> bytes:
    response: HttpResponse | None = None
    for attempt in range(4):
        response = session.get(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "tcg-eu-index/0.1 card-images",
                **(headers or {}),
            },
            timeout=timeout,
        )
        if response.status_code < 500 and response.status_code != 429:
            break
        if attempt < 3:
            time.sleep(2**attempt)
    assert response is not None
    response.raise_for_status()
    return response.content


def _record_from_dict(payload: dict[str, Any]) -> CatalogCardRecord:
    def variant(value: object) -> ImageVariant | None:
        return ImageVariant(**value) if isinstance(value, dict) else None

    faces = tuple(
        CardImageFace(
            face=face["face"],
            thumb=variant(face.get("thumb")),
            normal=variant(face.get("normal")),
            large=variant(face.get("large")),
        )
        for face in payload["faces"]
    )
    return CatalogCardRecord(**{"cardmarket_expansion_id": None, **payload, "faces": faces})


def _record_sort_key(record: CatalogCardRecord) -> tuple[object, ...]:
    return (
        record.cardmarket_id or 0,
        record.name_normalized,
        record.set_code or "",
        record.collector_number or "",
        record.provider_card_id,
        record.provider_art_id or "",
    )


def _ts_string(text: str, field: str) -> str | None:
    match = re.search(rf"\b{re.escape(field)}\s*:\s*(['\"])(.*?)\1", text)
    return match.group(2) if match else None


def _ts_english_name(text: str) -> str | None:
    match = re.search(r"\bname\s*:\s*\{\s*en\s*:\s*(['\"])(.*?)\1", text, re.S)
    return _decode_ts_value(match.group(2)) if match else None


def _ts_display_name(text: str) -> str | None:
    english = _ts_english_name(text)
    if english:
        return english
    block = re.search(r"\bname\s*:\s*\{(.*?)\}", text, re.S)
    if block is None:
        return None
    preferred = re.search(
        r"(?:\bid\b|\bja\b|\bko\b|['\"]zh-tw['\"]|\bth\b)\s*:\s*(['\"])(.*?)\1",
        block.group(1),
        re.S,
    )
    if preferred:
        return _decode_ts_value(preferred.group(2))
    fallback = re.search(r"(?:\w+|['\"][^'\"]+['\"])\s*:\s*(['\"])(.*?)\1", block.group(1), re.S)
    return _decode_ts_value(fallback.group(2)) if fallback else None


def _decode_ts_value(value: str) -> str:
    return bytes(value, "utf-8").decode("unicode_escape") if "\\" in value else value


def _ts_cardmarket_id(text: str) -> int | None:
    match = re.search(r"\bthirdParty\s*:\s*\{.*?\bcardmarket\s*:\s*(\d+)", text, re.S)
    return int(match.group(1)) if match else None


def _loose_name(value: str) -> str:
    value = re.sub(r"\s*\[[^\]]*\]\s*$", "", value)
    return "".join(character for character in normalize_card_name(value) if character.isalnum())


_SWU_REVIEWED_NAME_ALIASES = {
    ("countdookudarthtyranus", "countdookudarthtyrannus"),
    ("c3poanythingimightdo", "c3p0anythingimightdo"),
    ("idenversioinfernosquadcommander", "idenversioinferosquadcommander"),
    ("securitycomplex", "securitycomplexscarif"),
    ("energyconversionlab", "energyconversionlabeadu"),
    ("tarkintown", "tarkintownlothal"),
    ("jabbathehutthishighexaltedness", "jabbathehutthishighexaltdeness"),
    ("petranakiarena", "petranakiarenageonosis"),
    ("datavault", "datavaultscarif"),
    ("poedamerononehellofapilot", "poedamerononehellofaapilot"),
    ("theedpalace", "theedpalacenaboo"),
    ("shieldgeneratorcomplex", "shieldgeneratorcomplexendor"),
    ("moseisley", "moseisleytatooine"),
    ("massassitemple", "massassitempleyavin4"),
    ("c3pohumancyborgrelations", "c3p0humancyborgrelations"),
    ("enfysnestuntilwecangonohigher", "enfynestuntilwecangonohigher"),
    ("k2solockingthevault", "k2s0lockingthevault"),
}


def _manual_override_name_matches(
    identity: CanonicalCardIdentity, candidate: CatalogCardRecord
) -> bool:
    source_name = _loose_name(identity.cardmarket_name_raw)
    provider_name = _loose_name(candidate.name_raw)
    if source_name == provider_name:
        return True
    if identity.game == "digimon" and identity.collector_number_canonical:
        if source_name.endswith("ace") and source_name.removesuffix("ace") == provider_name:
            return True
        source_primary_name = _loose_name(identity.cardmarket_name_raw.split("/", 1)[0])
        if source_primary_name == provider_name:
            return True
    if (
        identity.game == "starwarsunlimited"
        and (source_name, provider_name) in _SWU_REVIEWED_NAME_ALIASES
    ):
        return True
    if identity.game == "riftbound" and "," in identity.cardmarket_name_raw:
        # Cardmarket prefixes champion legend cards with the champion name
        # (for example "Kai'Sa, Daughter of the Void"), while Riot's official
        # gallery uses only the printed legend title ("Daughter of the Void")
        # and labels starter-deck records with an additional "Starter" suffix.
        # This relaxation is intentionally limited to manually reviewed
        # overrides, where the exact provider printing is versioned in YAML.
        source_legend_title = _loose_name(
            identity.cardmarket_name_raw.split(",", 1)[1]
        )
        if source_legend_title == provider_name or (
            provider_name.endswith("starter")
            and source_legend_title == provider_name.removesuffix("starter")
        ):
            return True
    return (
        identity.game == "onepiece"
        and identity.collector_number_canonical == "OP06-101"
        and {source_name, provider_name} == {"nami", "onami"}
    )


def _base_onepiece_number(value: str) -> str:
    return re.sub(r"_(?:p|r|jp)\d+$", "", value, flags=re.IGNORECASE)


def _lorcana_name(card: dict[str, Any]) -> str | None:
    name = _text(card.get("name"))
    version = _text(card.get("version"))
    return f"{name} - {version}" if name and version else name


def _swu_name(card: dict[str, Any]) -> str | None:
    name = _text(card.get("Name"))
    subtitle = _text(card.get("Subtitle"))
    return f"{name}, {subtitle}" if name and subtitle else name


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _today_version() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


def _json_object(raw: bytes) -> dict[str, Any]:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("provider response must be a JSON object")
    return payload


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def _ndjson(records: Any) -> bytes:
    return b"".join(_json_bytes(record) + b"\n" for record in records)
