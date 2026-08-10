from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

from core.settings import Settings
from core.store import ObjectStore

from ingest.manifest import manifest_key
from ingest.normalize import run_normalize


def backfill_archive(
    store: ObjectStore,
    start: date,
    end: date,
    settings: Settings,
    category_map_path: Path = Path("packages/ingest/category_map.yaml"),
) -> dict[str, object]:
    if end < start:
        raise ValueError("end date must be on or after start date")

    runs: list[dict[str, object]] = []
    errors: list[str] = []
    cursor = start
    while cursor <= end:
        key = manifest_key(cursor)
        if not store.exists(key):
            errors.append(f"{cursor}: missing manifest")
            cursor += timedelta(days=1)
            continue
        try:
            results = run_normalize(
                cursor,
                settings,
                store=store,
                category_map_path=category_map_path,
            )
            runs.extend(asdict(result) for result in results)
        except Exception as exc:
            errors.append(f"{cursor}: {exc}")
        cursor += timedelta(days=1)

    return {
        "status": "pass" if not errors else "fail",
        "since": start.isoformat(),
        "until": end.isoformat(),
        "expected_days": (end - start).days + 1,
        "ok_runs": len(runs),
        "runs": runs,
        "errors": errors,
    }
