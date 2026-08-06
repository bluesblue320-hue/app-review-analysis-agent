"""Deterministic answerability and answer validation guardrails."""

from __future__ import annotations

import re
from dataclasses import dataclass

UNSUPPORTED_INFERENCE_PATTERNS = (
    re.compile(r"(下个月|未来|以后|会不会|是否会).*(上升|下降|增长|减少|变好|变差)"),
    re.compile(r"(造成|导致|引起|因为).*(用户流失|流失多少|服务器接口|收入|营收)"),
    re.compile(r"(用户流失|收入|营收).*(多少|增加|减少|变化)"),
    re.compile(r"(一定|必然).*(原因|导致|上升|下降)"),
)

UNSUPPORTED_CLAIM_PATTERNS = (
    re.compile(r"\b\d+(?:\.\d+)*\b\s*是最(?:好|差)的"),
    re.compile(r"(?:一定|必然|直接推广|无需验证)"),
)


class UnsupportedClaimError(ValueError):
    """Raised when a model answer makes an unsupported absolute claim."""


@dataclass(frozen=True)
class AnswerabilityDecision:
    supported: bool
    answer: str = ""
    limitations: tuple[str, ...] = ()


def assess_answerability(question: str) -> AnswerabilityDecision:
    """Reject causal, predictive and commercial estimates absent from review data."""
    normalized = str(question or "").strip()
    if not any(
        pattern.search(normalized) for pattern in UNSUPPORTED_INFERENCE_PATTERNS
    ):
        return AnswerabilityDecision(supported=True)

    limitation = (
        "当前评论数据只能描述已有评论中的相关性和分布，无法判断或预估未来变化、"
        "因果关系、用户流失或收入影响。"
    )
    missing = (
        "需要补充实验或发布前后对照、活跃与留存、服务端故障、收入等独立数据后，"
        "才能验证该问题。"
    )
    return AnswerabilityDecision(
        supported=False,
        answer=f"{limitation}\n\n{missing}",
        limitations=(limitation, missing),
    )


def validate_supported_claims(answer: str) -> None:
    """Reject vague superlatives and certainty claims not defined by tool evidence."""
    normalized = str(answer or "").strip()
    if any(pattern.search(normalized) for pattern in UNSUPPORTED_CLAIM_PATTERNS):
        raise UnsupportedClaimError("模型回答包含缺少明确评价维度或证据的绝对化结论")
