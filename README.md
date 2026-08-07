# App 评论舆情分析 Agent

一个面向 App Store 评论的中文舆情分析应用。项目由 Streamlit 前端、FastAPI 后端、确定性分析模块和受控 DeepSeek Agent 组成，可完成数据清洗、情绪分析、看板筛选、版本对比、风险识别、AI 洞察和自然语言问答。支持 Direct / LangChain 双 Agent Adapter、PostgreSQL 持久化与 Redis 缓存，生产环境通过 Docker Compose 部署。

> 本项目所有性能、覆盖率和评估数字均来自仓库内可重复运行的测试与报告（`evaluation/reports/`、`docs/execution/`），未宣称未测量的结果。

## 核心能力

- 上传 CSV 后统一执行数据清洗、中文分词、情绪评分、问题分类和风险标记。
- 展示评论数、平均评分、差评占比、平均情绪、高风险评论、关键词、趋势和问题优先级。
- 支持评分、情绪、问题类型、关键词和高风险条件筛选；筛选使用 `st.form`，仅提交时请求。
- 后端重新执行所有筛选和指标计算，不信任前端传入的样本数量。
- 评论池使用 `view + offset + limit` 分页，不依赖摘要前 100 条预览。
- 受控 Tool Calling Agent：规则快速路由 / DeepSeek 工具调用 / 规则降级三路径。
- Direct 与 LangChain 双 Adapter，通过 `AGENT_ADAPTER` 切换，共享同一 Orchestrator。
- 数据集与 AI 洞察持久化到 PostgreSQL（可重启恢复），确定性摘要缓存到 Redis。
- AI 洞察首次模型调用前要求当前会话确认。

## 技术栈

- Python 3.12、Pandas、jieba、SnowNLP、scikit-learn
- Streamlit 前端与 Requests HTTP Client
- FastAPI、Pydantic、Uvicorn、SQLAlchemy 2、Alembic
- PostgreSQL 16、Redis 7
- LangChain（`ChatDeepSeek`，可选 extra）
- pytest、pytest-cov、Ruff、GitHub Actions

## 系统架构

```text
浏览器
  └─ Streamlit（app.py → frontend/components.py，仅装配与展示）
       └─ frontend/api_client.py（唯一 HTTP Client，令牌仅存 Session）
            └─ FastAPI（backend/main.py）
                 ├─ 数据集 Repository（内存 / PostgreSQL + Alembic）
                 ├─ Insight Repository（fingerprint 去重 + 唯一约束）
                 ├─ 确定性分析（评分过滤、情绪、关键词、趋势、优先级）
                 ├─ Redis 缓存（分析摘要）+ Insight 短锁（减少重复模型调用）
                 └─ 受控 Agent（双 Adapter，单次规划最多选择 3 个只读分析工具）

共享业务层
  ├─ review_preprocessing.py   # 清洗、分词、情绪
  ├─ visual_analysis.py        # 确定性指标与筛选
  ├─ agent_workflow.py         # 原规则工作流与降级
  ├─ ai_analysis.py            # DeepSeek 洞察
  └─ review_fields.py          # 统一字段常量
```

## 八个核心工具与机制

| # | 机制 | 说明 |
| --- | --- | --- |
| 1 | 评分严格过滤 | 1～5 范围外评分删除并统计原因（`removed_rows/invalid_reasons`） |
| 2 | 服务端范围签名 | `sha256(content_hash + canonical_filters + analysis_version)` |
| 3 | Insight fingerprint | 固定字段顺序 SHA-256，数据库 `UNIQUE` 保证最终单条记录 |
| 4 | 原子 insert-or-get-existing | 唯一约束冲突回滚后读取已有记录，不返回 500 |
| 5 | 受控 Tool Calling | 白名单 + Pydantic 参数校验 + 单次规划最多选择 3 个只读工具 |
| 6 | 回答可信度校验 | 数字须有工具证据；绝对结论受 Guardrail 约束 |
| 7 | 规则降级 | 模型未配置/超时/非法工具/校验失败 → 原规则工作流 |
| 8 | PII 脱敏 | 构造模型消息前统一替换手机/邮箱/身份证/银行卡 |

## 受控 Tool Calling（Agent）

Agent 根据问题复杂度选择执行路径：

- 单一、明确的问题使用规则快速路由，不调用大模型。
- 复杂或跨维度问题由 DeepSeek（Direct 或 LangChain `bind_tools`）选择只读分析工具。
- 单次请求最多 3 个工具；工具名称白名单校验；参数 Pydantic 校验。
- 模型回答数字必须能在工具结果中找到证据；伪造 evidence ID 触发降级。
- 未配置、超时、非法 JSON、非法工具或校验失败时自动降级到原规则工作流。
- 响应返回 intent、routing、tool calls（名称/状态/耗时/参数/错误）、evidence_call_ids、limitations、warnings。

### 切换 Adapter

```bash
AGENT_ADAPTER=direct      # 默认：原生 DeepSeek Tool Calling
AGENT_ADAPTER=langchain   # LangChain ChatDeepSeek（需要 pip install -e ".[langchain]"）
```

## API

FastAPI 默认监听 `http://127.0.0.1:8000`，统一 `/api/v1` 前缀：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | 存活检查 |
| `GET` | `/api/v1/ready` | 就绪检查（存储不可达返回 503） |
| `POST` | `/api/v1/datasets` | 上传 CSV 返回 `dataset_id` 与统计 |
| `POST` | `/api/v1/analytics/summary` | 服务端筛选并生成看板汇总 |
| `POST` | `/api/v1/reviews/search` | `view + offset + limit` 评论分页 |
| `GET` | `/api/v1/ai/config` | AI 配置状态（不含 API Key） |
| `POST` | `/api/v1/ai/insights` | 生成并保存 AI 洞察，返回 `insight_id` |
| `POST` | `/api/v1/agent/query` | 规则路由或受控 Tool Calling |

所有接口（除 health/ready）需要 `Authorization: Bearer <token>`；启动前设置 `APP_ACCESS_TOKEN`。开发环境默认不启用鉴权（`APP_ENV=development`）；`APP_ENV=production` 时 `APP_ACCESS_TOKEN` 必填。

## 快速开始（本地）

### 1. 安装

```bash
git clone https://github.com/bluesblue320-hue/app-review-analysis-agent.git
cd app-review-analysis-agent
python -m venv .venv
source .venv/bin/activate        # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

### 2. 启动（两个终端）

```bash
# 终端一：FastAPI（默认 SQLite + 内存缓存）
uvicorn backend.main:app --reload

# 终端二：Streamlit
streamlit run app.py
```

验证：`curl http://127.0.0.1:8000/api/v1/health`

### 3. DeepSeek 配置（可选）

创建未提交的 `.env`：

```env
DEEPSEEK_API_KEY=your_api_key
AI_PROVIDER=deepseek
AI_MODEL=deepseek-v4-flash
AGENT_ADAPTER=direct
```

不配置 DeepSeek 也可使用看板与规则 Agent；复杂问题自动降级。

### 4. 生产存储（PostgreSQL + Redis + 迁移）

```bash
export DATABASE_URL="postgresql+psycopg2://app:app@localhost:5432/app"
export REDIS_URL="redis://localhost:6379/0"
export STORAGE_BACKEND=database
alembic upgrade head
uvicorn backend.main:app --workers 1
```

## Docker Compose（生产）

```bash
cp .env.example .env        # 设置 APP_ACCESS_TOKEN（必填）、DEEPSEEK_API_KEY
docker compose up --build -d
```

- 仅 Streamlit `8501` 暴露到宿主机；FastAPI、PostgreSQL、Redis 在内部网络。
- `api` 容器启动时先 `alembic upgrade head` 再启动 Uvicorn 单 worker。
- 数据持久化到 `postgres_data` / `redis_data` 卷。
- 就绪探针：`curl /api/v1/ready`。

## CSV 数据格式

至少包含 `评分`（1～5）与 `内容`：

| 字段 | 必需 | 说明 |
| --- | --- | --- |
| `评分` | 是 | 1～5 星 |
| `内容` | 是 | 评论正文 |
| `时间` / `日期` / `评论时间` / `发布时间` | 否 | 趋势分析 |
| `版本` | 否 | 版本对比 |
| `标题` | 否 | 评论标题 |

后端生成 `分词内容`、`情绪指数`、`问题类型`、`风险标签` 等分析字段。

## 测试、质量与评估

```bash
python -m ruff check .                    # Lint
python -m ruff format --check .           # 格式
python -m pytest                          # 全量测试
python -m pytest --cov=. --cov-report=xml # 覆盖率（门禁 80%）
python -m compileall -q backend frontend evaluation tests

# Agent 评估（Mock 为确定性 CI 门禁）
python -m evaluation.evaluate_agent --mode mock --adapter direct --fail-under
python -m evaluation.evaluate_agent --mode mock --adapter langchain --fail-under
python -m evaluation.evaluate_agent --mode live --output-dir evaluation/reports/live  # 需要 API Key

# 数据 / 性能 / 故障 / 备份
python -m evaluation.generate_fixture --rows 10000
python -m evaluation.benchmark --rows 10000 --runs 3
python -m evaluation.failure_drill
python -m evaluation.backup_drill --database-url postgresql+psycopg2://app:app@localhost:5432/app
```

### 当前基线（仓库内可复现）

- 完整 pytest：**340 passed + 3 subtests**。
- 全项目覆盖率：**82.76%**（阶段 5 实测；CI Linux 以 80% 硬门禁复核）。
- Agent Mock 评估：**Direct 46/46、LangChain 46/46**。
- 性能（10,000 行 × 3 次，`evaluation/reports/perf/benchmark.json`）：上传 P95 24.8s、预热摘要 P95 56ms、分页 P95 2.6ms、规则 Agent P95 188ms。
- 故障演练 6/6 通过（`evaluation/reports/failure-drill/report.json`）。

## 数据模型与迁移

- `datasets`：`content_hash`、`analysis_version`、统计字段、过期时间。
- `reviews`：`(dataset_id, row_number)` 唯一；固定分析字段独立列，其余入 `payload_json`。
- `insights`：`insight_fingerprint` 唯一；`provider/model_name/analysis_version`；过期时间。
- 迁移：`alembic upgrade head` / `downgrade base`（生产不自动 downgrade）。

## Redis 契约

- 分析缓存 Key：`ara:{env}:v1:analytics:{dataset_id}:{scope_signature}:{analysis_type}:{insight_id_or_none}`。
- Insight 短锁：`ara:{env}:v1:lock:insight:{dataset_id}:{scope_signature}`（`SET NX EX` + token 安全释放）。
- 缓存值含 `schema_version`，版本不匹配视为 miss。
- Redis 故障全部降级：读失败→miss、写失败→忽略、锁失败→放行；数据唯一性始终由 PostgreSQL 约束保证。

## 降级与故障行为

| 故障 | 行为 |
| --- | --- |
| DeepSeek 未配置 / 超时 / 5xx / 非法 JSON | Agent 降级到规则工作流；AI 洞察报可读错误 |
| Redis 断开 / 超时 | 缓存 miss、短锁放行；功能不受影响（允许重复模型调用，PG 兜底唯一） |
| PostgreSQL 不可用 | `/ready` 返回 503；请求返回明确服务错误 |
| 数据集过期 / 删除 | 返回 `dataset_not_found`；缓存残留不影响（读前验证存在性） |
| 非法工具 / 参数 | 工具被拒 / 校验失败；整体降级到规则 |

## 已知限制

- 本地默认使用 SQLite + 内存缓存（`STORAGE_BACKEND` 默认按 `APP_ENV` 选择）；生产必须配置 PostgreSQL。
- LangChain 依赖锁定 `langchain-core==0.3.60` 组合（规避 `uuid_utils` 原生扩展在受控系统的加载问题），升级需在 CI 验证。
- Windows 开发机全量 coverage 偶发 Segfault（pandas/jieba 原生扩展与 coverage 追踪器冲突）；CI Linux 为最终覆盖验收环境。
- Live 评估需要 `DEEPSEEK_API_KEY`，结果随模型波动，不作为普通 PR CI 门禁。
- 上传真实用户评论前请确认数据授权、隐私与合规要求；部分工具结果或评论样本可能发送到模型服务。

## 项目结构

```text
.
├─ app.py                         # Streamlit 装配入口（仅编排）
├─ frontend/
│  ├─ api_client.py               # 统一 HTTP Client
│  └─ components.py               # Streamlit 组件（上传/筛选/看板/分页/AI/Agent）
├─ backend/
│  ├─ main.py                     # FastAPI 入口
│  ├─ routers/ schemas/ services/ core/
│  ├─ agent/                      # Tool Calling + 双 Adapter
│  └─ storage/                    # SQLAlchemy 模型与运行
├─ alembic/                       # 数据库迁移
├─ evaluation/                    # Agent 评估、基准、故障演练、备份演练、夹具
├─ Dockerfile.api / Dockerfile.streamlit / docker-compose.yml
├─ pyproject.toml                 # 依赖（base/langchain/dev）
└─ tests/                         # 单元 + 集成测试
```

## 示例数据采集

```bash
python spider.py
```

默认用于抓取小红书中国区 App Store 评论；使用前请检查应用 ID、页数与平台条款。
