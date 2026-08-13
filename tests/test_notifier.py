from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
import requests
from core.notifier import post_discord


def test_discord_notification_is_optional_without_a_webhook() -> None:
    assert post_discord(None, "OK", "pipeline complete") is False


def test_discord_notification_posts_expected_message() -> None:
    response = Mock()
    response.raise_for_status.return_value = None
    with patch("core.notifier.requests.post", return_value=response) as request:
        assert post_discord("https://discord.example/webhook", "WARN", "archive delayed")

    request.assert_called_once_with(
        "https://discord.example/webhook",
        json={"content": "[WARN] archive delayed"},
        timeout=10,
    )


def test_strict_notification_turns_delivery_failure_into_a_failed_check() -> None:
    with (
        patch(
            "core.notifier.requests.post",
            side_effect=requests.RequestException("offline"),
        ),
        pytest.raises(RuntimeError, match="Discord notification failed"),
    ):
        post_discord("https://discord.example/webhook", "CRITICAL", "test", strict=True)
