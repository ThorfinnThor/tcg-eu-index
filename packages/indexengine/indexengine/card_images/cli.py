from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click
from core.logging import configure_logging
from core.r2 import LocalObjectStore, R2Client
from core.settings import Settings

from indexengine.card_images.catalogs import (
    PROVIDER_GAMES,
    PUBLIC_PROVIDERS,
    sync_catalog_snapshot,
)
from indexengine.card_images.pipeline import (
    materialize_magic_images,
    run_catalog_image_matching,
    run_magic_image_matching,
)
from indexengine.card_images.qa import build_magic_activation_qa
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


@main.command("sync-catalogs")
@click.option(
    "--provider",
    "providers",
    multiple=True,
    type=click.Choice(tuple(PROVIDER_GAMES)),
    help="Provider to sync; repeat the option. Defaults to every public provider.",
)
@click.option("--local-store", type=click.Path(path_type=Path))
def sync_catalogs_command(providers: tuple[str, ...], local_store: Path | None) -> None:
    store = LocalObjectStore(local_store) if local_store else R2Client(Settings.from_env())
    selected = providers or PUBLIC_PROVIDERS
    results = [asdict(sync_catalog_snapshot(store, provider)) for provider in selected]
    click.echo(json.dumps(results, indent=2, sort_keys=True))


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
    report["exact_coverage_ratio"] = result.exact_matches / result.rows if result.rows else 0.0
    (report_root / "coverage.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (report_root / "coverage.md").write_text(
        "# Card image coverage\n\n"
        f"Dataset `{result.dataset_version}`, snapshot `{result.snapshot_id}`.\n\n"
        "| Game | Rows | Exact matches | Published | Exact coverage |\n"
        "|---|---:|---:|---:|---:|\n"
        f"| magic | {result.rows} | {result.exact_matches} | "
        f"{result.published_images} | {report['exact_coverage_ratio']:.1%} |\n"
    )
    click.echo(json.dumps(asdict(result), indent=2, sort_keys=True))


@main.command("match-catalogs")
@click.option("--dataset-version", required=True)
@click.option("--local-store", type=click.Path(path_type=Path))
@click.option(
    "--collector-root",
    type=click.Path(path_type=Path),
    default=Path("apps/web/source-data/collector"),
)
def match_catalogs_command(
    dataset_version: str,
    local_store: Path | None,
    collector_root: Path,
) -> None:
    store = LocalObjectStore(local_store) if local_store else R2Client(Settings.from_env())
    code_by_game = {
        "pokemon": "PKEUCOL",
        "yugioh": "YGEUCOL",
        "digimon": "DGEUCOL",
        "lorcana": "LCEUCOL",
        "starwarsunlimited": "SWUEUCOL",
        "fleshandblood": "FABEUCOL",
        "onepiece": "OPEUCOL",
        "dragonballsuper": "DBSEUCOL",
        "riftbound": "RBEUCOL",
    }
    results = []
    selected = list(PUBLIC_PROVIDERS)
    selected.extend(
        provider
        for provider in ("optcg", "dragonball")
        if store.exists(f"provider-snapshots/{provider}/latest.json")
    )
    for provider in selected:
        game = PROVIDER_GAMES[provider]
        results.append(
            asdict(
                run_catalog_image_matching(
                    store,
                    collector_root,
                    dataset_version,
                    game=game,
                    code=code_by_game[game],
                    provider=provider,
                )
            )
        )
    click.echo(json.dumps(results, indent=2, sort_keys=True))


@main.command("materialize-web")
@click.option("--local-store", type=click.Path(path_type=Path))
@click.option(
    "--source-data-root",
    type=click.Path(path_type=Path),
    default=Path("apps/web/source-data"),
)
def materialize_web_command(
    local_store: Path | None,
    source_data_root: Path,
) -> None:
    store = LocalObjectStore(local_store) if local_store else R2Client(Settings.from_env())
    result = materialize_magic_images(store, source_data_root)
    click.echo(json.dumps(asdict(result), indent=2, sort_keys=True))


@main.command("qa-magic")
@click.option("--dataset-version", required=True)
@click.option("--snapshot")
@click.option("--local-store", type=click.Path(path_type=Path))
@click.option("--reviews", type=click.Path(path_type=Path))
@click.option("--require-ready", is_flag=True)
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
def qa_magic_command(
    dataset_version: str,
    snapshot: str | None,
    local_store: Path | None,
    reviews: Path | None,
    require_ready: bool,
    collector_root: Path,
    report_root: Path,
) -> None:
    store = LocalObjectStore(local_store) if local_store else R2Client(Settings.from_env())
    result = build_magic_activation_qa(
        store,
        collector_root,
        dataset_version,
        report_root,
        snapshot_id=snapshot,
        reviews_path=reviews,
    )
    click.echo(json.dumps(asdict(result), indent=2, sort_keys=True))
    if require_ready and not result.publication_ready:
        raise click.ClickException("Magic card-image publication gates are not ready")


if __name__ == "__main__":
    main()
