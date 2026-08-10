"""PII redaction applied before any text leaves the process for an external model.

Redaction is a deterministic pre-processing step: it runs on the request text
(review bodies, titles and tool evidence) before model messages are built.
It must never rely on prompt instructions to redact.
"""

from __future__ import annotations

import re

PHONE_PLACEHOLDER = "[PHONE]"
EMAIL_PLACEHOLDER = "[EMAIL]"
CN_ID_PLACEHOLDER = "[CN_ID]"
BANK_CARD_PLACEHOLDER = "[BANK_CARD]"


# Mainland China mobile numbers: 1[3-9] followed by 9 digits.
PHONE_PATTERN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
# Common email shape; intentionally conservative to avoid over-matching.
EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9._%+-])"
)
# 18-digit ID card with checksum digit or 17 digits + X/x.
CN_ID_PATTERN = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
# Bank card: 16-19 digits, often grouped with spaces.
BANK_CARD_PATTERN = re.compile(r"(?<!\d)\d{16,19}(?!\d)")


def redact_text(text: object) -> str:
    """Replace phone, email, CN ID and bank card patterns with placeholders."""
    normalized = str(text or "")
    normalized = PHONE_PATTERN.sub(PHONE_PLACEHOLDER, normalized)
    normalized = EMAIL_PATTERN.sub(EMAIL_PLACEHOLDER, normalized)
    normalized = CN_ID_PATTERN.sub(CN_ID_PLACEHOLDER, normalized)
    normalized = BANK_CARD_PATTERN.sub(BANK_CARD_PLACEHOLDER, normalized)
    return normalized


def redact_recursive(value: object) -> object:
    """Recursively redact every string inside dict/list/tuple structures.

    Non-string leaves (numbers, booleans, None) pass through unchanged so
    aggregate statistics and ratings are never altered. This is the single
    boundary used before any payload is sent to an external model.
    """
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {key: redact_recursive(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [redact_recursive(item) for item in value]
    return value


def redact_mapping(values: dict[str, object]) -> dict[str, object]:
    """Apply :func:`redact_text` to every string value of a mapping."""
    redacted: dict[str, object] = {}
    for key, value in values.items():
        if isinstance(value, str):
            redacted[key] = redact_text(value)
        else:
            redacted[key] = value
    return redacted
