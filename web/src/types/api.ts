export interface APIErrorPayload {
  error: { code: string; message: string };
  request_id: string;
}

export class APIError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
    public readonly requestId: string,
  ) {
    super(message);
    this.name = "APIError";
  }
}

export interface DatasetUploadResponse {
  dataset_id: string;
  original_rows: number;
  valid_rows: number;
  removed_rows: number;
  invalid_rating_rows: number;
  invalid_reasons: Record<string, number>;
  columns: string[];
  created_at: string;
  expires_at: string;
}

export interface Filters {
  rating_min: number;
  rating_max: number;
  sentiment_min: number;
  sentiment_max: number;
  categories: string[];
  keyword: string;
  high_risk_only: boolean;
}

export const DEFAULT_FILTERS: Filters = {
  rating_min: 1,
  rating_max: 5,
  sentiment_min: 0,
  sentiment_max: 100,
  categories: [],
  keyword: "",
  high_risk_only: false,
};

export interface ReviewItem {
  rating: number;
  sentiment: number;
  category: string;
  risk_label: string;
  content: string;
  version: string | null;
}

export interface AnalyticsSummary {
  sample_size: number;
  average_rating: number;
  negative_ratio: number;
  average_sentiment: number;
  high_risk_count: number;
  rating_distribution: Array<{ rating: number; review_count: number }>;
  sentiment_distribution: Array<{ range: string; review_count: number }>;
  negative_keywords: Array<{ keyword: string; weight: number }>;
  positive_keywords: Array<{ keyword: string; weight: number }>;
  issue_priorities: IssuePriority[];
  trend: Array<{
    date: string;
    average_sentiment: number;
    average_rating: number;
    review_count: number;
  }>;
  high_risk_reviews: ReviewItem[];
  rating_sentiment_mismatches: ReviewItem[];
  rating_sentiment_mismatch_count: number;
  reviews: ReviewItem[];
  available_categories: string[];
  scope_signature: string;
  warnings: string[];
}

export interface IssuePriority {
  category: string;
  priority_score: number;
  severity: string;
  review_count: number;
  average_rating: number;
  average_sentiment: number;
  ai_severity: number;
  ai_recommendation: string;
  representative_review: string;
}

export interface ReviewSearchResponse {
  items: ReviewItem[];
  total: number;
  offset: number;
  limit: number;
  next_offset: number | null;
}

export type ReviewView = "all" | "high_risk" | "rating_sentiment_mismatch";

export interface AIConfigResponse {
  provider: string;
  model: string;
  configured: boolean;
}

export interface AIInsightContent {
  summary?: string;
  pain_points?: Array<Record<string, unknown> | string>;
  delighters?: Array<Record<string, unknown> | string>;
  sentiment_drivers?: string[];
  high_risk_reviews?: Array<Record<string, unknown>>;
  recommendations?: string[];
  report_copy?: string;
  [key: string]: unknown;
}

export interface AIInsightResponse {
  insight_id: string;
  insights: AIInsightContent;
  sample_size: number;
  scope_signature: string;
}

export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
  status: "success" | "failed" | "rejected";
  duration_ms: number;
  error: string | null;
}

export interface AgentQueryRequest {
  dataset_id: string;
  question: string;
  filters: Filters;
  scope: "full" | "filtered";
  insight_id?: string;
}

export interface AgentQueryResponse {
  intent: string;
  answer: string;
  scope: "full" | "filtered";
  scope_label: string;
  sample_size: number;
  scope_signature: string;
  tables: Record<string, Array<Record<string, unknown>>>;
  routing: "rule" | "tool_calling" | "rule_fallback";
  tool_calls: ToolCall[];
  evidence: Record<string, unknown>;
  evidence_call_ids: string[];
  warnings: string[];
  limitations: string[];
}
