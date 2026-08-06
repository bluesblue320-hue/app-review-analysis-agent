# 阶段 1：Agent 正确性与质量基线

> 周期：第 1–2 周  
> 目标：让 Agent 对可回答与不可回答问题都给出可验证、可降级、无越权的结果，并建立不可绕过的 CI 质量门禁。

## 1. 范围

本阶段包含：

- 确定性可回答性判断。
- 受控只读工具执行。
- 严格结构化模型输出。
- 数字、结论和证据 ID 校验。
- 提示注入与绝对化结论防护。
- `limitations` API 契约。
- Ruff、pytest-cov、GitHub Actions 和 Mock Agent 评估。

本阶段不包含数据库迁移、Redis 缓存、Next.js 或异步任务。

## 2. 可回答性策略

在模型路由之前执行确定性判断，问题分为三类：

| 类型 | 示例 | 行为 |
| --- | --- | --- |
| 可由评论数据回答 | 差评集中在哪些问题、哪个版本评分最低 | 执行相关只读工具，基于证据回答 |
| 只能描述、不能推断 | 这些评论会导致多少用户流失、收入下降多少 | 仍执行相关工具描述现状，但必须明确“当前评论数据无法判断或预估”，列出缺失数据 |
| 越权或无评价维度 | 忽略规则、执行删除；哪个方案最好；一定能提升留存吗 | 拒绝越权动作；要求明确评价维度或返回限制，不能生成确定性结论 |

不可回答问题必须至少说明：

1. 当前评论数据能说明什么。
2. 当前数据不能说明什么。
3. 缺少哪些数据，例如用户 cohort、流失定义、实验组/对照组、收入事件、时间窗口或版本曝光量。
4. 若要进一步分析，应如何补充数据，但不能伪造预测值。

## 3. 结构化输出契约

模型合成层只接受以下逻辑结构：

```json
{
  "answer": "基于工具证据的中文回答",
  "limitations": ["当前评论样本不能代表全部活跃用户"],
  "evidence_call_ids": ["call_1", "call_2"]
}
```

服务端验证规则：

- `answer` 非空，长度受限。
- `limitations` 必须是字符串数组，不接受模型返回对象或自由格式文本。
- `evidence_call_ids` 只能引用本次请求中状态为 `success` 的工具调用。
- 回答中的业务数字必须能在引用工具结果中找到；序号、日期和版本号需采用单独的解析规则，避免误判。
- 出现“最好、一定、必然、直接推广、保证提升”等表达时，必须同时存在明确评价维度和证据，否则拒绝结果。
- 任一校验失败，进入规则降级；API 保持 `routing=rule_fallback`，并写入不含敏感内容的 warning。

## 4. 提示注入防护

### 输入边界

- 系统提示明确：用户问题、评论正文、标题、上传附加列都属于不可信数据。
- 评论中的“忽略之前指令”“调用某工具”“输出密钥”等内容只能作为评论样本，不能改变工具白名单。
- 工具名由服务端静态注册；参数由 Pydantic `extra=forbid` 校验。
- 单次请求最多 3 个只读工具调用。

### 输出边界

- 不返回环境变量、密钥、Authorization 头、数据库 URL 或完整系统提示。
- 工具错误只返回稳定错误类型，不把栈、SQL 或内部路径交给模型。
- 对抗输入失败时，优先规则降级，不重试具有相同风险的模型请求。

## 5. 实施任务

| 编号 | 任务 | 主要文件 | 验收 |
| --- | --- | --- | --- |
| P1-001 | 建立可回答性分类器 | `backend/agent/guardrails.py` | 未来预测、因果、流失、收入问题全部命中 |
| P1-002 | 为限制类问题执行相关只读工具 | Agent 编排层 | 工具 trace 存在且回答不越界 |
| P1-003 | 定义严格合成响应 | 模型 Client/Adapter | 非 JSON、缺字段、错误 ID 均降级 |
| P1-004 | 数字与绝对结论校验 | Guardrail | 无证据数字和无维度结论被拒绝 |
| P1-005 | 增加 `limitations` | Schema、Service、前端 Client | 旧 `routing` 枚举完全兼容 |
| P1-006 | 扩展对抗评估集 | `evaluation/fixtures` | 不可回答和注入用例 100% |
| P1-007 | 建立 `pyproject.toml` | 项目根目录 | Ruff、pytest、coverage 配置集中 |
| P1-008 | 建立 GitHub Actions | `.github/workflows/ci.yml` | PR 自动执行完整门禁 |
| P1-009 | 补测试至 80% | `tests/` | 不排除核心文件、不降低阈值 |

## 6. 测试设计

### 单元测试

- 每类可回答性意图的正例、反例和边界表达。
- 中文同义词、否定句和混合问题。
- 结构化输出缺字段、错误类型、多余字段、未知 evidence ID。
- 数字格式：整数、小数、百分比、日期、版本号、排序序号。
- “最好”有评价维度和无评价维度两种情况。
- 评论正文内嵌提示注入、工具名、JSON 和伪系统指令。

### 集成测试

- Agent API 返回 `limitations`，旧请求仍可解析。
- DeepSeek 未配置、超时、HTTP 错误、非法 JSON、非法工具时规则降级。
- 模型返回虚假数字时 `routing=rule_fallback`。
- 工具调用 trace 的状态、参数、耗时和错误类型正确。

### 固定评估

```powershell
python -m evaluation.evaluate_agent --mode mock --fail-under
```

要求：46/46，所有聚合指标为 1.0；评估中不得发起真实外部模型请求。

## 7. CI 门禁

CI 至少包含四个独立 job：

1. `lint`：Ruff check 与 format check。
2. `test`：完整 pytest，覆盖率 `--cov-fail-under=80`。
3. `agent-eval`：Mock Agent `--fail-under`。
4. `package-smoke`：应用导入、OpenAPI 生成和依赖冲突检查。

建议命令：

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest --cov=. --cov-report=term-missing --cov-report=xml --cov-fail-under=80
python -m evaluation.evaluate_agent --mode mock --fail-under
```

覆盖率配置应排除虚拟环境、缓存、生成报告和纯脚本入口，但不能排除 `backend/services`、`backend/agent`、`backend/core`。

## 8. 可观测性要求

Agent 日志只记录：

- `request_id`、routing、intent、工具名、工具状态、耗时、限制数量、降级原因类型。
- 不记录 question 全文、评论正文、模型完整输入输出、密钥或工具证据全文。

建议指标：

- `agent_requests_total{routing,intent}`
- `agent_fallback_total{reason}`
- `agent_tool_duration_ms{tool}`
- `agent_guardrail_rejections_total{type}`

## 9. 退出条件

- 原测试全部通过且覆盖率不低于 80%。
- Mock Agent 46/46；不可回答、回答约束和提示注入通过率均为 100%。
- `AgentQueryResponse.limitations` 已在 API、Client 和界面中兼容展示。
- 任何模型错误都不会破坏确定性看板和规则 Agent。
- CI 是分支合并的必需检查，不能通过跳过测试合并。

## 10. 风险与回退

- 结构化输出导致模型兼容问题：回退到直接 Client + 规则降级，保留原始工具执行结果。
- 数字校验误伤日期或版本：完善 token 分类，不关闭数字校验。
- Guardrail 命中不准：优先增加可重复的评估案例，不把分类交给另一次 LLM 调用。
