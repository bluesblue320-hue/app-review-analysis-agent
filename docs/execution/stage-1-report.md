# 阶段 1 报告：Agent 可靠性、数据质量、CI 与安全基础（CP1）

> 运行 ID：`upgrade-20260806`
> 日期：2026-08-06
> 总控 Agent 一次启动执行，阶段 1/8

## 状态

- **阶段状态**：passed
- **检查点**：CP1 ✅
- **阶段开始 Commit**：`0eae65a`（CP0）
- **阶段结束 Commit**：见下方 Git 提交
- **允许进入阶段 2**：是

## 本阶段目标

1. 严格过滤 1～5 范围外的评分并记录删除原因。
2. 复核复杂问题先于简单意图的路由顺序。
3. 将 `evidence_call_ids` 加入统一 AgentAnswer 和 API 响应。
4. 按"纯不可回答"和"包含可回答子问题"执行锁定行为。
5. 完善数字、评价维度、绝对结论和提示注入校验。
6. 验收服务端 Insight Store 契约（跨数据集/范围/样本/过期不可复用）。
7. 验收完整范围高星低情绪总数与独立预览列表。
8. 引入 `pyproject.toml`、Ruff、pytest-cov，分离运行/开发依赖。
9. 建立基础 GitHub Actions。
10. 全项目覆盖率不低于阶段 0 基线（64%），达到 70% 并固定为门禁。
11. 接入 Bearer 鉴权、request ID、敏感日志过滤和 PII 脱敏。

## 实际修改文件

### 新增
| 文件 | 说明 |
| --- | --- |
| `backend/core/privacy.py` | PII 脱敏（手机/邮箱/身份证/银行卡 → 占位符） |
| `pyproject.toml` | 项目元数据、依赖分组、Ruff/pytest/coverage 配置 |
| `.github/workflows/ci.yml` | CI：lint、pytest、覆盖率 70、Mock Agent、应用导入 |
| `tests/conftest.py` | 兼容 Windows 超长环境变量（`patch.dict` 恢复崩溃） |
| `tests/test_dataset_ingestion.py` | 评分 1～5 严格过滤与删除原因统计 |
| `tests/test_privacy.py` | PII 脱敏单元测试 |
| `tests/test_middleware.py` | 请求 ID、鉴权 401、日志安全字段 |
| `tests/test_deepseek_client.py` | 模型客户端 synthesis/chat 错误路径与 evidence 校验 |

### 修改
| 文件 | 改动 |
| --- | --- |
| `backend/schemas/agent.py` | `AgentQueryResponse` 增加 `evidence_call_ids` |
| `backend/agent/tool_calling.py` | 结果携带 `evidence_call_ids`；伪造 ID 校验失败 → 降级；规则路径 `rule_1`；工具消息 PII 脱敏 |
| `backend/services/agent_service.py` | 传递 `evidence_call_ids` |
| `backend/schemas/dataset.py` | 上传响应增加 `removed_rows`、`invalid_rating_rows`、`invalid_reasons` |
| `backend/services/dataset_ingestion.py` | `IngestionStats` 统计与 `_build_ingestion_stats` |
| `backend/services/dataset_service.py` | `DatasetRecord` 增加统计字段 |
| `backend/services/sqlalchemy_dataset_store.py` | 适配新统计返回 |
| `backend/routers/datasets.py` | 上传/删除响应输出新字段 |
| `backend/main.py` | 接入 `request_context_middleware` 与 `application_lifespan` |
| `backend/agent/deepseek_client.py` | 构造模型消息前 PII 脱敏 |
| `tests/integration/test_api.py` | 上传统计断言、鉴权 401/200、删除接口、evidence_call_ids；修复 `test_upload_excludes...` 断言死代码 |
| 其余 | Ruff 格式化（import 排序、空白） |

## 主要实现

1. **评分严格过滤**：`parse_and_prepare_dataset` 现在返回 `IngestionStats`，统计 `invalid_rating`（不可解析或超出 1～5）与 `empty_content` 删除原因；上传响应包含 `removed_rows/invalid_rating_rows/invalid_reasons`。
2. **evidence_call_ids**：规则路径使用稳定 `rule_1`；tool_calling 路径对模型返回的 ID 做服务端二次校验（只能引用成功调用），伪造/失败 ID 使结果校验失败并进入规则降级；`AgentQueryResponse` 暴露该字段。
3. **PII 脱敏**：`redact_text` 在构造模型消息前统一替换手机号/邮箱/身份证/银行卡；工具证据递归脱敏后才序列化发送。
4. **鉴权与请求 ID**：`request_context_middleware` 接入主应用，Bearer 校验、`X-Request-ID`、JSON 安全日志（仅白名单字段）。
5. **工程化**：`pyproject.toml` 分离运行/开发依赖；Ruff 全绿；GitHub Actions 覆盖 lint、pytest、覆盖率 70 门禁、Mock Agent、应用导入。
6. **修复既有缺陷**：`test_upload_excludes_out_of_range_ratings_and_full_agent_uses_valid_rows` 的断言被 `_generate_insight` 定义截断成死代码，已移回原函数体，断言真实生效。

## 实际运行的命令与结果

| 命令 | 退出状态 | 结果 |
| --- | --- | --- |
| `python -m compileall -q backend frontend evaluation tests` | 0 | 通过 |
| `python -m pytest --collect-only -q` | 0 | 通过 |
| `python -m pytest` | 0 | **180 passed, 3 subtests passed**（阶段 0 为 145+3） |
| `python -m pytest --cov=. --cov-report=term-missing --cov-report=xml` | 0 | **覆盖率 70%**（2468 stmts，731 未覆盖） |
| `python -m ruff check .` | 0 | All checks passed |
| `python -m ruff format --check .` | 0 | 全部已格式化 |
| `python -m evaluation.evaluate_agent --mode mock --fail-under` | 0 | **46/46 通过，0 失败** |

## 测试结果

- 完整 pytest：180 passed + 3 subtests，0 failed。
- 新增测试覆盖：评分 0/6/10/`abc`/空值删除、1～5 保留；PII 脱敏（手机/邮箱/身份证/银行卡）；伪造 evidence ID 降级；失败工具 ID 不作为证据；鉴权缺失/错误令牌 401、正确令牌通过；删除接口；日志不含 token/PII/评论正文。

## 覆盖率

- **全项目：70%**（阶段 0 基线 64%，已达到本阶段 70% 目标并固定为门禁）。
- 核心模块覆盖率：`privacy.py` 100%、`middleware.py` 100%、`security.py` 100%、`tool_calling.py` 95%、`deepseek_client.py` 91%、`dataset_ingestion.py` 88%、`datasets.py` 100%、`schemas/agent.py` 97%。
- 阶段 1 新增/修改核心代码覆盖率全部 >= 80% 目标。

## Agent 评估结果

Mock 固定评估 **46/46**，`routing_accuracy`、`tool_exact_match_rate`、`illegal_tool_block_rate`、`grounded_number_check_rate`、`answer_constraint_pass_rate` 等全部 1.0。

## 已知限制

- `ai_analysis.py`（71%）、`app.py`（0%，Streamlit 单体）覆盖率偏低；Streamlit 组件化属于阶段 6 范围。
- SQLAlchemy/Redis 持久化仍为 0% 覆盖，属阶段 3～4 范围，按主文档未在本阶段补测。
- 本机完整覆盖率运行耗时约 4 分钟；偶发 pandas 原生访问冲突（Windows）重跑即恢复，已登记。
- 阶段 1 未执行任何 Live 模型调用（无 API Key 需求，Mock 为确定性门禁）。

## 门禁是否通过

**通过** ✅

- [x] 完整 pytest 通过（180 + 3）
- [x] 全项目覆盖率 70%，不低于阶段 0 基线 64%
- [x] 可靠性/安全/API 核心代码覆盖率 >= 80%
- [x] Mock Agent 46/46
- [x] Ruff lint + format 通过
- [x] 鉴权缺失/错误令牌 401
- [x] 日志不包含 token、评论原文或 PII
- [x] 伪造 evidence ID 触发降级

## Git 提交

- CP1 阶段提交：见下方（`fix: complete agent reliability data validation and security baseline`）

## 下一阶段输入条件

- 阶段 2 可开始。依赖：CP1 通过、AgentAnswer/Guardrail/PII/鉴权/CI 稳定、覆盖率 70% 门禁。
- 阶段 2 目标：Direct/LangChain 双 Adapter（共享 Orchestrator、单次规划最多选择 3 个只读分析工具）、双 Adapter Mock 46/46、覆盖率 75%、首次 Live 对比。
