"""Shared-token authentication helpers."""

from __future__ import annotations

import hmac


def bearer_token_is_valid(authorization: str | None, expected_token: str) -> bool:
    if not expected_token:
        return True
    prefix = "Bearer "
    if not authorization or not authorization.startswith(prefix):
        return False
    supplied = authorization[len(prefix) :].strip()
    return bool(supplied) and hmac.compare_digest(supplied, expected_token)
