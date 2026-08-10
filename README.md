# App Review Intelligence

面向 App Store 中文评论的工程化 AI 分析应用。浏览器端使用 React + TypeScript，所有数据清洗、情绪分析、关键词、问题分类、风险计算、指标、AI 洞察和受控 Tool Calling 均由 FastAPI 后端负责。生产环境由 Nginx 提供静态文件、反向代理 API，并在服务器侧注入共享访问令牌。

## 核心能力

- CSV 拖放上传，后端统一校验、清洗、分词、情绪评分、问题分类和风险标记。
- 草稿筛选与提交筛选分离；只有点击“应用筛选”才重新请求后端。
- KPI、评分/情绪分布、评分情绪散点、正负关键词、趋势和问题优先级图表。
- 评论池使用服务端 `view + offset + limit` 分页，不下载完整数据集。
- AI 洞察与 `dataset_id + scope_signature` 绑定，当前会话首次模型调用前必须确认。
- Agent 会话展示意图、路由、工具状态/参数/耗时/错误、证据 ID、表格、warnings 和 limitations。
- Direct / LangChain 双 Adapter 共享同一受控 Agent Orchestrator；模型不可用时保留规则降级。
- PostgreSQL 持久化数据集与洞察，Redis 缓存确定性摘要并提供短锁。

## 架构

```text
Browser
  └─ React + TypeScript (Vite, TanStack Query, ECharts, Tailwind CSS)
       └─ /api/* same-origin requests
            └─ Nginx
                 ├─ /             → React static files + SPA fallback
                 └─ /api/*        → FastAPI + server-side Bearer token
                      ├─ Deterministic analytics / preprocessing
                      ├─ Controlled Agent (Direct / LangChain)
                      ├─ AI insights
                      ├─ PostgreSQL + Alembic
                      └─ Redis cache + insight lock
```

FastAPI 是唯一业务后端。React 不直接访问 DeepSeek、PostgreSQL 或 Redis，也不复制 Python 分析逻辑。

## 技术栈

- Web：React 19、TypeScript、Vite、TanStack Query、ECharts、Tailwind CSS
- API：Python 3.12、FastAPI、Pydantic、Uvicorn
- 分析：Pandas、jieba、SnowNLP、scikit-learn、pyecharts（离线词云模块）
- Agent：受控工具白名单、Direct Adapter、LangChain Adapter、规则降级
- 数据：PostgreSQL 16、SQLAlchemy 2、Alembic、Redis 7
- 质量：pytest、pytest-cov、Ruff、Vitest、React Testing Library、ESLint、GitHub Actions

## API 契约

统一前缀是 `/api/v1`，只在 `web/src/api/client.ts` 定义一次。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | 存活检查（公开） |
| `GET` | `/api/v1/ready` | PostgreSQL migration / Redis 就绪状态（公开） |
| `POST` | `/api/v1/datasets` | multipart CSV 上传 |
| `DELETE` | `/api/v1/datasets/{dataset_id}` | 删除数据集及关联洞察/缓存 |
| `POST` | `/api/v1/analytics/summary` | 服务端筛选与完整看板摘要 |
| `POST` | `/api/v1/analytics/reviews/search` | 评论服务端分页 |
| `GET` | `/api/v1/ai/config` | AI provider/model/configured 状态，不返回密钥 |
| `POST` | `/api/v1/ai/insights` | 生成或复用当前范围洞察 |
| `POST` | `/api/v1/agent/query` | 规则路由或受控 Tool Calling |

错误统一为：

```json
{
  "error": { "code": "validation_error", "message": "..." },
  "request_id": "..."
}
```

Web client 统一处理 timeout、网络错误、非法 JSON、401、404、409、413、415、422、500/503，并发送/展示 `X-Request-ID`。

## CSV 格式

必须包含 `评分`（1～5）与 `内容`。可选字段包括 `版本`、`时间`、`日期`、`评论时间`、`发布时间` 和 `标题`。评论预览/分页响应会返回可空的 `version`。

## 本地开发

### 后端

项目要求 Python 3.12。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,langchain]"
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

开发环境默认使用内存 Store 且未配置 `APP_ACCESS_TOKEN` 时允许请求。需要数据库存储时配置 `DATABASE_URL`、`STORAGE_BACKEND=database` 并运行 `alembic upgrade head`。

### 前端

```powershell
cd web
npm ci
npm run dev
```

打开 `http://127.0.0.1:5173`。Vite 将 `/api` 代理到 `http://127.0.0.1:8000`，无需 CORS，也不需要浏览器 token。

## 生产部署

复制环境模板并设置强随机令牌：

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

默认访问 `http://127.0.0.1:8080`，可通过 `WEB_PORT` 修改宿主端口。Compose 只发布 `web` 的 Nginx 端口；FastAPI、PostgreSQL 和 Redis 只在内部网络可达。API 容器先运行 `alembic upgrade head`，再启动单 Uvicorn worker。

### 生产服务访问保护

`APP_ACCESS_TOKEN` 用于保护 Nginx → FastAPI 的内部服务访问，并让浏览器无需持有服务器共享 Secret。它不是最终用户身份认证：当前版本未实现用户登录、JWT、RBAC 或多用户身份隔离；能够访问 Web 页面的用户共享同一条由 Nginx 注入的服务器侧令牌。

- `APP_ACCESS_TOKEN` 只存在于 Compose/server environment，并在 Nginx 运行时模板展开后作为 `Authorization: Bearer ...` 注入代理请求。
- React bundle 不读取 `APP_ACCESS_TOKEN`，没有 `VITE_APP_ACCESS_TOKEN`，也不把共享 token 写入 localStorage/sessionStorage。
- `DEEPSEEK_API_KEY` 只传给 FastAPI 容器；`GET /ai/config` 只暴露 provider、model 和 configured 布尔值。
- 浏览器与 Nginx 同源通信；Nginx 将 `X-Request-ID` 传给 FastAPI。

## 环境变量

| 变量 | 用途 | 生产要求 |
| --- | --- | --- |
| `APP_ENV` | `development` / `production` | Compose 固定为 production |
| `APP_ACCESS_TOKEN` | API 共享访问令牌 | 必填，只在 api/web 容器运行时存在 |
| `DEEPSEEK_API_KEY` | AI 洞察与复杂 Tool Calling | 可选，只在 api 容器 |
| `AI_PROVIDER` / `AI_MODEL` | 模型配置 | 可选 |
| `AGENT_ADAPTER` | `direct` / `langchain` | 默认 direct |
| `DATABASE_URL` | PostgreSQL DSN | 生产必需 |
| `REDIS_URL` | 缓存/短锁 | 生产建议 |
| `STORAGE_BACKEND` | `memory` / `database` | 生产为 database |
| `DATA_RETENTION_DAYS` | 数据保留天数 | 默认 30 |
| `MAX_UPLOAD_SIZE_MB` | FastAPI 上传限制 | 默认 10 |
| `LLM_TIMEOUT_SECONDS` | 模型超时 | 默认 60 |
| `LLM_MAX_TOOL_CALLS` | 单次最多工具调用 | 上限 3 |
| `WEB_PORT` | Nginx 宿主端口 | 默认 8080 |

## 测试与质量

```powershell
# Python
python -m ruff check .
python -m ruff format --check .
python -m pytest
python -m pytest --cov=. --cov-report=term-missing --cov-fail-under=80

# 确定性 Agent 门禁（不会调用真实模型）
python -m evaluation.evaluate_agent --mode mock --adapter direct --fail-under
python -m evaluation.evaluate_agent --mode mock --adapter langchain --fail-under

# Web
cd web
npm run lint
npm run typecheck
npm run test
npm run build

# 生产镜像与 Compose 配置
cd ..
$env:APP_ACCESS_TOKEN = "ci-validation-token"
docker build -f Dockerfile.api -t app-review-api:test .
docker build -f Dockerfile.web -t app-review-web:test .
docker compose config --quiet
```

GitHub Actions 保留 Python、PostgreSQL、Redis、Alembic 与双 Adapter mock evaluation 门禁，并设置独立 frontend 和 docker-build job；前端 job 还会检查生产 Bundle，防止服务端 Secret 配置被打包进浏览器。历史性能/评估结果保存在 `evaluation/reports/` 与 `docs/execution/`；这些历史报告不等同于当前机器重新测量的结果。

## 项目结构

```text
.
├─ web/                          # React + TypeScript Web application
│  ├─ src/api/                   # 唯一 HTTP 边界
│  ├─ src/components/            # upload/filter/charts/reviews/AI/Agent
│  ├─ src/context/               # dataset session state
│  ├─ src/pages/Dashboard.tsx
│  └─ src/test/                  # Vitest + RTL 核心路径测试
├─ backend/
│  ├─ main.py                    # FastAPI entrypoint
│  ├─ routers/ schemas/ services/ core/
│  ├─ agent/                     # Orchestrator、工具与双 Adapter
│  └─ storage/                   # SQLAlchemy runtime
├─ alembic/                      # PostgreSQL migrations
├─ evaluation/                   # Agent evaluation / benchmark / drills
├─ tests/                        # Python unit + integration tests
├─ Dockerfile.api
├─ Dockerfile.web                # Node build → Nginx runtime
├─ nginx.conf.template
└─ docker-compose.yml            # postgres + redis + api + web
```

## 已知限制

- `APP_ACCESS_TOKEN` 只提供 Nginx → FastAPI 的共享服务访问保护，不提供最终用户登录、JWT、RBAC 或多用户认证。
- 散点图使用摘要 API 返回的最多 100 条预览数据；评论池仍严格使用服务端分页。
- AI 洞察 schema 的 `insights` 内容由模型返回，因此 UI 对未知扩展字段采用安全降级展示。
- Live Agent evaluation 需要显式 `--mode live` 和有效模型密钥，不属于普通 CI 门禁。
- 上传真实评论前应确认授权、隐私与外部模型数据处理要求。
