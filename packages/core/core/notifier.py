from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)


def post_discord(webhook: str | None, level: str, message: str) -> None:
    if not webhook:
        logger.info("discord_not_configured", extra={"extra": {"level": level, "message": message}})
        return
    try:
        response = requests.post(webhook, json={"content": f"[{level}] {message}"}, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("discord_post_failed")
