# API、数据模型与配置契约

> 本文是各阶段共同遵守的契约。实现过程中如需修改，必须同步更新后端 Schema、OpenAPI、前端生成类型、测试和本文。

## 1. 通用约定

- API 前缀：`/api/v1`。
- JSON 字段使用 snake_case，时间使用 UTC ISO 8601。
- 除 `/health`、`/ready` 外，请求必须包含 `Authorization: Bearer <token>`。
- 客户端可传 `X-Request-ID`；服务端必须在所有响应头返回最终 request ID。
- 分页使用 `offset`/`limit`，`limit` 最大 100。
- 删除、过期和从未存在的数据集统一为 `dataset_not_found`。
- 业务错误通过稳定 `error.code` 判断，不依赖 message 文本。

## 2. 接口清单

| 方法 | 路径 | 鉴权 | 用途 |
| --- | --- | --- | --- |
| GET | `/health` | 否 | 进程存活 |
| GET | `/ready` | 否 | 数据库/可选 Redis 就绪状态 |
| POST | `/datasets` | 是 | 上传并预处理 CSV |
| GET | `/datasets/{dataset_id}` | 是 | 获取数据集元数据，建议新增 |
| DELETE | `/datasets/{dataset_id}` | 是 | 主动删除数据集及关联记录 |
| POST | `/analytics/summary` | 是 | 生成筛选范围摘要 |
| POST | `/analytics/reviews/search` | 是 | 分页查询评论 |
| GET | `/ai/config` | 是 | 返回模型是否可用，不返回密钥 |
| POST | `/ai/insights` | 是 | 创建范围匹配的 AI 洞察 |
| POST | `/agent/query` | 是 | 规则或受控 Tool Calling |
| POST | `/jobs` | 是 | 可选：提交长任务 |
| GET | `/jobs/{job_id}` | 是 | 可选：查询任务状态 |

## 3. 核心请求与响应

### 3.1 上传

`POST /api/v1/datasets` 使用 `multipart/form-data`，字段名 `file`。

成功 `201`：

```json
{
  "dataset_id": "dataset_xxx",
  "original_rows": 10000,
  "valid_rows": 9980,
  "invalid_rows": 20,
  "invalid_reasons": {"invalid_rating": 12, "empty_content": 8},
  "columns": ["评分", "内容", "时间", "版本"],
  "created_at": "2026-08-05T08:00:00Z",
  "expires_at": "2026-09-04T08:00:00Z"
}
```

### 3.2 删除

`DELETE /api/v1/datasets/{dataset_id}`：

```json
{"dataset_id": "dataset_xxx", "deleted": true}
```

成功响应仅代表数据库事务已提交；缓存失效失败必须记录并异步补偿，但不能让已删除数据再次从缓存返回。

### 3.3 筛选结构

```json
{
  "rating_min": 1,
  "rating_max": 5,
  "sentiment_min": 0,
  "sentiment_max": 100,
  "categories": [],
  "keyword": "",
  "high_risk_only": false
}
```

要求：范围上下界合法；类别去重和 trim；keyword 最大 200 字符；后端重新执行筛选，不信任前端统计值。

### 3.4 评论分页

请求：

```json
{
  "dataset_id": "dataset_xxx",
  "filters": {},
  "view": "high_risk",
  "offset": 0,
  "limit": 50
}
```

`view`：`all`、`high_risk`、`rating_sentiment_mismatch`。

响应：

```json
{
  "items": [
    {
      "review_id": 101,
      "rating": 1,
      "sentiment": 8.5,
      "category": "账号与安全",
      "risk_label": "高风险",
      "content": "评论正文"
    }
  ],
  "total": 132,
  "offset": 0,
  "limit": 50,
  "next_offset": 50
}
```

排序必须稳定，建议默认 `(row_number, id)`；筛选变化后前端重置 offset。

### 3.5 Agent

响应保留现有 `routing` 枚举：`rule`、`tool_calling`、`rule_fallback`。

```json
{
  "intent": "negative_review_analysis",
  "answer": "基于当前筛选范围……",
  "scope": "filtered",
  "scope_label": "当前筛选数据",
  "sample_size": 320,
  "scope_signature": "sha256...",
  "tables": {},
  "routing": "tool_calling",
  "tool_calls": [],
  "evidence": {},
  "warnings": [],
  "limitations": ["评论数据无法估计用户流失人数"]
}
```

`evidence` 只返回前端需要的安全摘要；完整模型上下文不通过 API 暴露。

## 4. 错误契约

```json
{
  "error": {
    "code": "validation_error",
    "message": "limit 不能大于 100。",
    "details": null
  },
  "request_id": "01J..."
}
```

主要错误码：

| HTTP | code | 场景 |
| --- | --- | --- |
| 400 | `invalid_csv_format` | CSV 结构无法解析 |
| 400 | `unsupported_encoding` | 编码不支持 |
| 401 | `unauthorized` | 未提供或令牌错误 |
| 404 | `dataset_not_found` | 数据集不存在、已删除或已过期 |
| 404 | `insight_not_found` | 洞察不存在或已过期 |
| 409 | `idempotency_conflict` | 相同幂等键对应不同请求 |
| 413 | `upload_too_large` | 超过 10 MB |
| 422 | `validation_error` | Schema 校验失败 |
| 422 | `dataset_row_limit_exceeded` | 超过 10,000 行 |
| 422 | `dataset_column_limit_exceeded` | 超过 50 列 |
| 422 | `review_text_too_long` | 单条超过 5,000 字 |
| 429 | `rate_limited` | 可选服务端限流 |
| 500 | `internal_error` | 未预期错误 |
| 503 | `not_ready` | 数据库或迁移未就绪 |

错误 message 可本地化，code 必须稳定。

## 5. 数据模型

### `datasets`

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `dataset_id` | varchar(100) | PK，不可枚举随机 ID |
| `filename` | varchar(255) | 仅 basename，不保存客户端路径 |
| `original_rows` | integer | >= 0 |
| `valid_rows` | integer | >= 0 |
| `invalid_rows` | integer | >= 0 |
| `columns_json` | json/jsonb | 字符串数组 |
| `status` | varchar(32) | processing/ready/failed/deleted |
| `created_at` | timestamptz | 非空 |
| `expires_at` | timestamptz | 非空、索引 |

### `reviews`

固定列：`id`、`dataset_id`、`row_number`、`rating`、`content`、`title`、`review_time`、`version`、`tokens`、`sentiment`、`category`、`risk_label`、`extra_json`。

索引候选：

- `(dataset_id, row_number)` unique。
- `(dataset_id, rating)`。
- `(dataset_id, sentiment)`。
- `(dataset_id, risk_label, row_number)`。
- `(dataset_id, category, row_number)`。

只有在真实查询计划证明有效后保留索引，避免上传写放大。

### `insights`

`insight_id` PK、`dataset_id` FK、`scope_signature`、`sample_size`、`provider`、`model`、`payload_json`、`created_at`、`expires_at`。

范围匹配要求 dataset、signature、sample_size 都一致；任何一项不匹配都不复用。

## 6. 配置矩阵

| 配置 | 开发默认 | 生产要求 |
| --- | --- | --- |
| `APP_ENV` | `development` | `production` |
| `APP_ACCESS_TOKEN` | 可空 | 必填，缺失拒绝启动 |
| `DATABASE_URL` | `sqlite:///...` | PostgreSQL URL，secret 提供 |
| `STORAGE_BACKEND` | `memory` 或 `database` | `database` |
| `REDIS_URL` | 可空 | 可选；启用缓存/任务时必填 |
| `DATA_RETENTION_DAYS` | `30` | 正整数 |
| `MAX_UPLOAD_SIZE_MB` | `10` | 最大不得高于批准值 |
| `MAX_DATASET_ROWS` | `10000` | 最大不得高于批准值 |
| `MAX_DATASET_COLUMNS` | `50` | 最大不得高于批准值 |
| `MAX_REVIEW_TEXT_CHARS` | `5000` | 最大不得高于批准值 |
| `CACHE_TTL_SECONDS` | `300` | 正整数 |
| `AGENT_PROVIDER` | `direct` | 灰度后可 `langchain` |
| `DEEPSEEK_API_KEY` | 可空 | 可选 secret，不得日志输出 |
| `ENABLE_DOCS` | `true` | 默认 `false` |
| `WEB_SESSION_SECRET` | 本地随机 | Next.js 上线时必填 |

配置加载时必须校验类型、范围和组合条件；错误应在启动期暴露。

## 7. 缓存与算法版本

缓存 key 必须包含：

- environment、cache schema version。
- dataset ID。
- 规范化 filters、view、offset/limit（仅分页缓存时）。
- insight ID 或明确的 null。
- `ANALYTICS_ALGORITHM_VERSION`。

更改预处理、筛选语义或指标算法时递增算法版本，避免旧缓存与新结果混用。
