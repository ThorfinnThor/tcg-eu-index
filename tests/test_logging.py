from __future__ import annotations

import logging

import pytest
from core.logging import configure_logging


def test_structured_logs_leave_stdout_available_for_cli_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging()
    logging.getLogger("test").info("pipeline_event", extra={"extra": {"status": "ok"}})

    captured = capsys.readouterr()
    assert captured.out == ""
    assert '"message": "pipeline_event"' in captured.err
    assert '"status": "ok"' in captured.err
