from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def week_bounds(value: str) -> tuple[date, date]:
    year, week = value.split("-W", 1)
    start = date.fromisocalendar(int(year), int(week), 1)
    return start, start + timedelta(days=6)


def render_weekly_chart(
    history_path: Path, week: str, code: str, output_path: Path
) -> None:
    start, end = week_bounds(week)
    records = json.loads(history_path.read_text())
    rows = [
        item
        for item in records
        if start <= date.fromisoformat(str(item["value_date"])) <= end
    ]
    if not rows:
        raise ValueError(f"no observations for {code} in {week}")

    values = [float(item["index_value"]) for item in rows]
    labels = [str(item["value_date"])[5:] for item in rows]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
    figure, axis = plt.subplots(figsize=(12, 6.3), dpi=100)
    figure.patch.set_facecolor("#10100f")
    axis.set_facecolor("#10100f")
    axis.plot(labels, values, color="#e7b75f", linewidth=2.6)
    axis.fill_between(labels, values, min(values), color="#e7b75f", alpha=0.12)
    axis.set_title(f"{code} | {week}", color="#f4efe4", loc="left", pad=18)
    axis.set_ylabel("Index level", color="#a7a195")
    axis.grid(axis="y", color="#34342e", linewidth=0.8)
    axis.tick_params(colors="#a7a195")
    for spine in axis.spines.values():
        spine.set_visible(False)
    figure.tight_layout(pad=2)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, facecolor=figure.get_facecolor())
    plt.close(figure)
