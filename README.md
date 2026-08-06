# App 评论舆情分析 Agent

一个面向 App Store 评论的中文舆情分析应用。项目由 Streamlit 前端、FastAPI 后端、确定性分析模块和受控 DeepSeek Tool Calling 组成，可完成数据清洗、情绪分析、看板筛选、版本对比、风险识别和自然语言问答。

## 核心能力

- 上传 CSV 后统一执行数据清洗、中文分词、情绪评分、问题分类和风险标记。
- 展示评论数、平均评分、差评占比、平均情绪、高风险评论、关键词和趋势。
- 支持评分、情绪、问题类型、关键词和高风险条件筛选。
- 后端重新执行所有筛选和指标计算，不信任前端传入的样本数量。
- Streamlit 只通过统一 API Client 获取数据和分析结果，不直接调用业务分析函数。
- 数据集和已生成的 AI 洞察保存在 FastAPI 进程内存中，分别使用 `dataset_id` 和 `insight_id` 标识。
- 可选接入 DeepSeek，生成结构化 AI 洞察并处理复杂 Agent 问题。

## 技术栈

- Python、Pandas、jieba、SnowNLP、scikit-learn
- Streamlit 前端与 Requests HTTP Client
- FastAPI、Pydantic、Uvicorn 后端
- pytest 单元测试、Mock 测试和 API 集成测试
- DeepSeek API（可选）

## 系统架构

```text
浏览器
  └─ Streamlit（app.py）
       └─ frontend/api_client.py
            └─ FastAPI（backend/main.py）
                 ├─ 数据集与 AI 洞察内存管理
                 ├─ 服务端筛选与看板汇总
                 ├─ AI 洞察
                 └─ 受控 Agent
                      ├─ 简单问题：规则快速路由
                      ├─ 复杂问题：DeepSeek Tool Calling
                      └─ 失败场景：原规则工作流降级

共享业务层
  ├─ review_preprocessing.py
  ├─ visual_analysis.py
  ├─ agent_workflow.py
  ├─ ai_analysis.py
  └─ review_fields.py
```

前后端复用同一套数据清洗和分析函数，没有复制第二套指标计算逻辑。

## 受控 Tool Calling

Agent 根据问题复杂度选择执行路径：

- 单一、明确的问题继续使用规则快速路由，不调用大模型。
- 复杂或跨分析维度的问题由 DeepSeek 选择只读分析工具。
- 单次请求最多执行 3 个工具。
- 工具名称必须通过白名单校验。
- 工具参数必须通过 Pydantic 校验，额外字段会被拒绝。
- 模型回答中的数字必须能够在工具结果中找到证据。
- API 返回工具名称、参数、状态、耗时和错误信息。
- 模型未配置、超时、响应异常、非法工具或数字校验失败时，自动降级到原规则工作流。

当前项目没有加入 RAG、LangChain、LangGraph、数据库或 Redis。

## API

FastAPI 默认监听 `http://127.0.0.1:8000`，接口统一使用 `/api/v1` 前缀：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | 服务健康检查 |
| `POST` | `/api/v1/datasets` | 上传 CSV 并返回 `dataset_id` |
| `POST` | `/api/v1/analytics/summary` | 对服务端数据集重新筛选并生成看板汇总 |
| `GET` | `/api/v1/ai/config` | 查询 AI 配置状态，不返回 API Key |
| `POST` | `/api/v1/ai/insights` | 生成并保存当前范围的 AI 洞察，返回 `insight_id` |
| `POST` | `/api/v1/agent/query` | 执行规则路由或受控 Tool Calling |

启动后可访问 `http://127.0.0.1:8000/docs` 查看 OpenAPI 文档。

## 快速开始

### 1. 克隆并安装依赖

```bash
git clone https://github.com/bluesblue320-hue/app-review-analysis-agent.git
cd app-review-analysis-agent
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS / Linux：

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### 2. 使用两个终端启动

在两个终端中激活同一个虚拟环境，然后分别运行：

```bash
# 终端一：启动 FastAPI
uvicorn backend.main:app --reload

# 终端二：启动 Streamlit
streamlit run app.py
```

验证后端：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

前端默认连接 `http://127.0.0.1:8000`。如后端地址不同，请在启动 Streamlit 前设置：

Windows PowerShell：

```powershell
$env:BACKEND_URL="https://your-backend.example.com"
$env:BACKEND_TIMEOUT_SECONDS="60"
streamlit run app.py
```

macOS / Linux：

```bash
BACKEND_URL="https://your-backend.example.com" \
BACKEND_TIMEOUT_SECONDS="60" \
streamlit run app.py
```

## DeepSeek 配置

不配置 DeepSeek 也可以使用看板、服务端统计和规则 Agent。复杂问题会自动降级到原规则工作流。

在项目根目录创建未提交的 `.env`：

```env
DEEPSEEK_API_KEY=your_api_key
AI_PROVIDER=deepseek
AI_MODEL=deepseek-v4-flash
```

也可以通过运行环境设置：

```env
LLM_TIMEOUT_SECONDS=60
LLM_MAX_TOOL_CALLS=3
MAX_UPLOAD_SIZE_MB=10
MAX_SUMMARY_REVIEW_ROWS=100
```

`LLM_MAX_TOOL_CALLS` 即使配置为更大的值，也会被服务端限制为最多 3 次。

## CSV 数据格式

上传文件必须至少包含 `评分` 和 `内容` 两列：

| 字段 | 必需 | 说明 |
| --- | --- | --- |
| `评分` | 是 | 1～5 星评分 |
| `内容` | 是 | 评论正文 |
| `时间` / `日期` / `评论时间` / `发布时间` | 否 | 用于趋势分析 |
| `版本` | 否 | 用于版本对比 |
| `标题` | 否 | 用于展示评论标题 |

```csv
时间,评分,版本,标题,内容
2026-07-01,1,9.2.0,无法登录,更新后一直提示登录失败
2026-07-02,5,9.2.0,体验不错,页面流畅而且内容推荐很准确
```

后端会生成 `分词内容`、`情绪指数`、`问题类型` 和 `风险标签` 等分析字段。

## 项目结构

```text
.
├─ app.py                         # Streamlit 页面入口
├─ frontend/api_client.py         # 统一前端 HTTP Client
├─ backend/
│  ├─ main.py                     # FastAPI 应用入口与统一异常处理
│  ├─ routers/                    # API 路由
│  ├─ schemas/                    # Pydantic 请求与响应模型
│  ├─ services/                   # 数据集、Insight Store、分析、AI 和 Agent 服务
│  ├─ core/                       # 配置、异常与 JSON 序列化
│  └─ agent/                      # Tool Calling 定义、执行器与编排
├─ review_preprocessing.py        # 数据清洗、分词和情绪计算
├─ review_fields.py               # 统一业务字段常量
├─ visual_analysis.py             # 确定性指标和筛选逻辑
├─ agent_workflow.py              # 原规则分析工作流与降级能力
├─ ai_analysis.py                 # DeepSeek AI 洞察
├─ nlp_analysis.py                # 离线 NLP 分析入口
├─ requirements.txt               # 运行与测试依赖
└─ tests/
   └─ integration/                # FastAPI 端到端接口测试
```

## 运行测试

```bash
python -m pytest -v
```

测试不会真实调用 DeepSeek。覆盖范围包括：

- 数据清洗、分词与情绪计算。
- 看板指标、筛选、版本分析和范围签名。
- API 上传、服务端筛选、异常响应和 JSON 序列化。
- API Client 的不可访问、超时、非 200 和非法 JSON 处理。
- 规则快路由、单工具、多工具、非法工具、参数错误、三次调用上限和超时降级。

## 运行与数据限制

- 数据集和 AI 洞察只保存在 FastAPI 进程内存中，服务重启后会丢失。
- 不要使用多个互不共享内存的后端 worker，否则同一 `dataset_id` 或 `insight_id` 可能无法在不同 worker 间访问。
- 上传真实用户评论前，请确认数据授权、隐私和合规要求。
- 启用 DeepSeek 后，部分工具结果或评论样本可能被发送到模型服务。
- `.env`、`.streamlit/secrets.toml`、CSV、日志和虚拟环境已被 Git 忽略，请勿提交真实密钥。

## Agent 评估

仓库内置可重复运行的 Agent 自动化评估（`evaluation/`），用于量化验证路由、工具选择、参数提取、非法工具拦截、数字可信度和降级能力。默认 Mock 模式不调用真实 DeepSeek，可安全用于本地开发和 CI：

```bash
python -m evaluation.evaluate_agent --mode mock
python -m evaluation.evaluate_agent --mode mock --fail-under
python -m evaluation.evaluate_agent --mode live --output-dir evaluation/reports/live
```

详细说明见 `evaluation/README.md`。

## 示例数据采集

仓库包含 App Store 评论采集脚本：

```bash
python spider.py
```

默认配置用于抓取小红书中国区 App Store 评论。使用前请检查 `spider.py` 中的应用 ID、页数和目标平台使用条款。
