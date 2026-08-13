from __future__ import annotations

from indexengine.methodology import Methodology
from indexengine.readiness import build_readiness_payload


def test_public_readiness_contains_only_aggregate_gates() -> None:
    methodology = Methodology.load()
    results = [
        {
            "index_code": definition.code,
            "run_date": "2026-08-13",
            "status": "accumulating",
            "available_days": 2,
            "required_days": 60,
            "selected_constituents": 0,
        }
        for definition in methodology.indexes
    ]
    games = sorted({definition.game_key for definition in methodology.indexes})
    manifest = {
        "date": "2026-08-13",
        "files": [
            {"game": game, "kind": kind}
            for game in games
            for kind in ("priceguide", "catalogue")
        ],
    }

    payload = build_readiness_payload({"results": results}, manifest, methodology)

    assert payload["state"] == "collecting"
    assert payload["publicationStatus"] == "blocked_until_human_cutover"
    assert len(payload["indexes"]) == 20
    first = payload["indexes"][0]
    assert first["daysRemaining"] == 58
    assert first["gates"]["language_scope_resolved"] is True
    assert "lookback_complete" in first["blockers"]
    serialized = str(payload).casefold()
    assert "price_avg" not in serialized
    assert "ref_price" not in serialized


def test_public_readiness_becomes_review_eligible_only_when_every_gate_passes() -> None:
    methodology = Methodology.load()
    results = [
        {
            "index_code": definition.code,
            "run_date": "2026-10-10",
            "status": "ready",
            "available_days": 60,
            "required_days": 60,
            "selected_constituents": definition.target_size,
        }
        for definition in methodology.indexes
    ]
    games = sorted({definition.game_key for definition in methodology.indexes})
    manifest = {
        "date": "2026-10-10",
        "files": [
            {"game": game, "kind": kind}
            for game in games
            for kind in ("priceguide", "catalogue")
        ],
    }

    payload = build_readiness_payload({"results": results}, manifest, methodology)

    assert payload["state"] == "eligible_for_human_review"
    assert all(not item["blockers"] for item in payload["indexes"])
