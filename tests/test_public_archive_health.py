from __future__ import annotations

from ingest.public_health import build_public_archive_health


def audit_report() -> dict[str, object]:
    return {
        "status": "fail",
        "since": "2026-08-10",
        "until": "2026-08-13",
        "expected_days": 4,
        "manifest_count": 3,
        "coverage_ratio": 0.75,
        "verified_file_count": 12,
        "errors": [
            "2026-08-12: missing manifest",
            "2026-08-13: cardmarket/priceguide/private-key.json.gz: sha256 mismatch",
        ],
        "warnings": ["R2 storage status is warning"],
        "r2": {
            "storage": {
                "total_bytes": 1234,
                "free_tier_bytes": 10_000_000_000,
                "free_tier_usage_ratio": 0.00000012,
                "status": "within_free_tier",
                "largest_objects": [{"key": "private-key", "bytes": 1000}],
            },
            "operations": {
                "billing_month": "2026-08",
                "class_a": {
                    "projected_operations": 31_000,
                    "free_tier_operations": 1_000_000,
                    "free_tier_usage_ratio": 0.031,
                    "status": "within_free_tier",
                },
                "class_b": {
                    "projected_operations": 124_000,
                    "free_tier_operations": 10_000_000,
                    "free_tier_usage_ratio": 0.0124,
                    "status": "within_free_tier",
                },
            },
        },
        "cutover": {
            "first_full_observation_date_if_gapless": "2026-10-10",
            "first_eligible_effective_date_if_gapless": "2026-10-11",
            "first_monthly_rebalance_date_if_gapless": "2026-11-01",
            "projection_assumes_no_archive_gaps": True,
        },
    }


def test_public_archive_health_exposes_aggregates_without_private_keys() -> None:
    payload = build_public_archive_health(audit_report())

    assert payload["status"] == "attention_required"
    assert payload["gapCount"] == 1
    assert payload["gaps"] == [
        {"date": "2026-08-12", "game": None, "reason": "Daily archive manifest missing"}
    ]
    assert payload["integrityErrorCount"] == 2
    serialized = str(payload)
    assert "private-key" not in serialized
    assert "cardmarket/priceguide" not in serialized
