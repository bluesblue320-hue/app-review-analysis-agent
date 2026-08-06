# 阶段 2 报告：Direct/LangChain 双 Agent Adapter（CP2）

> 运行 ID：`upgrade-20260806`
> 日期：2026-08-06
> 总控 Agent 一次启动执行，阶段 2/8

## 状态

- **阶段状态**：passed（Mock/代码/覆盖率门禁全部通过；Live 对比因外部依赖未执行，如实登记，不视为通过）
- **检查点**：CP2 ✅（代码门禁部分）
- **阶段开始 Commit**：`e62ffab`（CP1）
- **允许进入阶段 3**：是

## 本阶段目标

1. 新增 `AgentModelAdapter` 统一接口，Direct 与 LangChain 双实现，共享同一 Orchestrator（可回答性判断、规则快速路由、最多三次有界工具循环、工具白名单、Pydantic 参数校验、工具证据收集、PII 脱敏、结构化回答校验、数字与绝对结论校验、规则降级、Tool Trace）。
2. LangChain Adapter 使用 `ChatDeepSeek.bind_tools`，由共享 Orchestrator 控制有界循环（不采用 LangChain Agent Executor）。
3. 配置 `AGENT_ADAPTER=direct|langchain` 运行时切换。
4. 双 Adapter Mock 固定 46/46（确定性回归门禁）。
5. 全项目覆盖率从 70% 提升到 75% 并固定为门禁。
6. 完成首次 Live 对比（Direct vs LangChain）作为人工验收交付物——因当前环境无 `DEEPSEEK_API_KEY` 且网络受限，**未执行**，如实登记为外部依赖阻塞项。

## 实际修改文件

### 新增
| 文件 | 说明 |
| --- | --- |
| `backend/agent/adapters/__init__.py` | `AgentPlanRequest`/`AgentPlan`/`SynthesisRequest`/`AgentAnswer` Pydantic 契约；`AgentModelAdapter` Protocol；`build_adapter` 工厂 |
| `backend/agent/adapters/direct_adapter.py` | Direct 原生 DeepSeek Adapter（薄包装 `DeepSeekToolClient`，行为不变） |
| `backend/agent/adapters/langchain_adapter.py` | LangChain `ChatDeepSeek.bind_tools` Adapter；`LangChainUnavailableError`/`LangChainAdapterError`；工具调用规范化、JSON 结构化输出解析 |
| `tests/test_adapters.py` | 双 Adapter 契约测试（单工具/多工具/超三次/非法工具/非法参数/缺 Key/超时/非法 JSON/无工具/虚假数字/无证据绝对结论/结构化输出失败/工具失败），parametrize direct+langchain |
| `tests/test_langchain_adapter.py` | LangChain 纯函数与错误路径单元测试（plan/synthesize/解析/懒加载） |
| `tests/test_ai_analysis_extended.py` | `ai_analysis.py` 错误路径与辅助函数覆盖（env 加载/JSON 提取/缺列/空数据/sentiment/请求失败/结构异常） |
| `tests/test_cache_service.py` | `NullCache`/`RedisCache`/缓存 key 覆盖 |
| `tests/test_nlp_analysis_extended.py` | `nlp_analysis.py` 离线 CLI 覆盖（词云渲染/main 成功与失败路径/CSV 错误） |

### 修改
| 文件 | 改动 |
| --- | --- |
| `backend/agent/tool_calling.py` | `ControlledToolCallingAgent` 改为接受统一 Adapter；`_AdapterErrors` 归一化两种 Adapter 的可恢复错误；`_normalize_synthesis` 支持 `AgentAnswer` |
| `backend/core/config.py` | `agent_adapter: str = "direct"` 配置项与校验（`AGENT_ADAPTER` env） |
| `pyproject.toml` | `langchain` 可选依赖锁定兼容版本（langchain-core 0.3.60 避免 uuid_utils 原生扩展被系统策略阻止） |
| `evaluation/evaluate_agent.py` | `--adapter` 参数；双 Adapter Mock 注入；Live 配置校验抽离 |

## 主要实现

1. **统一 Adapter 契约**：`AgentModelAdapter` 只负责 `plan_tools`（一次模型往返规划工具调用）与 `synthesize`（一次模型往返生成结构化回答）；业务分析全部由共享 `ToolExecutor` 在 Orchestrator 控制下执行。
2. **Direct Adapter**：薄包装既有 `DeepSeekToolClient`，模型行为零变化，默认 `AGENT_ADAPTER=direct` 保持线上行为完全一致，可回退。
3. **LangChain Adapter**：`ChatDeepSeek`（deepseek-chat、temperature 0.1、json_object 输出），`bind_tools` + 单轮规划；工具调用规范化到共享 dict 结构；JSON 结构化输出由服务端统一二次校验（数字可信度、绝对结论、证据 ID）。
4. **共享 Orchestrator**：工具白名单、最多 3 次有界循环、Pydantic 参数校验、PII 脱敏、规则降级全部保留在原 `ControlledToolCallingAgent`，仅替换模型交互层。
5. **环境适配**：系统"应用程序控制策略"阻止 `uuid_utils`（langchain-core 0.3.60 及以上版本依赖的 Rust 扩展）加载；将 langchain 依赖锁定到 0.3.60 组合（langsmith 0.1.147），规避该问题并在 pyproject 固定。

## 实际运行的命令与结果

| 命令 | 退出状态 | 结果 |
| --- | --- | --- |
| `python -m compileall -q backend frontend evaluation tests` | 0 | 通过 |
| `python -m pytest` | 0 | **267 passed, 3 subtests passed**（阶段 1 为 180+3） |
| `python -m pytest --cov=. --cov-report=term` | 0 | **覆盖率 76%**（2652 stmts，649 未覆盖） |
| `coverage xml` | 0 | coverage.xml line-rate **0.7553** |
| `python -m evaluation.evaluate_agent --mode mock --adapter direct --fail-under` | 0 | **46/46 通过，0 失败** |
| `python -m evaluation.evaluate_agent --mode mock --adapter langchain --fail-under` | 0 | **46/46 通过，0 失败** |
| `python -m pytest tests/test_adapters.py` | 0 | 26 passed（direct+langchain 各 13 场景） |
| `python -m pytest tests/test_langchain_adapter.py` | 0 | 18 passed |
| `python -m ruff check .` | 0 | All checks passed（见下） |
| Live 对比（`--mode live --adapter direct` / `langchain`） | **not_run** | 无 `DEEPSEEK_API_KEY`，外部依赖阻塞 |

## 测试结果

- 完整 pytest：267 passed + 3 subtests，0 failed。
- 新增 Adapter 契约测试：单工具、多工具、超 3 次截断、非法工具拒绝、非法参数 Pydantic 失败、缺 Key 降级、超时降级、无工具降级、非法 JSON 合成降级、虚假数字降级、无证据绝对结论降级、结构化输出失败降级、工具失败降级——两个 Adapter 全通过。
- LangChain 单元测试：工具调用规范化、JSON 解析、非列表字段拒绝、空回答拒绝、懒加载缺 Key/错 Provider 报错。

## 覆盖率

- **全项目：75.53%（coverage.xml line-rate 0.7553）**，高于本阶段 75% 门禁，高于阶段 1 的 70%。
- 关键模块：`adapters/__init__.py` 87%、`direct_adapter.py` 90%、`langchain_adapter.py` 97%、`tool_calling.py` 88%、`nlp_analysis.py` 95%、`cache_service.py` 100%、`ai_analysis.py` 71%（维持）。
- 未覆盖主要集中于 `app.py`（Streamlit 单体 0%）、SQLAlchemy store（阶段 3/4 范围）、`spider.py`。

## Agent 评估结果

- **Direct Mock 46/46**、**LangChain Mock 46/46**：`routing_accuracy`、`illegal_tool_block_rate`、`fallback_success_rate`、`grounded_number_check_rate`、`answer_constraint_pass_rate` 全部 1.0。
- 双 Adapter 通过同一固定问题集与同一确定性 Mock，验证 Orchestrator 与两种模型交互层的接线一致性。

## Live 对比（未执行，如实登记）

- 主文档要求首次 Live 对比作为阶段 2 人工验收交付物；当前环境：
  - `DEEPSEEK_API_KEY` 未配置（环境变量与 `.env` 均无）；
  - 网络连接器全部 disconnected，无法访问 `api.deepseek.com`。
- 因此 `--mode live` 全部标记为 **not_run**，未生成 6 次运行目录与 comparison.md。
- 处理原则：Mock 46/46（PR CI 门禁）不受影响；Live 对比为人工交付物，不加入普通 PR CI；按主文档"DeepSeek 未配置且当前阶段只运行 Mock 测试"不作为硬阻塞，记录后继续。
- 恢复路径：配置 `DEEPSEEK_API_KEY` 且网络可用后，在阶段 7 按冻结案例目录规范补齐 Live 对比（脚本已就绪：`evaluation/evaluate_agent.py --mode live --adapter direct|langchain`）。

## 门禁是否通过

**通过** ✅（Mock/代码/覆盖率门禁）

- [x] 完整 pytest 通过（267 + 3）
- [x] 全项目覆盖率 75.53% >= 75% 门禁
- [x] Direct Mock 46/46
- [x] LangChain Mock 46/46
- [x] 双 Adapter 共享 Orchestrator、最多 3 次有界循环
- [x] LangChain 不使用 Agent Executor（bind_tools + 自管有界循环）
- [x] `AGENT_ADAPTER` 运行时切换
- [x] LangChain 结构化输出解析后经统一服务端证据/数字/结论校验
- [x] 新增 Adapter 代码覆盖率 >= 80%（direct 90%、langchain 97%）

**未执行（外部依赖，不视为通过）**：
- [ ] Live 对比 6 次运行目录与 comparison.md（缺 API Key + 网络受限）

## Git 提交

- CP2 阶段提交：见下方（阶段 2 提交消息）

## 下一阶段输入条件

- 阶段 3 可开始。依赖：CP2 通过、双 Adapter Mock 46/46、覆盖率 75% 门禁。
- 阶段 3 目标：PostgreSQL 生产存储（SQLAlchemy Dataset/Insight Store 加锁并发与连接池）、Redis 缓存接入（命中率与失效）、阶段 2 已知限制项修复。
