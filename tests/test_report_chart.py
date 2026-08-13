from __future__ import annotations

import json
import subprocess
from pathlib import Path

from reports.charts import week_bounds


def test_week_bounds_uses_iso_calendar() -> None:
    start, end = week_bounds("2026-W32")
    assert start.isoformat() == "2026-08-03"
    assert end.isoformat() == "2026-08-09"


def test_report_chart_cli_writes_a_real_png(tmp_path: Path) -> None:
    history = tmp_path / "history.json"
    output = tmp_path / "chart.png"
    history.write_text(
        json.dumps(
            [
                {"value_date": "2026-08-03", "index_value": 1000},
                {"value_date": "2026-08-09", "index_value": 1015},
            ]
        )
    )

    subprocess.run(
        [
            "python",
            "scripts/render_report_chart.py",
            "--history",
            str(history),
            "--week",
            "2026-W32",
            "--code",
            "OPEU100",
            "--output",
            str(output),
        ],
        check=True,
    )

    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert output.stat().st_size > 10_000
