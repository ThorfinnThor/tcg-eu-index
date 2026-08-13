from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)


def post_discord(
    webhook: str | None, level: str, message: str, *, strict: bool = False
) -> bool:
    if not webhook:
        logger.info("discord_not_configured", extra={"extra": {"level": level, "message": message}})
        if strict:
            raise RuntimeError("Discord webhook is not configured")
        return False
    try:
        response = requests.post(webhook, json={"content": f"[{level}] {message}"}, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("discord_post_failed")
        if strict:
            raise RuntimeError("Discord notification failed") from exc
        return False
    return True
