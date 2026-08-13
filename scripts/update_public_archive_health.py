from __future__ import annotations

import argparse
import json
from pathlib import Path

from ingest.public_health import build_public_archive_health


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export aggregate archive health without private object details."
    )
    parser.add_argument("--audit-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = build_public_archive_health(json.loads(args.audit_report.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
