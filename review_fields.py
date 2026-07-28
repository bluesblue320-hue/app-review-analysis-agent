"""Canonical column names used across review-analysis modules."""

RATING_COLUMN = "评分"
CONTENT_COLUMN = "内容"
SENTIMENT_COLUMN = "情绪指数"
TOKEN_COLUMN = "分词内容"
CATEGORY_COLUMN = "问题类型"
RISK_LABEL_COLUMN = "风险标签"
VERSION_COLUMN = "版本"
TIME_COLUMN = "时间"
TITLE_COLUMN = "标题"

TIME_COLUMN_CANDIDATES = (TIME_COLUMN, "日期", "评论时间", "发布时间")
REQUIRED_REVIEW_COLUMNS = frozenset({RATING_COLUMN, CONTENT_COLUMN})
