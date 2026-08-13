from __future__ import annotations

import re
from typing import Any

MISSING_MANIFEST = re.compile(r"^(\d{4}-\d{2}-\d{2}): missing manifest$")


def build_public_archive_health(report: dict[str, Any]) -> dict[str, object]:
    status = report.get("status")
    if status not in {"pass", "fail"}:
        raise ValueError("archive audit status must be pass or fail")
    errors = report.get("errors")
    warnings = report.get("warnings")
    if not isinstance(errors, list) or not isinstance(warnings, list):
        raise ValueError("archive audit must contain errors and warnings arrays")

    gaps = []
    for error in errors:
        match = MISSING_MANIFEST.fullmatch(str(error))
        if match:
            gaps.append(
                {
                    "date": match.group(1),
                    "game": None,
                    "reason": "Daily archive manifest missing",
                }
            )

    r2 = report.get("r2", {})
    storage = r2.get("storage", {}) if isinstance(r2, dict) else {}
    operations = r2.get("operations", {}) if isinstance(r2, dict) else {}
    class_a = operations.get("class_a", {}) if isinstance(operations, dict) else {}
    class_b = operations.get("class_b", {}) if isinstance(operations, dict) else {}
    cutover = report.get("cutover", {})

    return {
        "schemaVersion": 1,
        "generatedFor": report.get("until"),
        "status": "healthy" if status == "pass" else "attention_required",
        "since": report.get("since"),
        "until": report.get("until"),
        "expectedDays": report.get("expected_days"),
        "manifestCount": report.get("manifest_count"),
        "coverageRatio": report.get("coverage_ratio"),
        "verifiedFileCount": report.get("verified_file_count"),
        "integrityErrorCount": len(errors),
        "warningCount": len(warnings),
        "gapCount": len(gaps),
        "gaps": gaps,
        "storage": {
            "bytes": storage.get("total_bytes"),
            "freeTierBytes": storage.get("free_tier_bytes"),
            "usageRatio": storage.get("free_tier_usage_ratio"),
            "status": storage.get("status", "unknown"),
        },
        "operations": {
            "billingMonth": operations.get("billing_month"),
            "classA": {
                "projected": class_a.get("projected_operations"),
                "freeTier": class_a.get("free_tier_operations"),
                "usageRatio": class_a.get("free_tier_usage_ratio"),
                "status": class_a.get("status", "unknown"),
            },
            "classB": {
                "projected": class_b.get("projected_operations"),
                "freeTier": class_b.get("free_tier_operations"),
                "usageRatio": class_b.get("free_tier_usage_ratio"),
                "status": class_b.get("status", "unknown"),
            },
        },
        "cutoverProjection": {
            "firstFullObservationDate": cutover.get(
                "first_full_observation_date_if_gapless"
            ),
            "firstEligibleEffectiveDate": cutover.get(
                "first_eligible_effective_date_if_gapless"
            ),
            "firstMonthlyRebalanceDate": cutover.get(
                "first_monthly_rebalance_date_if_gapless"
            ),
            "assumesNoGaps": cutover.get("projection_assumes_no_archive_gaps", True),
        },
    }
