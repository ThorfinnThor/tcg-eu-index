from __future__ import annotations

import json
import logging
import time
from datetime import date
from pathlib import Path
from typing import Any

import click
import requests
from core.logging import configure_logging
from core.notifier import post_discord
from core.r2 import R2Client, gzip_body, sha256_hex
from core.settings import Settings, parse_run_date, utc_now

from ingest.cardmarket import catalogue_urls, combine_catalogues, priceguide_url
from ingest.manifest import Manifest, ManifestFile, latest_pointer, manifest_key

logger = logging.getLogger(__name__)
HEADER_ALLOWLIST = {"etag", "last-modified", "cache-control", "content-type"}


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


def write_immutable(store: Any, key: str, raw: bytes) -> tuple[str, bool]:
    compressed = gzip_body(raw)
    if not store.exists(key):
        store.write_bytes(key, compressed, "application/gzip")
        return key, False

    existing_raw = gzip_body(raw)
    if store.read_bytes(key) == existing_raw:
        return key, True

    n = 1
    while store.exists(conflict_key := key.replace(".json.gz", f".conflict-{n}.json.gz")):
        n += 1
    store.write_bytes(conflict_key, compressed, "application/gzip")
    return conflict_key, False


def run_archive(
    run_date: date,
    settings: Settings,
    store: Any | None = None,
    fetcher: Fetcher | None = None,
    data_dir: Path = Path("data"),
) -> Manifest:
    store = store or R2Client(settings)
    fetcher = fetcher or Fetcher(settings.cm_user_agent)
    key = manifest_key(run_date)
    if store.exists(key):
        logger.info("archive_already_exists", extra={"extra": {"date": run_date.isoformat()}})
        return Manifest.from_bytes(store.read_bytes(key))

    files: list[ManifestFile] = []
    for game in settings.cm_games:
        for kind in ("priceguide", "catalogue"):
            body, headers = _fetch_source(kind, game, settings, fetcher)
            destination = snapshot_key(kind, game, run_date)
            written_key, already_same = write_immutable(store, destination, body)
            files.append(
                ManifestFile(
                    game=game,
                    kind=kind,
                    key=written_key,
                    sha256_uncompressed=sha256_hex(body),
                    size_uncompressed=len(body),
                    fetched_at=utc_now().isoformat(),
                    headers=_safe_headers(headers),
                    unchanged_from_previous=already_same,
                )
            )

    manifest = Manifest(run_date=run_date.isoformat(), files=files)
    store.write_bytes(key, manifest.to_json_bytes(), "application/json")
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "manifest-latest.json").write_text(
        json.dumps(latest_pointer(manifest), indent=2, sort_keys=True) + "\n"
    )
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
        post_discord(
            settings.alert_discord_webhook,
            "OK",
            f"Archive complete for {manifest.run_date}",
        )
    except Exception as exc:
        post_discord(settings.alert_discord_webhook, "CRITICAL", f"Archive failed: {exc}")
        raise


if __name__ == "__main__":
    main()
