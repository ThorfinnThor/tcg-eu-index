from __future__ import annotations

from pathlib import Path

import yaml


def render(payload: dict[object, object]) -> str:
    lines = [
        "# Methodology v" + str(payload["methodology_version"]),
        "",
        "This page is generated from `packages/indexengine/methodology.yaml`.",
        "",
        "## Parameters",
        "",
    ]
    for key, value in payload.items():
        if key == "indexes":
            continue
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Launch Indexes", ""])
    for item in payload["indexes"]:  # type: ignore[index]
        lines.append(
            f"- `{item['code']}`: {item['name']} "
            f"({item['game_key']}, {item['universe']}, N={item['target_size']}, "
            f"languages={','.join(item['language_scope'])})"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    payload = yaml.safe_load(Path("packages/indexengine/methodology.yaml").read_text())
    expected = render(payload)
    target = Path(f"docs/methodology/v{payload['methodology_version']}.md")
    if target.read_text() != expected:
        raise SystemExit(f"{target} is out of sync; run scripts/render_methodology.py")


if __name__ == "__main__":
    main()
