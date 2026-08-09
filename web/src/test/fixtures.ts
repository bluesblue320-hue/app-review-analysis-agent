import type { AgentQueryResponse, AIInsightResponse, AnalyticsSummary, DatasetUploadResponse, ReviewSearchResponse } from "../types/api";

export const dataset: DatasetUploadResponse = {
  dataset_id: "dataset_test",
  original_rows: 2,
  valid_rows: 2,
  removed_rows: 0,
  invalid_rating_rows: 0,
  invalid_reasons: {},
  columns: ["评分", "内容", "版本"],
  created_at: "2026-08-09T00:00:00Z",
  expires_at: "2026-09-08T00:00:00Z",
};

export const datasetB: DatasetUploadResponse = {
  ...dataset,
  dataset_id: "dataset_test_b",
  created_at: "2026-08-10T00:00:00Z",
  expires_at: "2026-09-09T00:00:00Z",
};

export const summary: AnalyticsSummary = {
  sample_size: 2,
  average_rating: 3,
  negative_ratio: 50,
  average_sentiment: 52,
  high_risk_count: 1,
  rating_distribution: [{ rating: 1, review_count: 1 }, { rating: 5, review_count: 1 }],
  sentiment_distribution: [{ range: "0-20", review_count: 1 }, { range: "80-100", review_count: 1 }],
  negative_keywords: [{ keyword: "封号", weight: 0.9 }],
  positive_keywords: [{ keyword: "好用", weight: 0.8 }],
  issue_priorities: [{ category: "账号类", priority_score: 8.1, severity: "high", review_count: 1, average_rating: 1, average_sentiment: 12, ai_severity: 0, ai_recommendation: "", representative_review: "无故封号" }],
  trend: [{ date: "2026-08-01", average_sentiment: 52, average_rating: 3, review_count: 2 }],
  high_risk_reviews: [],
  rating_sentiment_mismatches: [],
  rating_sentiment_mismatch_count: 0,
  reviews: [{ rating: 1, sentiment: 12, category: "账号类", risk_label: "高风险", content: "无故封号", version: "4.2.1" }],
  available_categories: ["账号类", "功能类"],
  scope_signature: "scope-1234567890",
  warnings: [],
};

export const reviewPage: ReviewSearchResponse = {
  items: summary.reviews,
  total: 21,
  offset: 0,
  limit: 20,
  next_offset: 20,
};

export const insightResponse: AIInsightResponse = {
  insight_id: "insight_dataset_a",
  insights: {
    summary: "旧数据集的 AI 洞察",
    pain_points: [],
    delighters: [],
    recommendations: [],
  },
  sample_size: 2,
  scope_signature: summary.scope_signature,
};

export const agentResponse: AgentQueryResponse = {
  intent: "version_analysis",
  answer: "4.2.1 版本的账号类问题增加。",
  scope: "filtered",
  scope_label: "当前筛选结果",
  sample_size: 2,
  scope_signature: summary.scope_signature,
  tables: { 版本对比: [{ 版本: "4.2.1", 评论数: 2 }] },
  routing: "tool_calling",
  tool_calls: [{ name: "version_compare", arguments: { versions: ["4.2.1"] }, status: "success", duration_ms: 12, error: null }],
  evidence: { call_1: { count: 2 } },
  evidence_call_ids: ["call_1"],
  warnings: ["样本量较小。"],
  limitations: ["仅基于上传评论。"],
};
