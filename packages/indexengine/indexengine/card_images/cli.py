from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click
from core.logging import configure_logging
from core.r2 import LocalObjectStore, R2Client
from core.settings import Settings

from indexengine.card_images.pipeline import materialize_magic_images, run_magic_image_matching
from indexengine.card_images.readiness import audit_public_collector
from indexengine.card_images.scryfall import sync_scryfall_snapshot


@click.group()
def main() -> None:
    """Build versioned card-image snapshots, matches, and readiness reports."""
    configure_logging()


@main.command("audit")
@click.option(
    "--collector-root",
    type=click.Path(path_type=Path),
    default=Path("apps/web/source-data/collector"),
)
@click.option(
    "--output-root",
    type=click.Path(path_type=Path),
    default=Path("reports/images"),
)
def audit_command(collector_root: Path, output_root: Path) -> None:
    result = audit_public_collector(collector_root, output_root)
    click.echo(json.dumps(asdict(result), indent=2, sort_keys=True))


@main.command("sync-scryfall")
@click.option("--local-store", type=click.Path(path_type=Path))
def sync_scryfall_command(local_store: Path | None) -> None:
    store = LocalObjectStore(local_store) if local_store else R2Client(Settings.from_env())
    result = sync_scryfall_snapshot(store)
    click.echo(json.dumps(asdict(result), indent=2, sort_keys=True))


@main.command("match-magic")
@click.option("--dataset-version", required=True)
@click.option("--snapshot")
@click.option("--local-store", type=click.Path(path_type=Path))
@click.option(
    "--collector-root",
    type=click.Path(path_type=Path),
    default=Path("apps/web/source-data/collector"),
)
@click.option(
    "--report-root",
    type=click.Path(path_type=Path),
    default=Path("reports/images"),
)
def match_magic_command(
    dataset_version: str,
    snapshot: str | None,
    local_store: Path | None,
    collector_root: Path,
    report_root: Path,
) -> None:
    store = LocalObjectStore(local_store) if local_store else R2Client(Settings.from_env())
    result = run_magic_image_matching(
        store,
        collector_root,
        dataset_version,
        snapshot_id=snapshot,
    )
    report_root.mkdir(parents=True, exist_ok=True)
    report = asdict(result)
    report["exact_coverage_ratio"] = (
        result.exact_matches / result.rows if result.rows else 0.0
    )
    (report_root / "coverage.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    (report_root / "coverage.md").write_text(
        "# Card image coverage\n\n"
        f"Dataset `{result.dataset_version}`, snapshot `{result.snapshot_id}`.\n\n"
        "| Game | Rows | Exact matches | Published | Exact coverage |\n"
        "|---|---:|---:|---:|---:|\n"
        f"| magic | {result.rows} | {result.exact_matches} | "
        f"{result.published_images} | {report['exact_coverage_ratio']:.1%} |\n"
    )
    click.echo(json.dumps(asdict(result), indent=2, sort_keys=True))


@main.command("materialize-web")
@click.option("--local-store", type=click.Path(path_type=Path), required=True)
@click.option(
    "--source-data-root",
    type=click.Path(path_type=Path),
    default=Path("apps/web/source-data"),
)
def materialize_web_command(local_store: Path, source_data_root: Path) -> None:
    result = materialize_magic_images(LocalObjectStore(local_store), source_data_root)
    click.echo(json.dumps(asdict(result), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
