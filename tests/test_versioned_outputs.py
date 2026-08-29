from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from core.r2 import LocalObjectStore
from indexengine.collector_calc import CollectorDailyValue, CollectorMember, CollectorRebalance
from indexengine.methodology import Methodology
from indexengine.versioned_outputs import (
    build_collector_output_bundle,
    validate_collector_output_bundle,
    write_collector_output_bundle,
)


def test_collector_bundle_is_versioned_private_and_idempotent(tmp_path: Path) -> None:
    methodology = Methodology.load(Path("packages/indexengine/methodologies/v1.5.0-preview.1.yaml"))
    definition = methodology.index_by_code("OPEUCOL")
    effective = date(2026, 8, 20)
    member = CollectorMember(
        1,
        "nonfoil",
        "cardmarket:onepiece:product:1:nonfoil",
        10.0,
    )
    rebalance = CollectorRebalance(
        effective,
        date(2026, 8, 19),
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
        date(2026, 8, 19),
        methodology.methodology_version,
    )

    bundle = build_collector_output_bundle(
        definition,
        methodology,
        effective,
        [rebalance],
        [daily],
        [],
        [],
        source_hashes={"price_history": "b" * 64},
        engine_revision="test",
    )

    expected_prefix = "derived/indexes/1.5.0-preview.1/private_shadow/OPEUCOL/"
    assert bundle.series_id == "OPEUCOL:1.5.0-preview.1:private_shadow"
    diagnostics_prefix = "derived/diagnostics/1.5.0-preview.1/OPEUCOL/"
    assert all(
        key.startswith(expected_prefix) or key.startswith(diagnostics_prefix)
        for key in bundle.objects
    )
    manifest = json.loads(bundle.objects[f"{expected_prefix}manifest.json"])
    assert manifest["schema_version"] == 2
    assert manifest["public_alias_enabled"] is False
    assert manifest["outputs"]

    validate_collector_output_bundle(bundle)
    store = LocalObjectStore(tmp_path / "r2")
    assert len(write_collector_output_bundle(store, bundle)) == len(bundle.objects)
    assert write_collector_output_bundle(store, bundle) == []

    tampered = replace(
        bundle,
        objects={**bundle.objects, f"{expected_prefix}history.json": b"{}\n"},
    )
    with pytest.raises(ValueError, match="checksum mismatch"):
        validate_collector_output_bundle(tampered)
