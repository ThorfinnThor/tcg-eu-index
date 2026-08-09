from __future__ import annotations

from datetime import date
from pathlib import Path

import click


def current_week() -> str:
    year, week, _ = date.today().isocalendar()
    return f"{year}-W{week:02d}"


@click.command()
@click.option("--week", default=None)
def main(week: str | None) -> None:
    target_week = week or current_week()
    report_dir = Path("docs/reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    target = report_dir / f"{target_week}.md"
    if not target.exists():
        target.write_text(
            "\n".join(
                [
                    f"# European TCG Index Weekly Report {target_week}",
                    "",
                    "## Summary",
                    "",
                    "Automated metrics are pending the first production snapshots.",
                    "",
                    "## Editor's notes",
                    "",
                    "_Add human commentary before publishing._",
                    "",
                ]
            )
        )
    print(target)


if __name__ == "__main__":
    main()
