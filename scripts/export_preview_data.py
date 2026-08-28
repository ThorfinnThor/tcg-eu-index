from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from core.r2 import LocalObjectStore, R2Client
from core.settings import Settings
from indexengine.preview_export import export_preview_dataset


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export verified provisional index data from private R2 outputs."
    )
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--output-root", type=Path, default=Path("apps/web/source-data")
    )
    parser.add_argument("--store-root", type=Path)
    parser.add_argument(
        "--methodology",
        type=Path,
        default=Path("packages/indexengine/methodology.yaml"),
    )
    args = parser.parse_args()
    store = LocalObjectStore(args.store_root) if args.store_root else R2Client(Settings.from_env())
    result = export_preview_dataset(
        store, args.date, args.output_root, args.methodology
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
