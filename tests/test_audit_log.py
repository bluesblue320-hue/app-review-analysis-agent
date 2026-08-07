"""Stage 5: structured audit logging tests."""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

from backend.core.audit_log import get_request_id, log_event, set_request_id


class RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record.getMessage())


def _capture():
    handler = RecordingHandler()
    logger = logging.getLogger("backend.audit")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return handler


def test_log_event_emits_json_with_request_id() -> None:
    handler = _capture()
    try:
        set_request_id("req-123")
        log_event("agent_query", routing="tool_calling", adapter="direct")
    finally:
        logging.getLogger("backend.audit").removeHandler(handler)
    assert len(handler.records) == 1
    parsed = json.loads(handler.records[0])
    assert parsed["event"] == "agent_query"
    assert parsed["request_id"] == "req-123"
    assert parsed["routing"] == "tool_calling"
    assert parsed["adapter"] == "direct"


def test_log_event_redacts_pii() -> None:
    handler = _capture()
    try:
        set_request_id("req-9")
        log_event("analytics_cache_hit", note="联系 13800138000 或 a@b.com")
    finally:
        logging.getLogger("backend.audit").removeHandler(handler)
    parsed = json.loads(handler.records[0])
    assert "13800138000" not in parsed["note"]
    assert "a@b.com" not in parsed["note"]


def test_request_id_defaults_to_empty() -> None:
    with patch(
        "backend.core.audit_log._request_id_var",
        __import__("contextvars").ContextVar("request_id", default=""),
    ):
        assert get_request_id() == ""
