from __future__ import annotations

import math
import random
from datetime import date, timedelta

from core.store import ObjectStore

from ingest.manifest import Manifest, manifest_key, validate_manifest


def audit_archive(
    store: ObjectStore,
    start: date,
    end: date,
    expected_games: list[str],
    sample_rate: float,
    seed: str,
) -> dict[str, object]:
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
    for _, manifest in manifests:
        manifest_errors = validate_manifest(store, manifest, expected_games, selected_keys)
        errors.extend(f"{manifest.run_date}: {error}" for error in manifest_errors)

    return {
        "status": "pass" if not errors else "fail",
        "since": start.isoformat(),
        "until": end.isoformat(),
        "expected_days": (end - start).days + 1,
        "manifest_count": len(manifests),
        "file_count": len(all_file_keys),
        "snapshot_object_count": len(store.list_keys("cardmarket/")),
        "sample_rate": sample_rate,
        "verified_file_count": len(selected_keys),
        "errors": errors,
    }
