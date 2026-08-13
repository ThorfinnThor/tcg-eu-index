from __future__ import annotations

from typing import Any

from indexengine.methodology import Methodology


def build_readiness_payload(
    calc_payload: dict[str, Any],
    manifest_payload: dict[str, Any],
    methodology: Methodology,
) -> dict[str, object]:
    results = calc_payload.get("results")
    if not isinstance(results, list):
        raise ValueError("calculation receipt must contain a results array")
    by_code = {
        str(item["index_code"]): item
        for item in results
        if isinstance(item, dict) and item.get("index_code")
    }
    expected_codes = {definition.code for definition in methodology.indexes}
    if set(by_code) != expected_codes:
        missing = sorted(expected_codes - set(by_code))
        unexpected = sorted(set(by_code) - expected_codes)
        raise ValueError(
            f"calculation receipt index mismatch; missing={missing}, unexpected={unexpected}"
        )

    generated_for = str(manifest_payload.get("date", ""))
    if not generated_for:
        raise ValueError("archive heartbeat is missing its date")
    for item in by_code.values():
        if item.get("run_date") != generated_for:
            raise ValueError("calculation and archive receipt dates do not match")

    manifest_files = manifest_payload.get("files", [])
    observed_pairs = {
        (str(item.get("game")), str(item.get("kind")))
        for item in manifest_files
        if isinstance(item, dict)
    }
    expected_pairs = {
        (definition.game_key, kind)
        for definition in methodology.indexes
        for kind in ("priceguide", "catalogue")
    }
    snapshot_verified = expected_pairs.issubset(observed_pairs)

    indexes: list[dict[str, object]] = []
    for definition in methodology.indexes:
        result = by_code[definition.code]
        available_days = int(result["available_days"])
        required_days = int(result["required_days"])
        selected = int(result["selected_constituents"])
        gates = {
            "snapshot_verified": snapshot_verified,
            "lookback_complete": available_days >= required_days,
            "target_size_filled": selected == definition.target_size,
            "language_scope_resolved": definition.language_scope_status
            != "pending_source_field",
            "shadow_calculation_ready": result.get("status") == "ready",
        }
        blockers = [name for name, passed in gates.items() if not passed]
        indexes.append(
            {
                "code": definition.code,
                "state": "eligible_for_human_review" if not blockers else "accumulating",
                "availableArchiveDays": available_days,
                "requiredLookbackDays": required_days,
                "daysRemaining": max(required_days - available_days, 0),
                "selectedConstituents": selected,
                "targetSize": definition.target_size,
                "languageScope": "all-cardmarket-europe-languages",
                "gates": gates,
                "blockers": blockers,
            }
        )

    return {
        "schemaVersion": 1,
        "generatedFor": generated_for,
        "methodologyVersion": methodology.methodology_version,
        "state": (
            "eligible_for_human_review"
            if all(item["state"] == "eligible_for_human_review" for item in indexes)
            else "collecting"
        ),
        "publicationStatus": "blocked_until_human_cutover",
        "humanReviewRequired": True,
        "source": "daily-private-shadow-receipt",
        "indexes": indexes,
    }
