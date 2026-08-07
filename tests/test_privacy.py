"""PII redaction applied before any text reaches an external model."""

from __future__ import annotations

from backend.core.privacy import (
    BANK_CARD_PLACEHOLDER,
    CN_ID_PLACEHOLDER,
    EMAIL_PLACEHOLDER,
    PHONE_PLACEHOLDER,
    redact_mapping,
    redact_text,
)


def test_phone_number_is_redacted() -> None:
    assert redact_text("联系我 13812345678 谢谢") == (
        f"联系我 {PHONE_PLACEHOLDER} 谢谢"
    )


def test_email_is_redacted() -> None:
    assert redact_text("发送到 user@example.com 即可") == (
        f"发送到 {EMAIL_PLACEHOLDER} 即可"
    )


def test_cn_id_is_redacted() -> None:
    assert redact_text("身份证 110101199003071234 已上传") == (
        f"身份证 {CN_ID_PLACEHOLDER} 已上传"
    )


def test_bank_card_is_redacted() -> None:
    assert redact_text("卡号 6222021234567890123 请处理") == (
        f"卡号 {BANK_CARD_PLACEHOLDER} 请处理"
    )


def test_multiple_pii_types_in_one_text() -> None:
    text = "手机 13812345678 邮箱 a@b.com 身份证 110101199003071234"
    redacted = redact_text(text)
    assert PHONE_PLACEHOLDER in redacted
    assert EMAIL_PLACEHOLDER in redacted
    assert CN_ID_PLACEHOLDER in redacted
    assert "13812345678" not in redacted
    assert "a@b.com" not in redacted
    assert "110101199003071234" not in redacted


def test_short_digit_runs_are_not_over_redacted() -> None:
    text = "评分 5 分，共 128 条评论，版本 2.0.0"
    assert redact_text(text) == text


def test_non_string_values_pass_through_redact_mapping() -> None:
    values = {"content": "手机 13812345678", "count": 42, "ok": True}
    redacted = redact_mapping(values)
    assert redacted["content"] == f"手机 {PHONE_PLACEHOLDER}"
    assert redacted["count"] == 42
    assert redacted["ok"] is True
