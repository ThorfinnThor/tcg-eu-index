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
    parse_lorcast_payload,
    parse_optcg_payload,
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
from indexengine.card_images.pipeline import materialize_magic_images
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


def test_tcgdex_snapshot_preserves_direct_cardmarket_and_expansion_ids() -> None:
    archive_body = io.BytesIO()
    with tarfile.open(fileobj=archive_body, mode="w:gz") as archive:
        files = {
            "repo/data/Base/Test Set.ts": (
                'const set = { id: "base-test", name: { en: "Test Set" }, '
                "thirdParty: { cardmarket: 1234 } }"
            ),
            "repo/data/Base/Test Set/001.ts": (
                'const card = { name: { en: "Pikachu" }, variants: ['
                "{ thirdParty: { cardmarket: 9876 } }] }"
            ),
        }
        for name, body in files.items():
            encoded = body.encode()
            member = tarfile.TarInfo(name)
            member.size = len(encoded)
            archive.addfile(member, io.BytesIO(encoded))

    records = parse_tcgdex_tarball(archive_body.getvalue())

    assert len(records) == 1
    assert records[0].cardmarket_id == 9876
    assert records[0].cardmarket_expansion_id == 1234
    assert records[0].set_name == "Test Set"
    assert records[0].collector_number == "001"


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
