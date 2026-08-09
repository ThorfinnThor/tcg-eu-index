from __future__ import annotations

import click
from core.settings import Settings, parse_run_date
from indexengine.calc import run_calc


@click.command()
@click.option("--date", "date_value", default="today")
def main(date_value: str) -> None:
    run_calc(parse_run_date(date_value), Settings.from_env())


if __name__ == "__main__":
    main()
