from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from core.r2 import LocalObjectStore, R2Client
from core.settings import Settings
from indexengine.collector_preview import DEFAULT_METHODOLOGY, export_collector_preview


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a public noindex projection of collector singles previews."
    )
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument("--output-root", type=Path, default=Path("apps/web/source-data"))
    parser.add_argument("--store-root", type=Path)
    parser.add_argument("--methodology", type=Path, default=DEFAULT_METHODOLOGY)
    args = parser.parse_args()
    store = LocalObjectStore(args.store_root) if args.store_root else R2Client(Settings.from_env())
    result = export_collector_preview(
        store,
        args.date,
        args.output_root,
        methodology_path=args.methodology,
    )
    print(json.dumps(asdict(result), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
