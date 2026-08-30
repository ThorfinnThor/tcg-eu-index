from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import pytest
from core.r2 import LocalObjectStore
from indexengine.card_images.contracts import (
    CanonicalCardIdentity,
    PublicCardImage,
    normalize_card_name,
    public_image_from_match,
    source_row_key,
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
    body = gzip.compress(
        b"".join(json.dumps(record).encode() + b"\n" for record in records)
    )
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
