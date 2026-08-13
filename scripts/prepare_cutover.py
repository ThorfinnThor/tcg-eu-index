from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from core.r2 import LocalObjectStore, R2Client
from core.settings import Settings
from indexengine.cutover import prepare_cutover_candidate


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare a review-only public cutover candidate from private shadow outputs."
    )
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument("--audit-report", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--store-root", type=Path)
    parser.add_argument(
        "--methodology",
        type=Path,
        default=Path("packages/indexengine/methodology.yaml"),
    )
    args = parser.parse_args()
    store = LocalObjectStore(args.store_root) if args.store_root else R2Client(Settings.from_env())
    review = prepare_cutover_candidate(
        store,
        args.date,
        json.loads(args.audit_report.read_text()),
        args.output_root,
        args.methodology,
    )
    print(json.dumps(review, indent=2, sort_keys=True))
    if review["state"] != "eligible_for_human_review":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
