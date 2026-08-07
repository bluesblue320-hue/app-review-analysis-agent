# Live 对比报告（Direct vs LangChain）

> 状态：**未执行（外部依赖阻塞）**
> 更新日期：2026-08-07

## 阻塞原因

Live 对比需要 `DEEPSEEK_API_KEY` 且网络可访问 `api.deepseek.com`；当前开发环境两者均不可用（环境变量未配置、网络连接器全部断开）。Mock 46/46 门禁不受影响（见 `../mock-gate/`）。

## 复现命令（API Key 与网络可用后执行）

```bash
# Direct：运行 3 次
python -m evaluation.evaluate_agent --mode live --adapter direct \
  --output-dir evaluation/reports/live-comparison/direct/run1
python -m evaluation.evaluate_agent --mode live --adapter direct \
  --output-dir evaluation/reports/live-comparison/direct/run2
python -m evaluation.evaluate_agent --mode live --adapter direct \
  --output-dir evaluation/reports/live-comparison/direct/run3

# LangChain：运行 3 次
python -m evaluation.evaluate_agent --mode live --adapter langchain \
  --output-dir evaluation/reports/live-comparison/langchain/run1
python -m evaluation.evaluate_agent --mode live --adapter langchain \
  --output-dir evaluation/reports/live-comparison/langchain/run2
python -m evaluation.evaluate_agent --mode live --adapter langchain \
  --output-dir evaluation/reports/live-comparison/langchain/run3
```

## 完成后需更新的本文件内容

- [ ] 六个运行目录的 `summary.json` 汇总（routing_accuracy、tool_f1、argument_accuracy、降级率、失败分类）。
- [ ] 三次运行一致性说明（同案例跨运行是否稳定）。
- [ ] 失败案例分析（哪些案例依赖模型文本质量、哪些是机制限制）。
- [ ] 不提交未经脱敏的原始模型内容。

## 约定指标

与 Mock 门禁一致：routing_accuracy、tool_exact_match_rate、tool_precision/recall/f1、required_tool_success_rate、any_tool_success_rate、argument_accuracy、illegal_tool_block_rate、fallback_success_rate、grounded_number_check_rate、answer_constraint_pass_rate。

## 原则

- Live 结果不替代双 Adapter Mock 46/46（Mock 是确定性 CI 门禁）。
- 简历/README 中任何 Live、延迟、稳定性描述必须能追溯到本目录报告；未测量则删除该数字。
