from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from indexengine.collector_preview import repack_existing_collector_preview


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Paginate an existing collector preview projection."
    )
    parser.add_argument("--output-root", type=Path, default=Path("apps/web/source-data"))
    args = parser.parse_args()
    result = repack_existing_collector_preview(args.output_root)
    print(json.dumps(asdict(result), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
