from __future__ import annotations

import calendar
import json
import math
import random
from datetime import date, timedelta
from typing import Any

from core.store import ObjectStat, ObjectStore

from ingest.manifest import Manifest, manifest_key, validate_manifest

# Cloudflare R2 Standard monthly free allocation, checked 2026-08-11.
R2_FREE_STORAGE_BYTES = 10_000_000_000
R2_FREE_CLASS_A_OPERATIONS = 1_000_000
R2_FREE_CLASS_B_OPERATIONS = 10_000_000
CLASS_A_PER_PIPELINE_ATTEMPT_BOUND = 250
CLASS_B_PER_PIPELINE_ATTEMPT_BOUND = 1_000
WATCHDOG_WARNING_RATIO = 0.8


def _ratio(value: int, limit: int) -> float:
    return round(value / limit, 8) if limit else 0.0


def _budget_status(ratio: float) -> str:
    if ratio > 1:
        return "over_free_tier"
    if ratio >= WATCHDOG_WARNING_RATIO:
        return "warning"
    return "within_free_tier"


def _object_category(key: str) -> str:
    if key.startswith("cardmarket/"):
        return "raw_snapshots"
    if key.startswith("manifests/"):
        return "archive_manifests"
    if key.startswith("derived/catalogue/") or key.startswith("derived/prices/"):
        return "normalized_data"
    if key.startswith("derived/indexes/"):
        return "shadow_indexes"
    if key.startswith("derived/"):
        return "pipeline_receipts"
    return "other"


def _storage_report(objects: list[ObjectStat]) -> dict[str, Any]:
    categories: dict[str, dict[str, int]] = {}
    for item in objects:
        category = _object_category(item.key)
        summary = categories.setdefault(category, {"object_count": 0, "bytes": 0})
        summary["object_count"] += 1
        summary["bytes"] += item.size
    total_bytes = sum(item.size for item in objects)
    usage_ratio = _ratio(total_bytes, R2_FREE_STORAGE_BYTES)
    return {
        "object_count": len(objects),
        "total_bytes": total_bytes,
        "total_gb_decimal": round(total_bytes / 1_000_000_000, 6),
        "free_tier_bytes": R2_FREE_STORAGE_BYTES,
        "free_tier_usage_ratio": usage_ratio,
        "status": _budget_status(usage_ratio),
        "categories": categories,
        "largest_objects": [
            {"key": item.key, "bytes": item.size}
            for item in sorted(objects, key=lambda value: value.size, reverse=True)[:5]
        ],
    }


def _operations_report(end: date, scheduled_attempts_per_day: int) -> dict[str, Any]:
    billing_days = calendar.monthrange(end.year, end.month)[1]
    attempts = scheduled_attempts_per_day * billing_days
    class_a = attempts * CLASS_A_PER_PIPELINE_ATTEMPT_BOUND
    class_b = attempts * CLASS_B_PER_PIPELINE_ATTEMPT_BOUND
    class_a_ratio = _ratio(class_a, R2_FREE_CLASS_A_OPERATIONS)
    class_b_ratio = _ratio(class_b, R2_FREE_CLASS_B_OPERATIONS)
    return {
        "basis": "conservative workflow upper bound; verify provider billing analytics",
        "billing_month": end.strftime("%Y-%m"),
        "billing_days": billing_days,
        "scheduled_attempts_per_day": scheduled_attempts_per_day,
        "projected_pipeline_attempts": attempts,
        "class_a": {
            "projected_operations": class_a,
            "free_tier_operations": R2_FREE_CLASS_A_OPERATIONS,
            "free_tier_usage_ratio": class_a_ratio,
            "status": _budget_status(class_a_ratio),
        },
        "class_b": {
            "projected_operations": class_b,
            "free_tier_operations": R2_FREE_CLASS_B_OPERATIONS,
            "free_tier_usage_ratio": class_b_ratio,
            "status": _budget_status(class_b_ratio),
        },
    }


def _next_month_start(value: date) -> date:
    if value.day == 1:
        return value
    return date(value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1, 1)


def _latest_quality_key(
    objects: list[ObjectStat], index_code: str, end: date
) -> str | None:
    prefix = f"derived/indexes/{index_code}/quality/"
    keys = [
        item.key
        for item in objects
        if item.key.startswith(prefix)
        and item.key.endswith(".json")
        and item.key.removeprefix(prefix).removesuffix(".json") <= end.isoformat()
    ]
    return sorted(keys)[-1] if keys else None


def _read_quality(store: ObjectStore, key: str | None) -> dict[str, Any] | None:
    if key is None:
        return None
    try:
        payload = json.loads(store.read_bytes(key))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _index_readiness(
    store: ObjectStore,
    objects: list[ObjectStat],
    index_code: str,
    end: date,
    fallback_available_days: int,
    required_lookback_days: int,
) -> dict[str, object]:
    quality_key = _latest_quality_key(objects, index_code, end)
    quality = _read_quality(store, quality_key)
    available_days = int(
        quality.get("available_archive_days", fallback_available_days)
        if quality
        else fallback_available_days
    )
    required_days = int(
        quality.get("required_lookback_days", required_lookback_days)
        if quality
        else required_lookback_days
    )
    selected = quality.get("selected_constituents") if quality else None
    target = quality.get("target_size") if quality else None
    language_status = quality.get("language_scope_status", "unknown") if quality else "unknown"
    gates = {
        "quality_receipt_available": quality is not None,
        "lookback_complete": available_days >= required_days,
        "target_size_filled": (
            isinstance(selected, int) and isinstance(target, int) and selected == target
        ),
        "language_scope_resolved": language_status not in {"pending_source_field", "unknown"},
    }
    blockers = [name for name, passed in gates.items() if not passed]
    return {
        "index_code": index_code,
        "state": "eligible_for_human_review" if not blockers else "accumulating",
        "quality_key": quality_key,
        "quality_run_date": quality.get("run_date") if quality else None,
        "available_archive_days": available_days,
        "required_lookback_days": required_days,
        "days_remaining_before_full_lookback": max(required_days - available_days, 0),
        "selected_constituents": selected,
        "target_size": target,
        "language_scope_status": language_status,
        "gates": gates,
        "blocking_gates": blockers,
    }


def audit_archive(
    store: ObjectStore,
    start: date,
    end: date,
    expected_games: list[str],
    sample_rate: float,
    seed: str,
    index_codes: list[str] | None = None,
    required_lookback_days: int = 60,
    scheduled_attempts_per_day: int = 4,
    game_inceptions: dict[str, date] | None = None,
) -> dict[str, Any]:
    if required_lookback_days < 1:
        raise ValueError("required_lookback_days must be positive")
    if scheduled_attempts_per_day < 1:
        raise ValueError("scheduled_attempts_per_day must be positive")

    game_inceptions = game_inceptions or {game: start for game in expected_games}
    missing_inceptions = set(expected_games) - set(game_inceptions)
    unexpected_inceptions = set(game_inceptions) - set(expected_games)
    if missing_inceptions or unexpected_inceptions:
        raise ValueError(
            "game inception keys must match expected games; "
            f"missing={sorted(missing_inceptions)}, "
            f"unexpected={sorted(unexpected_inceptions)}"
        )

    objects = store.list_objects("")
    manifests: list[tuple[date, Manifest]] = []
    errors: list[str] = []
    cursor = start
    while cursor <= end:
        key = manifest_key(cursor)
        if not store.exists(key):
            errors.append(f"{cursor}: missing manifest")
        else:
            try:
                manifest = Manifest.from_bytes(store.read_bytes(key))
                manifests.append((cursor, manifest))
                if manifest.run_date != cursor.isoformat():
                    errors.append(
                        f"{cursor}: manifest run_date is {manifest.run_date!r}"
                    )
            except Exception as exc:
                errors.append(f"{cursor}: invalid manifest: {exc}")
        cursor += timedelta(days=1)

    all_file_keys = [file.key for _, manifest in manifests for file in manifest.files]
    sample_size = min(
        len(all_file_keys),
        max(1, math.ceil(len(all_file_keys) * sample_rate)) if all_file_keys else 0,
    )
    selected_keys = (
        set(all_file_keys)
        if sample_size == len(all_file_keys)
        else set(random.Random(seed).sample(all_file_keys, sample_size))
    )
    for manifest_date, manifest in manifests:
        expected_for_date = [
            game for game in expected_games if manifest_date >= game_inceptions[game]
        ]
        manifest_errors = validate_manifest(
            store, manifest, expected_for_date, selected_keys
        )
        errors.extend(f"{manifest.run_date}: {error}" for error in manifest_errors)

    expected_days = (end - start).days + 1
    index_codes = index_codes or ["OPEU100", "PKEU250", "OPEUSLD"]
    readiness = [
        _index_readiness(
            store,
            objects,
            code,
            end,
            len(manifests),
            required_lookback_days,
        )
        for code in index_codes
    ]
    latest_game_inception = max(game_inceptions.values())
    first_full_observation = latest_game_inception + timedelta(
        days=required_lookback_days - 1
    )
    first_eligible_effective_date = latest_game_inception + timedelta(
        days=required_lookback_days
    )
    automated_ready = not errors and all(
        item["state"] == "eligible_for_human_review" for item in readiness
    )
    storage = _storage_report(objects)
    operations = _operations_report(end, scheduled_attempts_per_day)
    warnings = []
    if storage["status"] != "within_free_tier":
        warnings.append(f"R2 storage status is {storage['status']}")
    for operation_class in ("class_a", "class_b"):
        status = operations[operation_class]["status"]
        if status != "within_free_tier":
            warnings.append(f"R2 {operation_class} projection status is {status}")

    return {
        "status": "pass" if not errors else "fail",
        "since": start.isoformat(),
        "until": end.isoformat(),
        "expected_days": expected_days,
        "manifest_count": len(manifests),
        "coverage_ratio": round(len(manifests) / expected_days, 8),
        "file_count": len(all_file_keys),
        "snapshot_object_count": sum(item.key.startswith("cardmarket/") for item in objects),
        "sample_rate": sample_rate,
        "game_inceptions": {
            game: inception.isoformat()
            for game, inception in sorted(game_inceptions.items())
        },
        "verified_file_count": len(selected_keys),
        "errors": errors,
        "warnings": warnings,
        "r2": {"storage": storage, "operations": operations},
        "cutover": {
            "state": "eligible_for_human_review" if automated_ready else "accumulating",
            "first_full_observation_date_if_gapless": first_full_observation.isoformat(),
            "first_eligible_effective_date_if_gapless": first_eligible_effective_date.isoformat(),
            "first_monthly_rebalance_date_if_gapless": _next_month_start(
                first_eligible_effective_date
            ).isoformat(),
            "projection_assumes_no_archive_gaps": True,
            "human_review_required": True,
            "indexes": readiness,
        },
    }


def render_audit_summary(report: dict[str, Any]) -> str:
    r2 = report["r2"]
    storage = r2["storage"]
    operations = r2["operations"]
    cutover = report["cutover"]
    storage_line = (
        f"| R2 storage | {storage['total_gb_decimal']:.6f} GB "
        f"({storage['free_tier_usage_ratio']:.2%} of free tier) |"
    )
    class_a_line = (
        f"| Projected Class A | {operations['class_a']['projected_operations']:,} "
        f"({operations['class_a']['free_tier_usage_ratio']:.2%}) |"
    )
    class_b_line = (
        f"| Projected Class B | {operations['class_b']['projected_operations']:,} "
        f"({operations['class_b']['free_tier_usage_ratio']:.2%}) |"
    )
    monthly_rebalance_line = (
        "| Earliest monthly rebalance if gapless | "
        f"{cutover['first_monthly_rebalance_date_if_gapless']} |"
    )
    lines = [
        "# Cardmarket archive audit",
        "",
        "| Check | Result |",
        "| --- | --- |",
        f"| Integrity | {report['status']} |",
        f"| Calendar coverage | {report['manifest_count']} / {report['expected_days']} days |",
        f"| Verified sample | {report['verified_file_count']} files |",
        f"| R2 objects | {storage['object_count']} |",
        storage_line,
        class_a_line,
        class_b_line,
        f"| Cutover readiness | {cutover['state']} |",
        monthly_rebalance_line,
        "",
        "## Index readiness",
        "",
        "| Index | State | Archive days | Remaining | Constituents | Language |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for item in cutover["indexes"]:
        selected = item["selected_constituents"]
        target = item["target_size"]
        constituent_count = f"{selected} / {target}" if target is not None else "pending"
        lines.append(
            f"| {item['index_code']} | {item['state']} | {item['available_archive_days']} | "
            f"{item['days_remaining_before_full_lookback']} | {constituent_count} | "
            f"{item['language_scope_status']} |"
        )
    errors = report.get("errors", [])
    warnings = report.get("warnings", [])
    if errors:
        lines.extend(["", "## Errors", "", *(f"- {error}" for error in errors)])
    if warnings:
        lines.extend(["", "## Warnings", "", *(f"- {warning}" for warning in warnings)])
    lines.extend(
        [
            "",
            "> Operation counts are conservative workflow projections, "
            "not provider billing telemetry.",
            "",
        ]
    )
    return "\n".join(lines)
