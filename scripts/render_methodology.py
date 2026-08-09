from __future__ import annotations

from pathlib import Path

import yaml
from check_methodology_sync import render


def main() -> None:
    payload = yaml.safe_load(Path("packages/indexengine/methodology.yaml").read_text())
    target = Path(f"docs/methodology/v{payload['methodology_version']}.md")
    target.write_text(render(payload))


if __name__ == "__main__":
    main()
