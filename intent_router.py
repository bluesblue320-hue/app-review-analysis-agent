"""Rule-based Chinese intent routing for review-analysis questions."""

# Rules are evaluated in priority order so an earlier intent always wins.
INTENT_RULES = (
    ("report_generation", ("报告",)),
    ("product_suggestion", ("产品优化", "优化建议", "产品建议")),
    ("risk_review_analysis", ("人工优先", "优先处理", "人工处理", "风险")),
    ("version_analysis", ("版本",)),
    ("trend_analysis", ("趋势",)),
    ("positive_review_analysis", ("最喜欢", "喜欢", "好评", "正向")),
    ("negative_review_analysis", ("差评", "负面", "不满")),
)

GENERAL_INTENT = "general_analysis"


def detect_intent(question: str) -> str:
    """Return the highest-priority intent whose keyword appears in *question*."""
    normalized_question = question.strip() if question else ""
    for intent, keywords in INTENT_RULES:
        if any(keyword in normalized_question for keyword in keywords):
            return intent
    return GENERAL_INTENT
