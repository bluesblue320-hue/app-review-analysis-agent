# Agent Mock 评估门禁（46/46）

本目录保存 **Direct 与 LangChain 双 Adapter 的确定性 Mock 评估报告**，是普通 PR CI 的固定门禁，**不依赖真实模型、不调用 DeepSeek、不产生任何费用**。

## 如何复现

```bash
python -m evaluation.evaluate_agent --mode mock --adapter direct --fail-under
python -m evaluation.evaluate_agent --mode mock --adapter langchain --fail-under
```

## 结果

| Adapter | 通过/总数 | 报告 |
| --- | --- | --- |
| direct | 46 / 46 | `direct/summary.json`、`direct/report.md` |
| langchain | 46 / 46 | `langchain/summary.json`、`langchain/report.md` |

关键指标（两个 Adapter 均为 1.0）：

- `routing_accuracy`：路由准确率
- `required_tool_success_rate`：必需工具成功率
- `argument_accuracy`：参数提取准确率
- `illegal_tool_block_rate`：非法工具拦截率
- `fallback_success_rate`：降级成功率
- `grounded_number_check_rate`：数字可信度校验率
- `answer_constraint_pass_rate`：回答约束通过率

## 说明

- Mock 模式验证系统机制（路由、白名单、参数、降级、数字校验、双 Adapter 接线一致性），不评估模型文本质量。
- Live 模式结果随模型波动，作为发布/作品集人工交付物，不作为普通 PR CI 门禁。
- 完整问题集与数据集：`evaluation/agent_questions.json`、`evaluation/fixtures/evaluation_reviews.csv`。

报告生成时间：2026-08-07（阶段 7 存档）。
