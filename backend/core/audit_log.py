"""Structured audit logging for service-level events.

Emits one JSON line per event with the active request ID (propagated via
contextvars so async handlers and nested service calls share it). All fields
are whitelisted; no token, PII, review body or full prompt is ever logged.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Any

from backend.core.privacy import redact_text

logger = logging.getLogger("backend.audit")
_request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)


def get_request_id() -> str:
    return _request_id_var.get()


def log_event(event: str, **fields: Any) -> None:
    """Emit a structured JSON log line with the active request ID."""
    safe_fields: dict[str, Any] = {}
    for key, value in fields.items():
        if isinstance(value, str):
            safe_fields[key] = redact_text(value)
        else:
            safe_fields[key] = value
    record = {
        "event": event,
        "request_id": get_request_id(),
        **safe_fields,
    }
    logger.info(json.dumps(record, ensure_ascii=False))
