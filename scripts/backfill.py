from __future__ import annotations

from datetime import date, timedelta

import click
from core.settings import Settings
from indexengine.calc import run_calc
from ingest.normalize import run_normalize


@click.command()
@click.option("--since", required=True)
@click.option("--until", "until_value", required=True)
def main(since: str, until_value: str) -> None:
    settings = Settings.from_env()
    cursor = date.fromisoformat(since)
    end = date.fromisoformat(until_value)
    while cursor <= end:
        run_normalize(cursor, settings)
        run_calc(cursor, settings)
        print(f"ok {cursor}")
        cursor += timedelta(days=1)


if __name__ == "__main__":
    main()
