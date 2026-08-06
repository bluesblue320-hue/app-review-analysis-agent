# 阶段 0 报告：工作树恢复（CP0）

> 运行 ID：`upgrade-20260806`
> 日期：2026-08-06
> 总控 Agent 一次启动执行，阶段 0/8

## 状态

- **阶段状态**：passed
- **检查点**：CP0 ✅
- **阶段开始 Commit**：`3ee5dba`（main 原始 HEAD）
- **阶段结束 Commit**：见下方 Git 提交
- **允许进入阶段 1**：是

## 本阶段目标

1. 创建可恢复的 Git 安全快照（rescue 分支 + WIP 保护提交 + 仓库外备份）。
2. 修复 Analytics Schema 与 Analytics Service 缩进错误。
3. 修复 SQLAlchemy Insight Store 方法签名与 `cleanup_expired` 契约。
4. 检查中间件、生命周期和安全文件可导入。
5. 核对根目录临时 `.patch` 内容已落入目标源文件，脚手架不进入正式提交。
6. 恢复 compileall、pytest 收集、完整 pytest 与 Mock Agent 评估。
7. 记录全项目覆盖率基线（阶段 0 不设置阈值）。

## 实际修改文件

| 文件 | 改动 |
| --- | --- |
| `backend/schemas/analytics.py` | 修复 `RatingSentimentMismatchItem`/`ReviewSearchResponse` 类定义缩进错位 |
| `backend/services/analytics_service.py` | 修复 `build_summary` 中误置 `@staticmethod` 导致的缓存写入缩进错误；`_renamed_records` 补充 `self` 参数 |
| `backend/services/sqlalchemy_insight_store.py` | `delete_dataset` 去除错误 `@staticmethod`；`_record` 补 `self`；`resolve` 改为与内存实现一致的关键字签名；新增 `cleanup_expired` |
| `.gitignore` | 忽略临时 `.*.patch`、`.coverage.*`、`coverage.xml` |
| `.coveragerc` | 新增覆盖率配置：排除 `.venv`、tests、evaluation 等，保证本地基线口径与 CI 一致 |
| `docs/execution/current-state.json` | 运行状态文件（初始化） |
| 根目录 15 个临时 `.patch` | 已核对内容全部落盘，从工作树与索引移除（脚手架不进正式提交） |

## 安全快照（任务 1～5）

1. **快照前记录**：`git status --short`、`git diff --binary`（86 KB）、`git diff --cached --binary`（空，无暂存改动）、`git diff --stat`（29 文件，+1157/-198）、untracked 清单（41 个文件）已保存至仓库外 `C:\Users\30306\stage0-snapshot-20260806\`。
2. **rescue 分支**：`rescue/upgrade-worktree-20260806` 从 `main` 创建。
3. **WIP 保护提交**：`03d4bf1`（70 文件，+6619/-198），包含全部 tracked 修改与 untracked 文件。
4. **还原校验**：
   - untracked 备份 41/41 sha256 与工作树一致；
   - WIP 提交 blob 与备份在 LF 规范化后 41/41 一致（4 处差异均为 `core.autocrlf=true` 的 CRLF 转换，已确认）；
   - 临时 worktree 检出 `03d4bf1` 成功（106 文件）。
5. 未使用任何破坏性 Git 命令（无 `reset --hard`、`clean -fd`、`checkout -- .`）。

## 主要实现

- **Analytics Schema**：`RatingSentimentMismatchItem` 补齐字段（rating/sentiment/category/risk_label/content），`ReviewSearchResponse` 独立成类。
- **Analytics Service**：缓存写入与返回值恢复正常缩进；`_renamed_records` 实例方法补 `self`，8 个集成测试恢复。
- **SQLAlchemy Insight Store**：方法签名与内存实现对齐；新增 `cleanup_expired()`（按 `expires_at <= now` 批量删除并返回数量），满足生命周期契约。

## 实际运行的命令与结果

| 命令 | 退出状态 | 结果 |
| --- | --- | --- |
| `python -m compileall -q backend frontend evaluation tests` | 0 | 通过（修复前 2 个 IndentationError） |
| `python -m pytest --collect-only -q` | 0 | **145 tests collected**（修复前 119 + 1 error） |
| `python -m pytest -v --cov=. --cov-report=term-missing --cov-report=xml` | 0 | **145 passed, 3 subtests passed**；覆盖率 **64%**（2379 stmts），coverage.xml 已生成 |
| `python -m evaluation.evaluate_agent --mode mock --fail-under` | 0 | **46/46 通过，0 失败**，全部聚合指标 1.0；报告 `evaluation/reports/20260806-162311/` |
| `git diff --check` | 0 | 无空白错误 |
| 模块导入检查（security/middleware/lifecycle/cache/insight_store/sqlalchemy stores/database/main） | 0 | 全部导入成功 |

## 测试结果

- 完整 pytest：145 passed + 3 subtests passed，0 failed。
- 收集：145 tests collected（与历史基线一致）。
- Mock Agent：46/46，`routing_accuracy`、`tool_exact_match_rate`、`tool_precision`、`tool_recall`、`tool_f1`、`required_tool_success_rate`、`any_tool_success_rate`、`argument_accuracy`、`illegal_tool_block_rate`、`fallback_success_rate`、`grounded_number_check_rate`、`answer_constraint_pass_rate` 全部 1.0。

## 覆盖率

- **全项目基线：64%**（2379 语句，850 未覆盖）。
- 阶段 0 不设置覆盖率失败阈值；该基线将成为阶段 1 的不可低于门禁。
- 低覆盖模块：`sqlalchemy_dataset_store.py`（0%）、`sqlalchemy_insight_store.py`（0%）、`database.py`（0%）、`middleware.py`（0%）、`security.py`（0%）、`lifecycle.py`（0%）、`cache_service.py`（50%）——均为尚未接线的持久化/安全基础文件，将在阶段 1～4 补测。

## Agent 评估结果

Mock 固定评估 46/46 通过，与主文档要求一致（`candidate-guardrails` 现已被验证为可收集、可回归的稳定基线）。

## 已知限制

- 运行完整覆盖率约需 4 分钟（`--cov=.` 追踪开销），非功能问题。
- 本机偶发 pandas/numpy 原生访问冲突（Windows access violation）出现在完整套件某次运行中，重跑即恢复；已在阶段报告中登记，后续阶段持续观察。
- SQLAlchemy/Redis 持久化文件已可导入但未接线（`STORAGE_BACKEND=memory` 默认），按主文档属阶段 3～4 范围。

## 门禁是否通过

**通过** ✅

- [x] rescue 分支 + WIP 提交 + 外部备份存在且已验证可还原
- [x] compileall 通过
- [x] pytest --collect-only 完整收集 145 个测试
- [x] 无语法、导入、缩进、Pydantic Schema 或循环依赖错误
- [x] Mock Agent 固定评估 46/46
- [x] 临时 .patch 有效内容已落入目标源文件，脚手架不进入正式提交
- [x] 覆盖率基线已记录（64%，不设阈值）

## Git 提交

- WIP 保护提交（恢复快照，不计入正式检查点）：`03d4bf1` `wip: preserve current upgrade worktree`
- CP0 阶段提交：见下方（`fix: stabilize current upgrade worktree and restore test collection`）

## 下一阶段输入条件

- 阶段 1 可开始。依赖：CP0 通过、无收集/导入错误、Mock 46/46、覆盖率基线 64% 已记录。
- 阶段 1 目标：评分 1～5 严格过滤、`evidence_call_ids`、不可回答/绝对结论防护、pyproject+Ruff+pytest-cov、GitHub Actions 基础、Bearer 鉴权/request ID/PII 脱敏，覆盖率 >= 70%。
