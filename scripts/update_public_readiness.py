from __future__ import annotations

import argparse
import json
from pathlib import Path

from indexengine.methodology import Methodology
from indexengine.readiness import build_readiness_payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write a public aggregate readiness receipt without exposing prices."
    )
    parser.add_argument("--calc-result", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--methodology",
        type=Path,
        default=Path("packages/indexengine/methodology.yaml"),
    )
    args = parser.parse_args()
    payload = build_readiness_payload(
        json.loads(args.calc_result.read_text()),
        json.loads(args.manifest.read_text()),
        Methodology.load(args.methodology),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
