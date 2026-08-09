from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import click
from core.r2 import LocalObjectStore
from ingest.manifest import Manifest, manifest_key, validate_manifest


@click.command()
@click.option("--since", required=True, help="YYYY-MM-DD inception date")
@click.option("--until", "until_value", default=None, help="YYYY-MM-DD end date, defaults to today")
@click.option("--store-root", default="work/local-r2", help="Local object-store root for dry runs")
@click.option("--games", default="onepiece,pokemon")
def main(since: str, until_value: str | None, store_root: str, games: str) -> None:
    start = date.fromisoformat(since)
    end = date.fromisoformat(until_value) if until_value else date.today()
    expected_games = [item.strip() for item in games.split(",") if item.strip()]
    store = LocalObjectStore(Path(store_root))
    cursor = start
    errors: list[str] = []
    while cursor <= end:
        key = manifest_key(cursor)
        if not store.exists(key):
            errors.append(f"{cursor}: missing manifest")
        else:
            manifest = Manifest.from_bytes(store.read_bytes(key))
            manifest_errors = validate_manifest(store, manifest, expected_games)
            errors.extend(f"{cursor}: {error}" for error in manifest_errors)
        cursor += timedelta(days=1)
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"archive ok: {start} through {end}")


if __name__ == "__main__":
    main()
