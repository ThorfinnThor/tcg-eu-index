from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import yaml
from core.r2 import LocalObjectStore
from indexengine import collector_preview
from indexengine.collector_calc import CollectorDailyValue, CollectorMember, CollectorRebalance
from indexengine.collector_preview import (
    _paginate_rebalances,
    export_collector_preview,
    repack_existing_collector_preview,
)
from indexengine.eligibility import CollectorVariantDiagnostic
from indexengine.methodology import Methodology
from indexengine.product_identity import CollectorProductMetadata
from indexengine.versioned_outputs import (
    build_collector_output_bundle,
    write_collector_output_bundle,
)


def test_exports_compact_noindex_single_preview(tmp_path: Path) -> None:
    source_methodology = Path("packages/indexengine/methodologies/v1.5.0-preview.2.yaml")
    methodology = Methodology.load(source_methodology)
    definition = methodology.index_by_code("OPEUCOL")
    effective = date(2026, 8, 29)
    member = CollectorMember(
        1,
        "nonfoil",
        "cardmarket:onepiece:product:1:nonfoil",
        12.0,
    )
    rebalance = CollectorRebalance(
        effective,
        date(2026, 8, 28),
        methodology.methodology_version,
        "a" * 64,
        1,
        (member,),
    )
    daily = CollectorDailyValue(
        effective,
        1000.0,
        0.0,
        "active",
        1,
        1,
        0,
        0,
        0,
        0.0,
        0.0,
        0.0,
        1.0,
        False,
        effective,
        date(2026, 8, 28),
        methodology.methodology_version,
    )
    diagnostic = CollectorVariantDiagnostic(
        cm_product_id=1,
        variant_key="nonfoil",
        stable_variant_id=member.stable_variant_id,
        eligible=True,
        exclusion_reasons=(),
        reference_price=12.0,
        history_days=10,
        valuation_observation_ratio=1.0,
        selection_price_observation_ratio=1.0,
        suspect_zero_ratio=0.0,
        price_update_frequency=0.5,
        inverse_dispersion=0.9,
        data_quality_score=0.8,
        activity_days=4,
        activity_ratio=0.4,
        observable_activity_days=10,
        last_positive_avg1_date=date(2026, 8, 28),
        days_since_positive_avg1=1,
        repeated_positive_avg1_days=4,
    )
    metadata = CollectorProductMetadata(
        cm_product_id=1,
        name="Roronoa Zoro",
        set_name="Romance Dawn",
        collector_number="OP01-001",
        cm_expansion_id=10,
        image_url=None,
        image_source=None,
        tcgplayer_product_url=None,
        metadata_status="collector_number_from_catalogue_name",
    )
    bundle = build_collector_output_bundle(
        definition,
        methodology,
        effective,
        [rebalance],
        [daily],
        [],
        [diagnostic],
        product_metadata={1: metadata},
        engine_revision="test",
    )
    store = LocalObjectStore(tmp_path / "r2")
    write_collector_output_bundle(store, bundle)
    methodology_payload = yaml.safe_load(source_methodology.read_text())
    methodology_payload["indexes"] = [
        item for item in methodology_payload["indexes"] if item["code"] == "OPEUCOL"
    ]
    methodology_path = tmp_path / "methodology.yaml"
    methodology_path.write_text(yaml.safe_dump(methodology_payload, sort_keys=False))
    output_root = tmp_path / "web"

    result = export_collector_preview(
        store,
        effective,
        output_root,
        methodology_path=methodology_path,
    )

    assert result.indexes == 1
    assert result.variants == 1
    index_payload = json.loads((output_root / "collector/index.json").read_text())
    assert index_payload["indexes"][0]["base_value"] == 1000
    diagnostics = json.loads((output_root / "collector/OPEUCOL/diagnostics.json").read_text())
    assert diagnostics["eligibility"] == []
    assert diagnostics["summary"] == {
        "average_activity_ratio": 0.4,
        "average_quality": 0.8,
        "count": 1,
        "positive_activity_rows": 1,
    }
    rebalances = json.loads((output_root / "collector/OPEUCOL/rebalances.json").read_text())
    assert rebalances["generated_for"] == effective.isoformat()
    assert rebalances["rebalances"][0]["constituents"] == []
    composition = json.loads((output_root / "collector/OPEUCOL/composition.json").read_text())
    assert composition["rebalances"][0]["page_count"] == 1
    composition_page = json.loads(
        (output_root / "collector/OPEUCOL/composition/2026-08-29/0001.json").read_text()
    )
    assert composition_page["constituents"][0]["name"] == "Roronoa Zoro"
    manifest = json.loads((output_root / "collector/OPEUCOL/manifest.json").read_text())
    assert manifest["publication_state"] == "preview_noindex"
    assert manifest["public_alias_enabled"] is False
    assert len(manifest["outputs"]) == 5

    repeated = export_collector_preview(
        store,
        effective,
        output_root,
        methodology_path=methodology_path,
    )
    assert repeated.changed_files == []
    assert repack_existing_collector_preview(output_root).changed_files == []


def test_paginates_compositions_in_global_ascending_price_order() -> None:
    source = {
        "schema_version": 2,
        "series_id": "OPEUCOL:1.5.0-preview.2:private_shadow",
        "index_code": "OPEUCOL",
        "methodology_version": "1.5.0-preview.2",
        "data_state": "private_shadow",
        "cadence": "monthly",
        "generated_for": "2026-08-29",
        "rebalances": [{
            "effective_date": "2026-08-29",
            "selection_as_of": "2026-08-28",
            "methodology_version": "1.5.0-preview.2",
            "selection_snapshot_sha256": "a" * 64,
            "eligible_count": 3,
            "active_count": 3,
            "constituents": [
                {"selection_price": 100.0, "stable_variant_id": "third"},
                {"selection_price": 10.0, "stable_variant_id": "second"},
                {"selection_price": 10.0, "stable_variant_id": "first"},
            ],
        }],
    }

    _, _, pages = _paginate_rebalances(
        source,
        "OPEUCOL",
        "1.5.0-preview.2",
        date(2026, 8, 29),
    )

    assert [
        item["stable_variant_id"]
        for item in pages["composition/2026-08-29/0001.json"]["constituents"]
    ] == ["first", "second", "third"]


def test_rejects_empty_projection_before_replacing_live_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_methodology = Path("packages/indexengine/methodologies/v1.5.0-preview.2.yaml")
    methodology_payload = yaml.safe_load(source_methodology.read_text())
    methodology_payload["indexes"] = [
        item for item in methodology_payload["indexes"] if item["code"] == "OPEUCOL"
    ]
    methodology_path = tmp_path / "methodology.yaml"
    methodology_path.write_text(yaml.safe_dump(methodology_payload, sort_keys=False))
    output_root = tmp_path / "web"
    existing_summary = output_root / "collector/OPEUCOL/summary.json"
    existing_summary.parent.mkdir(parents=True)
    existing_summary.write_text('{"sentinel":"last-known-good"}\n')

    empty_projection = {
        "summary.json": {"latest_index_value": None, "latest_value_date": None},
        "rebalances.json": {"rebalances": []},
        "composition.json": {"rebalances": []},
    }
    monkeypatch.setattr(
        collector_preview,
        "_projection",
        lambda *_args, **_kwargs: empty_projection,
    )

    with pytest.raises(ValueError, match="has no rebalances; refusing to publish"):
        export_collector_preview(
            LocalObjectStore(tmp_path / "r2"),
            date(2026, 8, 31),
            output_root,
            methodology_path=methodology_path,
        )

    assert json.loads(existing_summary.read_text()) == {"sentinel": "last-known-good"}
