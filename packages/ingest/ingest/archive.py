from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

import click
import requests
from core.logging import configure_logging
from core.notifier import post_discord
from core.r2 import R2Client, gzip_body, sha256_hex
from core.settings import Settings, parse_run_date, utc_now
from core.store import ObjectStore

from ingest.cardmarket import catalogue_urls, combine_catalogues, priceguide_url
from ingest.manifest import Manifest, ManifestFile, latest_pointer, manifest_key, validate_manifest

logger = logging.getLogger(__name__)
HEADER_ALLOWLIST = {"etag", "last-modified", "cache-control", "content-type"}


class ArchiveConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class ImmutableWriteResult:
    key: str
    status: Literal["created", "existing", "conflict"]


def snapshot_key(kind: str, game: str, run_date: date) -> str:
    return f"cardmarket/{kind}/{game}/{run_date:%Y}/{run_date:%m}/{run_date.isoformat()}.json.gz"


class Fetcher:
    def __init__(self, user_agent: str) -> None:
        self.session = requests.Session()
        self.user_agent = user_agent

    def fetch(self, url: str) -> tuple[bytes, dict[str, str]]:
        last_error: Exception | None = None
        for delay in (0, 30, 120, 600):
            if delay:
                time.sleep(delay)
            try:
                response = self.session.get(
                    url,
                    headers={"User-Agent": self.user_agent},
                    timeout=10,
                )
                response.raise_for_status()
                headers = {
                    key.lower(): value
                    for key, value in response.headers.items()
                    if key.lower() in HEADER_ALLOWLIST
                }
                return response.content, headers
            except requests.RequestException as exc:
                last_error = exc
                logger.warning("fetch_retry", extra={"extra": {"url": url, "error": str(exc)}})
        raise RuntimeError(f"failed to fetch {url}: {last_error}")


def _format_url(template: str, game: str) -> str:
    if not template:
        raise ValueError("Cardmarket URL template is required")
    if "{game}" not in template:
        raise ValueError("Cardmarket URL template must contain {game}")
    return template.format(game=game)


def _fetch_source(
    kind: str,
    game: str,
    settings: Settings,
    fetcher: Fetcher,
) -> tuple[bytes, dict[str, str]]:
    if kind == "priceguide":
        url = (
            _format_url(settings.cm_priceguide_url_template, game)
            if settings.cm_priceguide_url_template
            else priceguide_url(game)
        )
        return fetcher.fetch(url)

    if settings.cm_catalogue_url_template:
        return fetcher.fetch(_format_url(settings.cm_catalogue_url_template, game))

    responses = [fetcher.fetch(url) for url in catalogue_urls(game)]
    body = combine_catalogues([response[0] for response in responses])
    headers = {
        key: value for _, response_headers in responses for key, value in response_headers.items()
    }
    return body, headers


def _safe_headers(headers: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in headers.items() if key in HEADER_ALLOWLIST}


def _source_metadata(kind: str, raw: bytes) -> tuple[str | None, int]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Cardmarket {kind} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Cardmarket {kind} must be a JSON object")
    records_key = "priceGuides" if kind == "priceguide" else "products"
    records = payload.get(records_key)
    if not isinstance(records, list):
        raise ValueError(f"Cardmarket {kind} is missing {records_key}")
    if kind == "priceguide" and len(records) < 1_000:
        raise ValueError(f"Cardmarket priceguide has only {len(records)} records")
    source_created_at = payload.get("createdAt")
    return str(source_created_at) if source_created_at is not None else None, len(records)


def write_immutable(store: ObjectStore, key: str, raw: bytes) -> ImmutableWriteResult:
    compressed = gzip_body(raw)
    if not store.exists(key):
        store.write_bytes(key, compressed, "application/gzip")
        return ImmutableWriteResult(key, "created")

    if store.read_bytes(key) == compressed:
        return ImmutableWriteResult(key, "existing")

    n = 1
    while store.exists(conflict_key := key.replace(".json.gz", f".conflict-{n}.json.gz")):
        n += 1
    store.write_bytes(conflict_key, compressed, "application/gzip")
    return ImmutableWriteResult(conflict_key, "conflict")


def _previous_manifest(store: ObjectStore, run_date: date) -> Manifest | None:
    key = manifest_key(run_date - timedelta(days=1))
    if not store.exists(key):
        return None
    return Manifest.from_bytes(store.read_bytes(key))


def _previous_sha(manifest: Manifest | None, game: str, kind: str) -> str | None:
    if manifest is None:
        return None
    match = next(
        (file for file in manifest.files if file.game == game and file.kind == kind),
        None,
    )
    return match.sha256_uncompressed if match else None


def _write_latest_pointer(data_dir: Path, manifest: Manifest) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "manifest-latest.json").write_text(
        json.dumps(latest_pointer(manifest), indent=2, sort_keys=True) + "\n"
    )


def run_archive(
    run_date: date,
    settings: Settings,
    store: ObjectStore | None = None,
    fetcher: Fetcher | None = None,
    data_dir: Path = Path("data"),
) -> Manifest:
    store = store or R2Client(settings)
    fetcher = fetcher or Fetcher(settings.cm_user_agent)
    key = manifest_key(run_date)
    if store.exists(key):
        logger.info("archive_already_exists", extra={"extra": {"date": run_date.isoformat()}})
        existing_manifest = Manifest.from_bytes(store.read_bytes(key))
        if existing_manifest.run_date != run_date.isoformat():
            raise RuntimeError(
                f"existing manifest date {existing_manifest.run_date!r} does not match {run_date}"
            )
        errors = validate_manifest(store, existing_manifest, settings.cm_games)
        if errors:
            raise RuntimeError("existing archive manifest failed validation: " + "; ".join(errors))
        _write_latest_pointer(data_dir, existing_manifest)
        return existing_manifest

    previous_manifest = _previous_manifest(store, run_date)
    files: list[ManifestFile] = []
    for game in settings.cm_games:
        for kind in ("priceguide", "catalogue"):
            body, headers = _fetch_source(kind, game, settings, fetcher)
            source_created_at, record_count = _source_metadata(kind, body)
            destination = snapshot_key(kind, game, run_date)
            write_result = write_immutable(store, destination, body)
            if write_result.status == "conflict":
                raise ArchiveConflictError(
                    f"immutable key conflict at {destination}; "
                    f"preserved candidate at {write_result.key}"
                )
            body_sha = sha256_hex(body)
            files.append(
                ManifestFile(
                    game=game,
                    kind=kind,
                    key=write_result.key,
                    sha256_uncompressed=body_sha,
                    size_uncompressed=len(body),
                    fetched_at=utc_now().isoformat(),
                    headers=_safe_headers(headers),
                    source_created_at=source_created_at,
                    unchanged_from_previous=_previous_sha(previous_manifest, game, kind)
                    == body_sha,
                )
            )
            logger.info(
                "snapshot_stored",
                extra={
                    "extra": {
                        "game": game,
                        "kind": kind,
                        "key": write_result.key,
                        "records": record_count,
                        "status": write_result.status,
                    }
                },
            )

    manifest = Manifest(run_date=run_date.isoformat(), files=files)
    errors = validate_manifest(store, manifest, settings.cm_games)
    if errors:
        raise RuntimeError("archive validation failed: " + "; ".join(errors))
    store.write_bytes(key, manifest.to_json_bytes(), "application/json")
    _write_latest_pointer(data_dir, manifest)
    logger.info(
        "archive_complete",
        extra={"extra": {"date": run_date.isoformat(), "files": len(files)}},
    )
    return manifest


@click.command()
@click.option("--date", "date_value", default="today")
def main(date_value: str) -> None:
    configure_logging()
    settings = Settings.from_env()
    run_date = parse_run_date(date_value)
    try:
        manifest = run_archive(run_date, settings)
        unchanged = [
            f"{file.game}/{file.kind}" for file in manifest.files if file.unchanged_from_previous
        ]
        level = "WARN" if unchanged else "OK"
        suffix = f"; unchanged: {', '.join(unchanged)}" if unchanged else ""
        post_discord(
            settings.alert_discord_webhook,
            level,
            f"Archive complete for {manifest.run_date}{suffix}",
        )
        click.echo(json.dumps(latest_pointer(manifest), sort_keys=True))
    except Exception as exc:
        post_discord(settings.alert_discord_webhook, "CRITICAL", f"Archive failed: {exc}")
        raise


if __name__ == "__main__":
    main()
