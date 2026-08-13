from __future__ import annotations

import argparse
import os

from core.logging import configure_logging
from core.notifier import post_discord


def main() -> None:
    parser = argparse.ArgumentParser(description="Post a concise pipeline status to Discord.")
    parser.add_argument("--level", choices=("OK", "WARN", "CRITICAL"), required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    configure_logging()
    delivered = post_discord(
        os.getenv("ALERT_DISCORD_WEBHOOK"),
        args.level,
        args.message,
        strict=args.strict,
    )
    print("delivered" if delivered else "not-configured")


if __name__ == "__main__":
    main()
