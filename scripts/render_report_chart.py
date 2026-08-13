from __future__ import annotations

import argparse
from pathlib import Path

from reports.charts import render_weekly_chart


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a deterministic weekly index chart.")
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--week", required=True)
    parser.add_argument("--code", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    render_weekly_chart(args.history, args.week, args.code, args.output)
    print(args.output)


if __name__ == "__main__":
    main()
