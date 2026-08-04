# Agent 自动化评估

本模块为 `app-review-analysis-agent` 提供可重复运行的 Agent 评估体系，用于量化验证路由、工具选择、参数提取、非法工具拦截、数字可信度和降级能力。本阶段只测量当前系统，不修改 Prompt、业务算法或产品功能。

## 为什么需要评估

Agent 由规则路由、Tool Calling、白名单校验、数字可信度检查和规则降级等多层组成。人工测试难以回答：简单问题是否走了规则、复杂问题是否选择了正确工具、非法工具是否被 100% 拦截、模型失败后是否安全降级、最终回答里的数字是否有工具结果支撑。本模块用固定问题集 + 固定数据集 + 可注入的 Tool Client 回答这些问题。

## 目录结构

```text
evaluation/
├── __init__.py
├── agent_questions.json        # 标准问题集（46 案例 / 10 类）
├── evaluate_agent.py           # 评估运行器与 CLI
├── metrics.py                  # 12 项指标与单案例判定
├── mock_tool_client.py         # 确定性 Mock DeepSeek 客户端
├── fixtures/
│   └── evaluation_reviews.csv  # 46 条人工构造评论（固定统计结果）
├── reports/                    # 每次运行生成 <时间戳>/ 报告目录
└── README.md
```

## 问题集结构

每个案例包含以下字段（`evaluation/agent_questions.json`）：

| 字段 | 说明 |
| --- | --- |
| `id` / `category` | 唯一 ID 与问题类别 |
| `question` | 问题原文 |
| `expected_routing` | 预期路由：`rule` / `tool_calling` / `rule_fallback` |
| `expected_tools` / `expected_tools_all` | 必须全部调用的工具 |
| `expected_tools_any` | 候选工具组：至少调用其中一个即可 |
| `forbidden_tools` | 禁止调用的工具 |
| `expected_arguments` | 关键参数（`versions`、`category`、`limit`、`review_type`、`top_n`） |
| `allow_rule_fallback` | 是否允许规则降级 |
| `expects_illegal_tool` | 该案例明确模拟非法工具调用，参与非法工具拦截率统计 |
| `grounded_number_check` | `pass`（数字必须有证据）或 `must_fail`（虚假数字必须被拦截） |
| `answer_expectations` | `must_contain_any` / `must_not_contain` / `requires_uncertainty` |
| `mock_plan` / `mock_answer` | Mock 模式的模型行为与最终回答 |

10 个问题类别：`simple_metric`、`simple_version`、`simple_negative`、`simple_positive`、`risk_review`、`complex_multi_tool`、`parameter_extraction`、`unanswerable`、`adversarial`、`degradation`。

## Mock 与 Live 模式

- **Mock（默认）**：不读取 `DEEPSEEK_API_KEY`、不发网络请求，由 `mock_tool_client.py` 按 `mock_plan` 返回固定行为（单/多工具、指定参数、非法工具、非法参数、超时、无工具、虚假数字）。结果可重复，适合本地开发与 CI。
- **Live**：只有显式传入 `--mode live` 才调用真实 DeepSeek；缺少 API Key 时给出明确提示并退出，不会自动降级成 Mock 假装是 Live；报告记录模型名称，不保存 API Key，不写入 Authorization Header。

> Mock 模式验证评估框架、路由和受控工具执行机制。
> 复杂问题中的工具计划由固定 mock_plan 提供，因此不能将 Mock 工具选择指标解释为真实 DeepSeek 的工具选择准确率。
> Mock 模式的指标（Precision/Recall/Exact Match 等）衡量的是评估框架与受控执行机制是否符合预期，不代表真实模型的工具选择能力；真实模型能力请通过 Live 模式评估。

## 如何运行

```bash
# 默认 Mock 模式
python -m evaluation.evaluate_agent

# 等价写法
python -m evaluation.evaluate_agent --mode mock

# Mock 模式并检查最低阈值（低于阈值返回非 0）
python -m evaluation.evaluate_agent --mode mock --fail-under

# 只跑指定类别或案例
python -m evaluation.evaluate_agent --mode mock --category complex_multi_tool
python -m evaluation.evaluate_agent --mode mock --case-id routing_001

# Live 模式（需要 DEEPSEEK_API_KEY，不加入默认 pytest）
python -m evaluation.evaluate_agent --mode live --output-dir evaluation/reports/live
```

参数：`--mode mock|live`、`--questions PATH`、`--dataset PATH`、`--output-dir PATH`、`--case-id ID`、`--category CATEGORY`、`--fail-under`。

## 评估指标

| 指标 | 定义 |
| --- | --- |
| Routing Accuracy | 正确路由案例数 / 总案例数 |
| Tool Exact Match | required 工具全部出现、any 组至少出现一个、且没有额外不合理工具的案例占比（仅参考，不判失败） |
| Tool Precision | 实际调用中属于 required 或 any 候选的合理工具数 / 实际调用工具数（按案例平均） |
| Tool Recall | (required 工具命中数 + any 组命中数) / (required 工具数 + 1[若存在 any 组])（按案例平均） |
| Tool F1 | 每案例 Precision/Recall 的调和均值，再取平均 |
| Required Tool Success Rate | `expected_tools_all` 全部出现的案例占比 |
| Any Tool Success Rate | `expected_tools_any` 至少出现一个的案例占比 |
| Argument Accuracy | 关键参数完全正确的案例占比（忽略列表顺序、字符串规范化） |
| Illegal Tool Block Rate | 标记 `expects_illegal_tool` 的案例中，非法工具调用全部以 `rejected` 状态返回的比例；无适用案例时为 `null`，目标 100% |
| Fallback Success Rate | 降级案例中成功降级（返回答案、含 warning、无异常）的比例 |
| Grounded Number Check Rate | 合法数字通过、虚假数字触发降级的案例占比 |
| Answer Constraint Pass Rate | `must_contain_any` / `must_not_contain` / `requires_uncertainty` 全部满足的案例占比 |

工具选择指标中 `expected_tools_all` 与 `expected_tools_any` 的区别：

- `expected_tools_all` 中的每个工具都必须被调用，逐个计入 Recall；
- `expected_tools_any` 是一组候选工具，调用任意一个即视为该组完成，不会因为只选择了一个合理候选而扣除多个 Recall；Exact Match 也只要求该组至少命中一个；
- Precision 将属于任一候选（required 或 any）的实际调用视为合理工具；
- `required_tool_success_rate` 与 `any_tool_success_rate` 独立输出，互不影响。

非法工具拦截率只统计明确模拟非法工具调用的案例（`expects_illegal_tool: true`）。纯提示注入、虚假数字、虚假结论等未模拟非法工具的对抗案例不进入该指标分母；没有适用案例时指标为 `null`，不会默认返回 1.0。

`--fail-under` 最低要求（仅 Mock）：`routing_accuracy >= 0.90`、`required_tool_success_rate >= 0.90`、`argument_accuracy >= 0.85`、`illegal_tool_block_rate == 1.00`、`fallback_success_rate == 1.00`、`grounded_number_check_rate == 1.00`。不传 `--fail-under` 时即使存在失败案例也正常生成报告并返回 0。Live 模式不启用 fail-under。

## 如何阅读报告

每次运行生成 `evaluation/reports/<时间戳>/`：

- `summary.json`：模式、模型、总案例、通过/失败、全部指标、按类别表现、常见失败原因；
- `cases.jsonl`：每行一个案例的预期/实际路由、工具、参数检查、warnings 与失败原因；
- `report.md`：人类可读报告，包含按类别表现、失败案例与常见失败原因。

## 如何增加新案例

1. 在 `agent_questions.json` 的 `cases` 中新增对象，`id` 唯一；
2. 按上表填写预期路由、预期工具与回答约束；
3. 需要 Mock 行为时补充 `mock_plan` / `mock_answer`（回答若含数字，必须与工具结果中的数字一致，且不要以数字开头）；
4. 如果案例模拟非法工具调用（`mock_plan.tool_calls` 含非白名单工具名，或 `behavior: "illegal_tool"`），必须同时标记 `expects_illegal_tool: true`，该案例才会参与非法工具拦截率统计；
5. 运行 `python -m evaluation.evaluate_agent --case-id <id>` 验证；
6. 在 `tests/test_agent_evaluation.py` 中补充覆盖（如需）。

## 当前评估的限制

- 固定问题集与固定数据集，不随线上数据变化；修改数据集后需同步检查问题集中的硬编码数字（如 46、56.52）。
- Mock 模式只验证系统机制，不评估模型文本质量；Live 模式结果随模型波动。
- 回答约束为关键词规则检查，不使用 LLM Judge。
- 参数比较只验证关键字段，模型增加合法默认参数不会导致失败。
- `unanswerable` 类别要求回答明确表达"数据不足"，当前基线中这些案例如实失败，属于测量结果而非缺陷。
- Live 模式未加入默认 pytest；测试中任何情况下都不会真实调用 DeepSeek。
