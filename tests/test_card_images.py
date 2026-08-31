from __future__ import annotations

import gzip
import io
import json
import tarfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from core.r2 import LocalObjectStore
from indexengine.card_images.catalogs import (
    CatalogSnapshot,
    match_catalog_identities,
    parse_apitcg_payload,
    parse_bandai_onepiece_payload,
    parse_digimon_payload,
    parse_lorcast_payload,
    parse_optcg_payload,
    parse_riot_riftbound_page,
    parse_swudb_payload,
    parse_tcgdex_tarball,
)
from indexengine.card_images.contracts import (
    CanonicalCardIdentity,
    CardImageFace,
    ImageVariant,
    PublicCardImage,
    normalize_card_name,
    public_image_from_match,
    source_row_key,
)
from indexengine.card_images.overrides import (
    ManualCardImageOverride,
    load_manual_overrides,
)
from indexengine.card_images.pipeline import (
    _verified_expansion_metadata,
    materialize_magic_images,
)
from indexengine.card_images.policy import ProviderPolicy
from indexengine.card_images.qa import (
    MagicQaCandidate,
    load_manual_reviews,
    select_magic_qa_sample,
)
from indexengine.card_images.readiness import audit_public_collector
from indexengine.card_images.scryfall import (
    ScryfallSnapshot,
    match_magic_identities,
    parse_scryfall_bulk,
    sync_scryfall_snapshot,
)


def _identity(product_id: int = 42, finish: str = "nonfoil") -> CanonicalCardIdentity:
    return CanonicalCardIdentity(
        schema_version=1,
        game="magic",
        subgame=None,
        source_row_key=source_row_key("magic", product_id, finish),
        cardmarket_product_id=product_id,
        cardmarket_name_raw="Delver of Secrets",
        name_normalized=normalize_card_name("Delver of Secrets"),
        set_name_raw=None,
        set_code_raw=None,
        set_code_canonical=None,
        set_provider_id=None,
        collector_number_raw="001a",
        collector_number_canonical="001a",
        language=None,
        finish=finish,  # type: ignore[arg-type]
        source_variant_raw=finish,
        edition=None,
        artwork_variant=None,
        source_updated_at="2026-08-30",
    )


def _policy(state: str = "approved") -> ProviderPolicy:
    return ProviderPolicy(
        provider="scryfall",
        games=("magic",),
        metadata_access="approved",
        artwork_publication=state,  # type: ignore[arg-type]
        may_hotlink=True,
        may_mirror=False,
        attribution_required=True,
        reviewed_at="2026-08-30",
        evidence=("test",),
    )


def _bulk_record(product_id: int = 42, provider_id: str = "scryfall-card") -> dict[str, object]:
    return {
        "id": provider_id,
        "cardmarket_id": product_id,
        "name": "Delver of Secrets",
        "set": "mid",
        "set_name": "Midnight Hunt",
        "collector_number": "001a",
        "lang": "en",
        "layout": "transform",
        "card_faces": [
            {
                "image_uris": {
                    "small": "https://cards.scryfall.io/small/front.jpg",
                    "normal": "https://cards.scryfall.io/normal/front.jpg",
                    "large": "https://cards.scryfall.io/large/front.jpg",
                }
            },
            {
                "image_uris": {
                    "small": "https://cards.scryfall.io/small/back.jpg",
                    "normal": "https://cards.scryfall.io/normal/back.jpg",
                    "large": "https://cards.scryfall.io/large/back.jpg",
                }
            },
        ],
    }


def _snapshot(*records: object) -> ScryfallSnapshot:
    body = gzip.compress(b"".join(json.dumps(record).encode() + b"\n" for record in records))
    normalized = parse_scryfall_bulk(body, "https://data.scryfall.io/default.jsonl.gz")
    return ScryfallSnapshot(
        snapshot_id="scryfall-20260830000000",
        fetched_at="2026-08-30T00:00:00+00:00",
        source_url="https://data.scryfall.io/default.jsonl.gz",
        source_updated_at="2026-08-30T00:00:00+00:00",
        source_etag="test",
        raw_sha256="a" * 64,
        records=tuple(normalized),
    )


def test_source_key_and_identifiers_preserve_strings() -> None:
    identity = _identity()

    assert identity.collector_number_raw == "001a"
    assert identity.source_row_key == source_row_key("magic", 42, "nonfoil")
    assert identity.source_row_key != source_row_key("magic", 42, "foil")
    assert normalize_card_name("  Foo\u2013Bar  ") == "foo-bar"


def test_scryfall_metadata_preserves_set_name() -> None:
    record = parse_scryfall_bulk(
        gzip.compress(json.dumps(_bulk_record()).encode() + b"\n"),
        "https://data.scryfall.io/default.jsonl.gz",
    )[0]
    assert record.set_name == "Midnight Hunt"


def test_scryfall_direct_cardmarket_match_supports_two_faces() -> None:
    matches, assets = match_magic_identities(
        [_identity()],
        _snapshot(_bulk_record()),
        _policy(),
    )

    assert matches[0].status == "exact"
    assert matches[0].match_method == "direct_marketplace_id"
    asset = assets[matches[0].asset_id or ""]
    assert [face.face for face in asset.faces] == ["front", "back"]
    public = public_image_from_match(matches[0], asset)
    assert public.status == "exact"
    assert public.normal_url == "https://cards.scryfall.io/normal/front.jpg"


def test_scryfall_does_not_publish_ambiguous_or_unapproved_matches() -> None:
    duplicate = _bulk_record(provider_id="second-card")
    matches, assets = match_magic_identities(
        [_identity()],
        _snapshot(_bulk_record(), duplicate),
        _policy(),
    )
    assert matches[0].status == "ambiguous"
    assert matches[0].asset_id is None
    assert assets == {}

    approved_matches, approved_assets = match_magic_identities(
        [_identity()],
        _snapshot(_bulk_record()),
        _policy("pending"),
    )
    asset = approved_assets[approved_matches[0].asset_id or ""]
    assert public_image_from_match(approved_matches[0], asset).status == "blocked_legal"


def test_missing_cardmarket_id_is_provider_missing() -> None:
    matches, _ = match_magic_identities([_identity(404)], _snapshot(_bulk_record()), _policy())

    assert matches[0].status == "provider_missing"
    assert matches[0].reason_code == "CM_ID_NOT_FOUND"


def test_readiness_audit_uses_latest_pages_and_marks_synthetic_sets_missing(
    tmp_path: Path,
) -> None:
    collector = tmp_path / "collector"
    page_path = collector / "PKEUCOL" / "composition" / "2026-08-30" / "0001.json"
    page_path.parent.mkdir(parents=True)
    (collector / "index.json").write_text(
        json.dumps(
            {
                "generated_for": "2026-08-30",
                "indexes": [{"code": "PKEUCOL", "game_key": "pokemon"}],
            }
        )
    )
    (collector / "PKEUCOL" / "composition.json").write_text(
        json.dumps(
            {
                "rebalances": [
                    {
                        "effective_date": "2026-08-30",
                        "pages": [
                            {
                                "page": 1,
                                "path": "composition/2026-08-30/0001.json",
                            }
                        ],
                    }
                ]
            }
        )
    )
    page_path.write_text(
        json.dumps(
            {
                "constituents": [
                    {
                        "cm_product_id": 7,
                        "variant_key": "nonfoil",
                        "name": "Pikachu",
                        "set_name": "Expansion 123",
                        "collector_number": None,
                        "metadata_status": "catalogue_only",
                    }
                ]
            }
        )
    )

    result = audit_public_collector(collector, tmp_path / "reports")

    assert result.games[0].with_set_name == 0
    assert result.games[0].missing_prerequisite == 1
    missing = (tmp_path / "reports/missing-prerequisites.csv").read_text()
    assert "set_code,collector_number" in missing
    all_rows = (tmp_path / "reports/all-rows.csv").read_text()
    assert "image_status,has_public_image_url" in all_rows
    assert "not_materialized,false" in all_rows


def test_public_card_image_defaults_to_machine_readable_disabled_status() -> None:
    image = PublicCardImage(status="disabled")

    assert image.to_dict()["status"] == "disabled"
    assert image.normal_url is None


def test_materialization_refreshes_latest_metadata_summary(tmp_path: Path) -> None:
    source_data = tmp_path / "source-data"
    collector = source_data / "collector"
    index_root = collector / "YGEUCOL"
    page = index_root / "composition" / "2026-08-30" / "0001.json"
    page.parent.mkdir(parents=True)

    def write(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))

    identity = {
        "schema_version": 2,
        "series_id": "YGEUCOL:1.5.0-preview.2:private_shadow",
        "index_code": "YGEUCOL",
        "methodology_version": "1.5.0-preview.2",
        "data_state": "private_shadow",
        "publication_state": "preview_noindex",
        "generated_for": "2026-08-30",
    }
    member = {
        "cm_product_id": 7,
        "variant_key": "nonfoil",
        "stable_variant_id": "cardmarket:yugioh:product:7:nonfoil",
        "selection_price": 42.0,
        "name": "Chaos Nephthys",
        "set_name": "Expansion 123",
        "collector_number": None,
        "image": {"status": "disabled"},
        "image_url": None,
        "image_source": None,
    }
    write(
        collector / "index.json",
        {
            "schema_version": 1,
            "generated_for": "2026-08-30",
            "methodology_version": "1.5.0-preview.2",
            "indexes": [
                {
                    "code": "YGEUCOL",
                    "game_key": "yugioh",
                    "constituent_count": 1,
                }
            ],
        },
    )
    write(index_root / "manifest.json", {**identity, "outputs": {}})
    write(
        index_root / "summary.json",
        {
            **identity,
            "base_value": 1000.0,
            "product_metadata": {
                "constituent_count": 1,
                "named_count": 1,
                "set_name_count": 1,
                "collector_number_count": 0,
                "image_count": 0,
                "image_status_counts": {"disabled": 1},
            },
        },
    )
    write(index_root / "history.json", identity)
    write(index_root / "diagnostics.json", identity)
    write(
        index_root / "rebalances.json",
        {
            **identity,
            "rebalances": [
                {
                    "effective_date": "2026-08-30",
                    "selection_as_of": "2026-08-29",
                    "active_count": 1,
                    "constituents": [],
                }
            ],
        },
    )
    write(
        index_root / "composition.json",
        {
            **identity,
            "rebalances": [
                {
                    "effective_date": "2026-08-30",
                    "selection_as_of": "2026-08-29",
                    "active_count": 1,
                    "pages": [
                        {
                            "page": 1,
                            "path": "composition/2026-08-30/0001.json",
                        }
                    ],
                }
            ],
        },
    )
    write(
        page,
        {
            **identity,
            "effective_date": "2026-08-30",
            "page": 1,
            "page_count": 1,
            "constituents": [member],
        },
    )

    image = PublicCardImage(
        status="exact",
        provider="ygoprodeck",
        match_method="inferred_set_name_unique",
        front=CardImageFace(
            face="front",
            thumb=None,
            normal=ImageVariant(
                "https://example.test/chaos-nephthys.jpg",
                421,
                614,
                "image/jpeg",
            ),
            large=None,
        ),
        verified_at="2026-08-30T00:00:00Z",
    )
    store = LocalObjectStore(tmp_path / "store")
    store.write_bytes(
        "derived/card-images/yugioh/public-manifest.json",
        json.dumps(
            {
                "schema_version": 1,
                "game": "yugioh",
                "rows": [
                    {
                        "cardmarket_product_id": 7,
                        "finish": "nonfoil",
                        "set_name": "Battle of Chaos",
                        "collector_number": "BACH-EN025",
                        "image": image.to_dict(),
                    }
                ],
            }
        ).encode(),
        "application/json",
    )

    materialize_magic_images(store, source_data)

    summary = json.loads((index_root / "summary.json").read_text())
    assert summary["product_metadata"] == {
        "collector_number_count": 1,
        "constituent_count": 1,
        "image_count": 1,
        "image_status_counts": {"exact": 1},
        "named_count": 1,
        "set_name_count": 1,
    }
    projected = json.loads(page.read_text())["constituents"][0]
    assert projected["set_name"] == "Battle of Chaos"
    assert projected["collector_number"] == "BACH-EN025"
    assert projected["image_source"] == "ygoprodeck"


def test_verified_expansion_metadata_rejects_conflicting_provider_evidence() -> None:
    assert _verified_expansion_metadata(
        {
            10: {("Base Set", "base1")},
            20: {("Base Set", "base1"), ("Celebrations", "cel25")},
        }
    ) == {10: ("Base Set", "base1")}


def test_tcgdex_snapshot_preserves_direct_cardmarket_and_expansion_ids() -> None:
    archive_body = io.BytesIO()
    with tarfile.open(fileobj=archive_body, mode="w:gz") as archive:
        files = {
            "repo/data/Base.ts": 'const series = { id: "base" }',
            "repo/data/Base/Test Set.ts": (
                'const set = { id: "base-test", name: { en: "Test Set" }, '
                "thirdParty: { cardmarket: 1234 } }"
            ),
            "repo/data/Base/Test Set/001.ts": (
                'const card = { name: { en: "Pikachu" }, variants: ['
                "{ thirdParty: { cardmarket: 9876 } }] }"
            ),
            "repo/data/Base/Test Set/002.ts": (
                'const card = { name: { en: "Raichu" }, variants: [] }'
            ),
            "repo/data-asia/SM.ts": 'const series = { id: "sm" }',
            "repo/data-asia/SM/SM12a.ts": (
                'const set = { id: "SM12a", name: { ja: "タッグオールスターズ" }, '
                "thirdParty: { cardmarket: 3776 } }"
            ),
            "repo/data-asia/SM/SM12a/186.ts": (
                'const card = { name: { ja: "トゲピー&ピィ&ププリンGX" }, variants: ['
                "{ thirdParty: { cardmarket: 544676 } }] }"
            ),
        }
        for name, body in files.items():
            encoded = body.encode()
            member = tarfile.TarInfo(name)
            member.size = len(encoded)
            archive.addfile(member, io.BytesIO(encoded))

    asset_manifest = json.dumps(
        {"en": {"base": {"base-test": {"001": "checksum"}}}}
    ).encode()
    pokemon_tcg_body = io.BytesIO()
    with tarfile.open(fileobj=pokemon_tcg_body, mode="w:gz") as archive:
        pokemon_tcg_files = {
            "repo/sets/en.json": json.dumps(
                [{"id": "base-test-api", "name": "Test Set"}]
            ),
            "repo/cards/en/base-test-api.json": json.dumps(
                [
                    {
                        "id": "base-test-api-42",
                        "name": "Raichu",
                        "number": "42",
                        "images": {
                            "small": "https://images.pokemontcg.io/base-test-api/42.png",
                            "large": "https://images.pokemontcg.io/base-test-api/42_hires.png",
                        },
                    }
                ]
            ),
        }
        for name, body in pokemon_tcg_files.items():
            encoded = body.encode()
            member = tarfile.TarInfo(name)
            member.size = len(encoded)
            archive.addfile(member, io.BytesIO(encoded))
    records = parse_tcgdex_tarball(
        archive_body.getvalue(),
        asset_manifest=asset_manifest,
        pokemon_tcg_raw=pokemon_tcg_body.getvalue(),
        pokemon_tcg_verification=json.dumps(
            {
                "https://images.pokemontcg.io/base-test-api/42_hires.png": (
                    "https://images.pokemontcg.io/base-test-api/42.png"
                )
            }
        ).encode(),
    )

    assert len(records) == 3
    by_number = {record.collector_number: record for record in records}
    assert by_number["001"].cardmarket_id == 9876
    assert by_number["001"].cardmarket_expansion_id == 1234
    assert by_number["001"].set_name == "Test Set"
    assert by_number["001"].faces[0].normal.url == (
        "https://assets.tcgdex.net/en/base/base-test/001/high.webp"
    )
    assert by_number["001"].faces[0].thumb.url == (
        "https://assets.tcgdex.net/en/base/base-test/001/low.webp"
    )
    assert by_number["002"].cardmarket_id is None
    assert by_number["002"].cardmarket_expansion_id == 1234
    assert by_number["002"].set_name == "Test Set"
    assert by_number["002"].faces[0].normal.url == (
        "https://images.pokemontcg.io/base-test-api/42.png"
    )
    assert by_number["186"].cardmarket_id == 544676
    assert by_number["186"].cardmarket_expansion_id == 3776
    assert by_number["186"].set_code == "SM12a"
    assert by_number["186"].set_name == "タッグオールスターズ"
    assert by_number["186"].language == "ja"
    assert by_number["186"].faces == ()


def test_catalog_matcher_uses_unique_complete_name_and_rejects_reprints() -> None:
    cards = {
        "cards": [
            {
                "id": "one",
                "name": "Elsa",
                "version": "Spirit of Winter",
                "collector_number": "207",
                "lang": "en",
                "rarity": "Enchanted",
                "set": {"code": "1", "name": "The First Chapter"},
                "image_uris": {
                    "digital": {
                        "normal": "https://cards.lorcast.io/card/one.avif",
                        "small": "https://cards.lorcast.io/card/one-small.avif",
                        "large": "https://cards.lorcast.io/card/one-large.avif",
                    }
                },
            }
        ]
    }
    records = parse_lorcast_payload(json.dumps(cards).encode())
    snapshot = CatalogSnapshot(
        provider="lorcast",
        game="lorcana",
        snapshot_id="lorcast-test",
        fetched_at="2026-08-30T00:00:00+00:00",
        source_url="https://api.lorcast.com/v0/sets",
        source_version="test",
        raw_sha256="a" * 64,
        records=tuple(records),
    )
    identity = replace(
        _identity(),
        game="lorcana",
        source_row_key=source_row_key("lorcana", 42, "nonfoil"),
        cardmarket_name_raw="Elsa - Spirit of Winter",
        name_normalized=normalize_card_name("Elsa - Spirit of Winter"),
        collector_number_raw=None,
        collector_number_canonical=None,
    )
    policy = replace(_policy(), provider="lorcast", games=("lorcana",))

    matches, assets = match_catalog_identities([identity], snapshot, policy)
    assert matches[0].status == "exact"
    assert matches[0].match_method == "name_candidate_only"
    assert len(assets) == 1

    reprint = replace(
        records[0],
        provider_card_id="two",
        set_code="2",
        set_name="Rise of the Floodborn",
        collector_number="209",
    )
    duplicate_snapshot = replace(snapshot, records=(records[0], reprint))
    duplicate_matches, _ = match_catalog_identities([identity], duplicate_snapshot, policy)
    assert duplicate_matches[0].status == "ambiguous"


def test_catalog_matcher_uses_explicit_set_name_for_unique_card_name() -> None:
    records = parse_lorcast_payload(
        json.dumps(
            {
                "cards": [
                    {
                        "id": "test-pikachu",
                        "name": "Pikachu",
                        "collector_number": "001",
                        "lang": "en",
                        "set": {"code": "test", "name": "Test Set"},
                        "image_uris": {
                            "digital": {"normal": "https://cards.example/pikachu.avif"}
                        },
                    }
                ]
            }
        ).encode()
    )
    snapshot = CatalogSnapshot(
        provider="tcgdex",
        game="pokemon",
        snapshot_id="tcgdex-set-name-test",
        fetched_at="2026-08-30T00:00:00+00:00",
        source_url="https://example.test/tcgdex",
        source_version="test",
        raw_sha256="a" * 64,
        records=tuple(records),
    )
    identity = replace(
        _identity(),
        game="pokemon",
        source_row_key=source_row_key("pokemon", 42, "nonfoil"),
        cardmarket_name_raw="Pikachu [Tackle]",
        name_normalized=normalize_card_name("Pikachu [Tackle]"),
        set_name_raw="Test Set",
        set_code_raw="test",
        set_code_canonical="test",
        set_provider_id=None,
        collector_number_raw=None,
        collector_number_canonical=None,
    )
    policy = replace(_policy(), provider="tcgdex", games=("pokemon",))

    matches, _ = match_catalog_identities([identity], snapshot, policy)

    assert matches[0].status == "exact"
    assert matches[0].match_method == "set_name_name_unique"
    assert matches[0].provider_card_id == "test-pikachu"


def test_catalog_matcher_infers_set_only_from_corroborated_expansion_signature() -> None:
    cards = {
        "cards": [
            {
                "id": card_id,
                "name": name,
                "collector_number": number,
                "lang": "en",
                "set": {"code": set_code, "name": set_name},
                "image_uris": {
                    "digital": {"normal": f"https://cards.lorcast.io/card/{card_id}.avif"}
                },
            }
            for card_id, name, number, set_code, set_name in (
                ("a-hero", "Hero", "1", "A", "Alpha"),
                ("a-ally", "Ally", "2", "A", "Alpha"),
                ("a-spell", "Spell", "3", "A", "Alpha"),
                ("b-hero", "Hero", "1", "B", "Beta"),
                ("b-other", "Other", "2", "B", "Beta"),
            )
        ]
    }
    records = parse_lorcast_payload(json.dumps(cards).encode())
    snapshot = CatalogSnapshot(
        provider="lorcast",
        game="lorcana",
        snapshot_id="lorcast-signature-test",
        fetched_at="2026-08-30T00:00:00+00:00",
        source_url="https://api.lorcast.com/v0/cards",
        source_version="test",
        raw_sha256="b" * 64,
        records=tuple(records),
    )
    identities = [
        replace(
            _identity(),
            game="lorcana",
            source_row_key=source_row_key("lorcana", product_id, "nonfoil"),
            cardmarket_product_id=product_id,
            cardmarket_name_raw=name,
            name_normalized=normalize_card_name(name),
            set_provider_id="9001",
            collector_number_raw=None,
            collector_number_canonical=None,
        )
        for product_id, name in ((101, "Hero"), (102, "Ally"), (103, "Spell"))
    ]
    policy = replace(_policy(), provider="lorcast", games=("lorcana",))

    matches, _ = match_catalog_identities(identities, snapshot, policy)

    assert {match.status for match in matches} == {"exact"}
    assert {match.match_method for match in matches} == {"inferred_set_name_unique"}
    assert {match.provider_card_id for match in matches} == {"a-hero", "a-ally", "a-spell"}


def test_catalog_matcher_uses_full_marketplace_set_basket_for_sparse_index() -> None:
    cards = {
        "cards": [
            {
                "id": card_id,
                "name": name,
                "collector_number": number,
                "lang": "en",
                "set": {"code": set_code, "name": set_name},
                "image_uris": {
                    "digital": {"normal": f"https://cards.lorcast.io/card/{card_id}.avif"}
                },
            }
            for card_id, name, number, set_code, set_name in (
                ("a-hero", "Hero", "A-001", "A-001", "Alpha"),
                ("a-ally", "Ally", "A-002", "A-002", "Alpha"),
                ("a-spell", "Spell", "A-003", "A-003", "Alpha"),
                ("b-hero", "Hero", "B-001", "B-001", "Beta"),
                ("b-other", "Other", "B-002", "B-002", "Beta"),
            )
        ]
    }
    # Model YGOPRODeck, whose set_code is a card-level printing number. Set
    # inference therefore has to group by set_name rather than by set_code.
    records = tuple(
        replace(record, provider="ygoprodeck")
        for record in parse_lorcast_payload(json.dumps(cards).encode())
    )
    snapshot = CatalogSnapshot(
        provider="ygoprodeck",
        game="yugioh",
        snapshot_id="ygoprodeck-signature-test",
        fetched_at="2026-08-30T00:00:00+00:00",
        source_url="https://db.ygoprodeck.com/api/v7/cardinfo.php",
        source_version="test",
        raw_sha256="c" * 64,
        records=records,
    )
    identity = replace(
        _identity(),
        game="yugioh",
        source_row_key=source_row_key("yugioh", 101, "nonfoil"),
        cardmarket_product_id=101,
        cardmarket_name_raw="Hero",
        name_normalized=normalize_card_name("Hero"),
        set_provider_id="9001",
        collector_number_raw=None,
        collector_number_canonical=None,
    )
    policy = replace(_policy(), provider="ygoprodeck", games=("yugioh",))

    matches, _ = match_catalog_identities(
        [identity],
        snapshot,
        policy,
        marketplace_set_names={9001: ("Hero", "Ally", "Spell")},
    )

    assert matches[0].status == "exact"
    assert matches[0].match_method == "inferred_set_name_unique"
    assert matches[0].provider_card_id == "a-hero"


def test_catalog_matcher_accepts_provider_complete_parallel_heavy_set() -> None:
    provider_names = [f"Card {index}" for index in range(1, 11)]
    cards = {
        "cards": [
            {
                "id": f"a-{index}",
                "name": name,
                "collector_number": f"A-{index:03d}",
                "lang": "en",
                "set": {"code": f"A-{index:03d}", "name": "Alpha"},
                "image_uris": {
                    "digital": {"normal": f"https://cards.example/a-{index}.avif"}
                },
            }
            for index, name in enumerate(provider_names, start=1)
        ]
        + [
            {
                "id": f"b-{index}",
                "name": f"Card {index}",
                "collector_number": f"B-{index:03d}",
                "lang": "en",
                "set": {"code": f"B-{index:03d}", "name": "Beta"},
                "image_uris": {
                    "digital": {"normal": f"https://cards.example/b-{index}.avif"}
                },
            }
            for index in range(1, 4)
        ],
    }
    records = tuple(
        replace(record, provider="ygoprodeck")
        for record in parse_lorcast_payload(json.dumps(cards).encode())
    )
    snapshot = CatalogSnapshot(
        provider="ygoprodeck",
        game="yugioh",
        snapshot_id="ygoprodeck-provider-coverage-test",
        fetched_at="2026-08-30T00:00:00+00:00",
        source_url="https://db.ygoprodeck.com/api/v7/cardinfo.php",
        source_version="test",
        raw_sha256="e" * 64,
        records=records,
    )
    identity = replace(
        _identity(),
        game="yugioh",
        source_row_key=source_row_key("yugioh", 101, "nonfoil"),
        cardmarket_product_id=101,
        cardmarket_name_raw="Card 8",
        name_normalized=normalize_card_name("Card 8"),
        set_provider_id="9001",
        collector_number_raw=None,
        collector_number_canonical=None,
    )
    marketplace_names = tuple(provider_names[:8]) + tuple(
        f"Parallel {index}" for index in range(1, 13)
    )

    matches, _ = match_catalog_identities(
        [identity],
        snapshot,
        replace(_policy(), provider="ygoprodeck", games=("yugioh",)),
        marketplace_set_names={9001: marketplace_names},
    )

    assert matches[0].status == "exact"
    assert matches[0].match_method == "inferred_set_name_unique"
    assert matches[0].provider_card_id == "a-8"


def test_catalog_matcher_reuses_unanimous_direct_product_set_mapping() -> None:
    cards = {
        "cards": [
            {
                "id": card_id,
                "name": name,
                "collector_number": number,
                "lang": "en",
                "set": {"code": set_code, "name": set_name},
                "image_uris": {
                    "digital": {"normal": f"https://cards.lorcast.io/card/{card_id}.avif"}
                },
            }
            for card_id, name, number, set_code, set_name in (
                ("a-hero", "Hero", "1", "A", "Alpha"),
                ("a-ally", "Ally", "2", "A", "Alpha"),
                ("b-ally", "Ally", "2", "B", "Beta"),
            )
        ]
    }
    parsed = parse_lorcast_payload(json.dumps(cards).encode())
    records = tuple(
        replace(record, cardmarket_id=101 if record.provider_card_id == "a-hero" else None)
        for record in parsed
    )
    snapshot = CatalogSnapshot(
        provider="lorcast",
        game="lorcana",
        snapshot_id="lorcast-direct-set-test",
        fetched_at="2026-08-30T00:00:00+00:00",
        source_url="https://api.lorcast.com/v0/cards",
        source_version="test",
        raw_sha256="d" * 64,
        records=records,
    )
    identities = [
        replace(
            _identity(),
            game="lorcana",
            source_row_key=source_row_key("lorcana", product_id, "nonfoil"),
            cardmarket_product_id=product_id,
            cardmarket_name_raw=name,
            name_normalized=normalize_card_name(name),
            set_provider_id="9001",
            collector_number_raw=None,
            collector_number_canonical=None,
        )
        for product_id, name in ((101, "Hero"), (102, "Ally"))
    ]
    policy = replace(_policy(), provider="lorcast", games=("lorcana",))

    matches, _ = match_catalog_identities(identities, snapshot, policy)

    assert {match.status for match in matches} == {"exact"}
    by_product = {
        identity.cardmarket_product_id: match
        for identity, match in zip(identities, matches, strict=True)
    }
    assert by_product[101].match_method == "direct_marketplace_id"
    assert by_product[102].match_method == "inferred_set_name_unique"
    assert by_product[102].provider_card_id == "a-ally"


def test_credentialed_provider_parsers_preserve_printing_numbers_and_images() -> None:
    one_piece = parse_optcg_payload(
        json.dumps(
            [
                {
                    "id": "OP01-001_p1",
                    "name": "Roronoa Zoro",
                    "variant_type": "alt_art",
                    "image_url": "https://provider.example/OP01-001_p1.png",
                    "sets": [{"id": "OP-01", "label": "Romance Dawn"}],
                }
            ]
        ).encode()
    )[0]
    assert one_piece.collector_number == "OP01-001"
    assert one_piece.provider_art_id == "OP01-001_p1"

    dragon_ball = parse_apitcg_payload(
        json.dumps(
            {
                "products": [
                    {
                        "_id": 123,
                        "_subgame": "dragon-ball-super-fusion-world",
                        "name": "Son Goku",
                        "code": "FB04-059",
                        "set": {"code": "FB04", "name": "Ultra Limit"},
                        "images": [
                            {"medium": "https://provider.example/FB04-059.jpg"}
                        ],
                    }
                ]
            }
        ).encode()
    )[0]
    assert dragon_ball.collector_number == "FB04-059"
    assert dragon_ball.set_name == "Ultra Limit"


def test_bandai_onepiece_parser_preserves_art_variant_and_base_number() -> None:
    record = parse_bandai_onepiece_payload(
        json.dumps(
            {
                "cards": [
                    {
                        "id": "OP17-001_p1",
                        "name": "Monkey.D.Luffy",
                        "set_code": "OP-17",
                        "set_name": "[OP-17] Carrying On His Will",
                        "variant": "p1",
                        "image_url": "https://en.onepiece-cardgame.com/images/card.png",
                    }
                ]
            }
        ).encode()
    )[0]

    assert record.collector_number == "OP17-001"
    assert record.provider_art_id == "OP17-001_p1"
    assert record.variant_raw == "p1"
    assert record.faces[0].normal.url.endswith("/images/card.png")


def test_manual_override_publishes_only_the_reviewed_provider_art() -> None:
    record = parse_bandai_onepiece_payload(
        json.dumps(
            {
                "cards": [
                    {
                        "id": "OP17-001_p1",
                        "name": "Monkey.D.Luffy",
                        "set_code": "OP-17",
                        "set_name": "[OP-17] Carrying On His Will",
                        "variant": "p1",
                        "image_url": "https://en.onepiece-cardgame.com/images/card.png",
                    }
                ]
            }
        ).encode()
    )[0]
    snapshot = CatalogSnapshot(
        provider="bandai_onepiece",
        game="onepiece",
        snapshot_id="bandai-onepiece-test",
        fetched_at="2026-08-30T00:00:00+00:00",
        source_url="https://en.onepiece-cardgame.com/cardlist/",
        source_version="test",
        raw_sha256="f" * 64,
        records=(record,),
    )
    identity = replace(
        _identity(product_id=99),
        game="onepiece",
        source_row_key=source_row_key("onepiece", 99, "nonfoil"),
        cardmarket_product_id=99,
        cardmarket_name_raw="Monkey.D.Luffy",
        name_normalized=normalize_card_name("Monkey.D.Luffy"),
        collector_number_raw="OP17-001",
        collector_number_canonical="OP17-001",
    )
    override = ManualCardImageOverride(
        source_row_key=identity.source_row_key,
        game="onepiece",
        cardmarket_product_id=99,
        finish="nonfoil",
        provider="bandai_onepiece",
        provider_card_id="OP17-001_p1",
        provider_art_id="OP17-001_p1",
        reviewed_at="2026-08-30",
        evidence=("reviewed against the exact Cardmarket product",),
    )
    policy = replace(
        _policy(),
        provider="bandai_onepiece",
        games=("onepiece",),
    )

    matches, assets = match_catalog_identities(
        [identity],
        snapshot,
        policy,
        manual_overrides={identity.source_row_key: override},
    )

    assert matches[0].status == "manual"
    assert matches[0].match_method == "manual_override"
    assert matches[0].provider_art_id == "OP17-001_p1"
    assert matches[0].asset_id in assets


def test_manual_override_accepts_verified_onepiece_nami_alias() -> None:
    record = parse_bandai_onepiece_payload(
        json.dumps(
            {
                "cards": [
                    {
                        "id": "OP06-101_p3",
                        "name": "O-Nami",
                        "set_code": "OP-06",
                        "set_name": "[OP-06] Wings of the Captain",
                        "variant": "p3",
                        "image_url": "https://en.onepiece-cardgame.com/images/nami.png",
                    }
                ]
            }
        ).encode()
    )[0]
    snapshot = CatalogSnapshot(
        provider="bandai_onepiece",
        game="onepiece",
        snapshot_id="bandai-onepiece-nami-alias",
        fetched_at="2026-08-30T00:00:00+00:00",
        source_url="https://en.onepiece-cardgame.com/cardlist/",
        source_version="test",
        raw_sha256="f" * 64,
        records=(record,),
    )
    identity = replace(
        _identity(product_id=99),
        game="onepiece",
        source_row_key=source_row_key("onepiece", 99, "nonfoil"),
        cardmarket_product_id=99,
        cardmarket_name_raw="Nami",
        name_normalized=normalize_card_name("Nami"),
        collector_number_raw="OP06-101",
        collector_number_canonical="OP06-101",
    )
    override = ManualCardImageOverride(
        source_row_key=identity.source_row_key,
        game="onepiece",
        cardmarket_product_id=99,
        finish="nonfoil",
        provider="bandai_onepiece",
        provider_card_id="OP06-101_p3",
        provider_art_id="OP06-101_p3",
        reviewed_at="2026-08-31",
        evidence=("reviewed against the exact Cardmarket product",),
    )
    policy = replace(_policy(), provider="bandai_onepiece", games=("onepiece",))

    matches, assets = match_catalog_identities(
        [identity], snapshot, policy, manual_overrides={identity.source_row_key: override}
    )

    assert matches[0].status == "manual"
    assert matches[0].provider_art_id == "OP06-101_p3"
    assert matches[0].asset_id in assets


@pytest.mark.parametrize(
    ("cardmarket_name", "provider_name", "number"),
    (
        ("Diaboromon Ace", "Diaboromon", "P-114"),
        (
            "ShineGreymon: Burst Mode / Final Shining Burst",
            "ShineGreymon: Burst Mode",
            "BT25-104",
        ),
    ),
)
def test_manual_override_accepts_verified_digimon_name_aliases(
    cardmarket_name: str, provider_name: str, number: str
) -> None:
    record = parse_digimon_payload(
        json.dumps([{"id": number, "name": provider_name, "set_name": []}]).encode()
    )[0]
    snapshot = CatalogSnapshot(
        provider="digimon",
        game="digimon",
        snapshot_id="digimon-name-alias",
        fetched_at="2026-08-30T00:00:00+00:00",
        source_url="https://digimoncard.io/",
        source_version="test",
        raw_sha256="f" * 64,
        records=(record,),
    )
    identity = replace(
        _identity(product_id=99),
        game="digimon",
        source_row_key=source_row_key("digimon", 99, "nonfoil"),
        cardmarket_product_id=99,
        cardmarket_name_raw=cardmarket_name,
        name_normalized=normalize_card_name(cardmarket_name),
        collector_number_raw=number,
        collector_number_canonical=number,
    )
    override = ManualCardImageOverride(
        source_row_key=identity.source_row_key,
        game="digimon",
        cardmarket_product_id=99,
        finish="nonfoil",
        provider="digimon",
        provider_card_id=number,
        provider_art_id=None,
        reviewed_at="2026-08-31",
        evidence=("reviewed against the exact Cardmarket product",),
    )
    policy = replace(_policy(), provider="digimon", games=("digimon",))

    matches, assets = match_catalog_identities(
        [identity], snapshot, policy, manual_overrides={identity.source_row_key: override}
    )

    assert matches[0].status == "manual"
    assert matches[0].provider_card_id == number
    assert matches[0].asset_id in assets


@pytest.mark.parametrize(
    ("cardmarket_name", "provider_name"),
    (
        ("Count Dooku, Darth Tyranus", "Count Dooku, Darth Tyrannus"),
        ("C-3PO, Anything I Might Do?", "C-3P0, Anything I Might Do?"),
        ("Iden Versio, Inferno Squad Commander", "Iden Versio, Infero Squad Commander"),
        ("Security Complex", "Security Complex, Scarif"),
        ("Energy Conversion Lab", "Energy Conversion Lab, Eadu"),
        ("Tarkintown", "Tarkintown, Lothal"),
        ("Jabba the Hutt, His High Exaltedness", "Jabba the Hutt, His High Exaltdeness"),
        ("Petranaki Arena", "Petranaki Arena, Geonosis"),
        ("Data Vault", "Data Vault, Scarif"),
        ("Poe Dameron, One Hell of a Pilot", "Poe Dameron, One Hell of a a Pilot"),
        ("Theed Palace", "Theed Palace, Naboo"),
        ("Shield Generator Complex", "Shield Generator Complex, Endor"),
        ("Mos Eisley", "Mos Eisley, Tatooine"),
        ("Massassi Temple", "Massassi Temple, Yavin 4"),
        ("C-3PO, Human-Cyborg Relations", "C-3P0, Human-Cyborg Relations"),
        ("Enfys Nest, Until We Can Go No Higher", "Enfy Nest, Until We Can Go No Higher"),
        ("K-2SO, Locking the Vault", "K-2S0, Locking the Vault"),
    ),
)
def test_manual_override_accepts_reviewed_swu_name_aliases(
    cardmarket_name: str, provider_name: str
) -> None:
    record = parse_swudb_payload(
        json.dumps(
            {
                "cards": [
                    {
                        "Name": provider_name,
                        "Set": "TST",
                        "Number": "001",
                        "FrontArt": "https://cdn.swu-db.com/images/cards/TST/001.png",
                    }
                ]
            }
        ).encode()
    )[0]
    snapshot = CatalogSnapshot(
        provider="swudb",
        game="starwarsunlimited",
        snapshot_id="swudb-reviewed-name-alias",
        fetched_at="2026-08-31T00:00:00+00:00",
        source_url="https://www.swu-db.com/api",
        source_version="test",
        raw_sha256="f" * 64,
        records=(record,),
    )
    identity = replace(
        _identity(product_id=99),
        game="starwarsunlimited",
        source_row_key=source_row_key("starwarsunlimited", 99, "nonfoil"),
        cardmarket_product_id=99,
        cardmarket_name_raw=cardmarket_name,
        name_normalized=normalize_card_name(cardmarket_name),
        collector_number_raw=None,
        collector_number_canonical=None,
    )
    override = ManualCardImageOverride(
        source_row_key=identity.source_row_key,
        game="starwarsunlimited",
        cardmarket_product_id=99,
        finish="nonfoil",
        provider="swudb",
        provider_card_id="TST-001",
        provider_art_id=None,
        reviewed_at="2026-08-31",
        evidence=("reviewed against the exact Cardmarket product",),
    )
    policy = replace(_policy(), provider="swudb", games=("starwarsunlimited",))

    matches, assets = match_catalog_identities(
        [identity], snapshot, policy, manual_overrides={identity.source_row_key: override}
    )

    assert matches[0].status == "manual"
    assert matches[0].provider_card_id == "TST-001"
    assert matches[0].asset_id in assets


def test_manual_override_loader_derives_keys_and_rejects_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "overrides.yaml"
    mapping = (
        "  - game: onepiece\n"
        "    cardmarket_product_id: 99\n"
        "    finish: nonfoil\n"
        "    provider: bandai_onepiece\n"
        "    provider_card_id: OP17-001_p1\n"
        "    provider_art_id: OP17-001_p1\n"
        "    reviewed_at: '2026-08-30'\n"
        "    evidence:\n"
        "      - reviewed against the exact Cardmarket product\n"
    )
    path.write_text("version: 1\nmappings:\n" + mapping)

    loaded = load_manual_overrides(path)
    key = (source_row_key("onepiece", 99, "nonfoil"), "bandai_onepiece")
    assert loaded[key].provider_art_id == "OP17-001_p1"

    path.write_text("version: 1\nmappings:\n" + mapping + mapping)
    with pytest.raises(ValueError, match="duplicate manual override"):
        load_manual_overrides(path)


def test_reviewed_lorcana_overrides_exclude_the_pre_errata_stitch_print() -> None:
    overrides = load_manual_overrides(
        Path("packages/indexengine/config/card-images/overrides.yaml")
    )
    lorcana = {
        key: override
        for key, override in overrides.items()
        if override.game == "lorcana"
    }

    assert len(lorcana) == 342
    assert all(override.provider == "lorcast" for override in lorcana.values())
    assert not any(
        override.cardmarket_product_id == 832576 for override in lorcana.values()
    )


def test_reviewed_swu_overrides_include_only_visually_confirmed_artworks() -> None:
    overrides = load_manual_overrides(
        Path("packages/indexengine/config/card-images/overrides.yaml")
    )
    swu = {
        key: override
        for key, override in overrides.items()
        if override.game == "starwarsunlimited"
    }

    assert len(swu) == 636
    assert len({override.cardmarket_product_id for override in swu.values()}) == 574
    assert all(override.provider == "swudb" for override in swu.values())
    excluded_products = {
        815864,  # Annihilator: provider image is a different presentation.
        815900,  # Annihilator: provider image is a different presentation.
        815907,  # Executor: provider image does not match the Cardmarket image side.
        848227,  # No matching provider artwork in the active P25 snapshot.
        857161,  # No matching provider artwork in the active SEC snapshot.
        882842,  # No matching provider artwork in the active P26 snapshot.
        882847,  # No matching provider artwork in the active P26 snapshot.
        # Organized-play products whose Cardmarket artwork differs from every
        # reachable same-name printing in the active SWUDB snapshot.
        795084,
        795085,
        795086,
        795087,
        795088,
        795090,
        800800,
        804737,
        804739,
        804740,
        804741,
        804742,
        # Missing-provider rows whose closest names are absent or whose
        # available artwork was visually different.
        804735,
        814028,
        814029,
        814030,
        814031,
        814032,
        814033,
        833317,
        838354,
        838355,
        838356,
        838357,
        882844,
    }
    assert not excluded_products & {
        override.cardmarket_product_id for override in swu.values()
    }


def test_riot_riftbound_parser_uses_official_number_set_and_image() -> None:
    page = {
        "props": {
            "pageProps": {
                "page": {
                    "blades": [
                        {
                            "cards": {
                                "items": [
                                    {
                                        "id": "unl-131-219",
                                        "collectorNumber": 131,
                                        "name": "Abandon",
                                        "publicCode": "UNL-131/219",
                                        "set": {
                                            "value": {"id": "UNL", "label": "Unleashed"}
                                        },
                                        "rarity": {"value": {"label": "Uncommon"}},
                                        "cardImage": {
                                            "url": "https://cmsassets.rgpub.io/card.png",
                                            "mimeType": "image/png",
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            }
        }
    }
    raw = (
        '<html><script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(page)
        + "</script></html>"
    ).encode()

    record = parse_riot_riftbound_page(raw)[0]

    assert record.provider_card_id == "unl-131-219"
    assert record.set_code == "UNL"
    assert record.set_name == "Unleashed"
    assert record.collector_number == "UNL-131/219"
    assert record.faces[0].normal.url == "https://cmsassets.rgpub.io/card.png"


def test_reviewed_riftbound_variant_overrides_preserve_version_order() -> None:
    overrides = load_manual_overrides(
        Path("packages/indexengine/config/card-images/overrides.yaml")
    )
    riftbound = {
        key: override
        for key, override in overrides.items()
        if override.game == "riftbound"
    }

    assert len(riftbound) == 179
    assert len({override.cardmarket_product_id for override in riftbound.values()}) == 112
    assert all(override.provider == "riot_riftbound" for override in riftbound.values())

    product_to_printing = {
        override.cardmarket_product_id: override.provider_card_id
        for override in riftbound.values()
    }
    assert product_to_printing[847156] == "ogn-039-298"
    assert product_to_printing[847157] == "ogn-039a-298"
    assert product_to_printing[866785] == "sfd-057-221"
    assert product_to_printing[866786] == "sfd-057a-221"
    assert product_to_printing[866972] == "sfd-225-221"
    assert product_to_printing[867004] == "sfd-225-star-221"
    assert product_to_printing[884131] == "unl-147-219"
    assert product_to_printing[884132] == "unl-147a-219"
    assert product_to_printing[884237] == "unl-238-219"
    assert product_to_printing[847499] == "ogn-299-298"
    assert product_to_printing[847500] == "ogn-299-star-298"
    assert product_to_printing[866987] == "sfd-240-221"
    assert product_to_printing[847265] == "ogn-119a-298"
    assert product_to_printing[847541] == "ogs-019-024"
    assert product_to_printing[866971] == "sfd-224-221"
    assert product_to_printing[867003] == "sfd-224-star-221"
    assert product_to_printing[883980] == "unl-022a-219"
    assert product_to_printing[884171] == "unl-179a-219"
    assert product_to_printing[884218] == "unl-226-219"
    assert product_to_printing[885572] == "unl-226-star-219"


@pytest.mark.parametrize(
    ("provider_name", "provider_id", "source_name"),
    [
        ("Daughter of the Void", "ogn-299-298", "Kai'Sa, Daughter of the Void"),
        (
            "Wuju Bladesman - Starter",
            "ogs-019-024",
            "Master Yi, Wuju Bladesman",
        ),
    ],
)
def test_manual_override_accepts_riftbound_champion_legend_title(
    provider_name: str,
    provider_id: str,
    source_name: str,
) -> None:
    page = {
        "props": {
            "pageProps": {
                "cards": [
                    {
                        "id": provider_id,
                        "name": provider_name,
                        "publicCode": "OGN-299/298",
                        "set": {"value": {"id": "OGN", "label": "Origins"}},
                        "rarity": {"value": {"label": "Showcase"}},
                        "cardImage": {"url": "https://cmsassets.rgpub.io/kaisa.png"},
                    }
                ]
            }
        }
    }
    raw = (
        '<script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(page)
        + "</script>"
    ).encode()
    record = parse_riot_riftbound_page(raw)[0]
    snapshot = CatalogSnapshot(
        provider="riot_riftbound",
        game="riftbound",
        snapshot_id="riftbound-reviewed-legend-title",
        fetched_at="2026-08-31T00:00:00+00:00",
        source_url="https://playriftbound.com/en-us/card-gallery/",
        source_version="test",
        raw_sha256="f" * 64,
        records=(record,),
    )
    identity = replace(
        _identity(product_id=847499),
        game="riftbound",
        source_row_key=source_row_key("riftbound", 847499, "foil"),
        cardmarket_product_id=847499,
        cardmarket_name_raw=source_name,
        name_normalized=normalize_card_name(source_name),
        collector_number_raw=None,
        collector_number_canonical=None,
        finish="foil",
    )
    override = ManualCardImageOverride(
        source_row_key=identity.source_row_key,
        game="riftbound",
        cardmarket_product_id=847499,
        finish="foil",
        provider="riot_riftbound",
        provider_card_id=provider_id,
        provider_art_id=provider_id,
        reviewed_at="2026-08-31",
        evidence=("reviewed against the exact Cardmarket version",),
    )
    policy = replace(
        _policy(), provider="riot_riftbound", games=("riftbound",)
    )

    matches, assets = match_catalog_identities(
        [identity],
        snapshot,
        policy,
        manual_overrides={identity.source_row_key: override},
    )

    assert matches[0].status == "manual"
    assert matches[0].provider_card_id == provider_id
    assert matches[0].asset_id in assets


class _Response:
    def __init__(self, payload: object, *, headers: dict[str, str] | None = None) -> None:
        self.content = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.headers = headers or {}
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None


class _Client:
    def __init__(self, listing: object, download: bytes) -> None:
        self.responses = [_Response(listing), _Response(download, headers={"ETag": "v1"})]

    def get(self, url: str, **_: Any) -> _Response:
        return self.responses.pop(0)


def _listing(updated_at: str) -> dict[str, object]:
    return {
        "data": [
            {
                "type": "default_cards",
                "updated_at": updated_at,
                "jsonl_download_uri": "https://data.scryfall.io/default.jsonl.gz",
            }
        ]
    }


def test_snapshot_activation_is_idempotent_and_keeps_last_valid_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("indexengine.card_images.scryfall.MINIMUM_MAGIC_RECORDS", 1)
    store = LocalObjectStore(tmp_path / "store")
    valid_download = gzip.compress(json.dumps(_bulk_record()).encode() + b"\n")
    first = sync_scryfall_snapshot(
        store,
        client=_Client(_listing("2026-08-30T00:00:00Z"), valid_download),
    )
    assert first.record_count == 1
    latest_before = store.read_bytes("provider-snapshots/scryfall/latest.json")

    repeated = sync_scryfall_snapshot(
        store,
        client=_Client(_listing("2026-08-30T00:00:00Z"), b"unused"),
    )
    assert repeated.changed_keys == ()

    invalid_download = gzip.compress(json.dumps({"id": "no-market-id"}).encode() + b"\n")
    with pytest.raises(ValueError, match="only 0"):
        sync_scryfall_snapshot(
            store,
            client=_Client(_listing("2026-08-31T00:00:00Z"), invalid_download),
        )
    assert store.read_bytes("provider-snapshots/scryfall/latest.json") == latest_before


def test_magic_qa_sample_is_deterministic_stratified_and_product_unique() -> None:
    candidates = [
        MagicQaCandidate(
            source_row_key=f"row-{index}",
            cardmarket_product_id=index,
            cardmarket_name=f"Card {index}",
            finish="foil" if index % 2 else "nonfoil",
            provider_card_id=f"provider-{index}",
            provider_name=f"Card {index}",
            set_code="tst",
            collector_number=str(index),
            language="ja" if index % 7 == 0 else "en",
            layout="split" if index % 11 == 0 else "normal",
            face_count=2 if index % 13 == 0 else 1,
        )
        for index in range(1, 151)
    ]

    first = select_magic_qa_sample(candidates, 100, seed="2026-08-30")
    second = select_magic_qa_sample(list(reversed(candidates)), 100, seed="2026-08-30")

    assert first == second
    assert len(first) == 100
    assert len({item.cardmarket_product_id for item, _ in first}) == 100
    reasons = {reason for _, reason in first}
    assert {"multi_face", "special_layout", "foil", "non_english"} <= reasons


def test_manual_reviews_are_versioned_and_reject_duplicates(tmp_path: Path) -> None:
    reviews = tmp_path / "reviews.yaml"
    reviews.write_text(
        "version: 1\n"
        "dataset_version: '2026-08-30'\n"
        "reviews:\n"
        "  - source_row_key: row-1\n"
        "    status: approved\n"
    )
    assert load_manual_reviews(reviews, "2026-08-30") == {"row-1": "approved"}

    reviews.write_text(
        "version: 1\n"
        "dataset_version: '2026-08-30'\n"
        "reviews:\n"
        "  - source_row_key: row-1\n"
        "    status: approved\n"
        "  - source_row_key: row-1\n"
        "    status: rejected\n"
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_manual_reviews(reviews, "2026-08-30")

    with pytest.raises(FileNotFoundError):
        load_manual_reviews(tmp_path / "missing.yaml", "2026-08-30")
