# 阶段 0：基线冻结与架构决策

> 周期：2–3 个工作日  
> 目标：把当前未提交工作树整理为可测试、可继续演进的基线，消除“代码存在但未集成”的不确定性。

## 1. 进入条件

- 以当前工作树为唯一实现基线，不执行 `git reset --hard` 或覆盖用户改动。
- 保存当前 `git status`、`git diff --stat` 和测试结果。
- 明确本阶段只做集成修复、基线测试和架构决策，不扩大业务功能。

## 2. 当前已知问题

仓库检查发现以下事项必须在进入阶段 1 前处理：

1. `backend/schemas/analytics.py` 中评论分页响应与评分/情绪不一致项的类定义需要重新整理，确保模块可导入且响应模型字段正确。
2. `SqlAlchemyInsightStore.delete_dataset` 的方法声明不正确，并缺少生命周期清理所需的 `cleanup_expired`。
3. `backend/core/middleware.py`、`security.py`、`lifecycle.py` 已创建，但尚未接入 `backend/main.py`。
4. SQLAlchemy、Alembic、Redis、Ruff、pytest-cov 等依赖尚未正式加入运行/开发依赖。
5. 数据库当前使用 `create_all`，没有迁移版本，不满足生产可升级要求。
6. 全量 pytest 尚未在当前所有改动合并后重新通过。
7. 根目录存在多个临时 `.patch` 文件；确认补丁内容已经体现在目标文件后应移除。

## 3. 架构决策记录

### ADR-001：生产数据库

- 决策：生产使用 PostgreSQL，开发和单元测试允许 SQLite 或内存 Repository。
- 原因：项目已经计划引入 Redis、异步任务和新前端，继续把 SQLite 作为长期生产主库会很快遇到连接、并发和迁移限制。
- 兼容：保留 SQLite WAL 配置，支持单机演示和轻量部署；数据库模型和 Alembic 迁移必须同时兼容 PostgreSQL 与 SQLite。

### ADR-002：Redis 定位

- 决策：Redis 只用于摘要缓存、短时锁、幂等键和异步任务状态。
- 禁止：不在 Redis 中保存评论、洞察或任务结果的唯一副本；不使用 `KEYS` 扫描生产 keyspace。
- 降级：Redis 不可用时，读请求直接计算；写请求仍以 PostgreSQL 事务为准。

### ADR-003：LangChain 定位

- 决策：通过内部 `AgentModelAdapter` 接口引入 LangChain，实现结构化输出和受控工具调用。
- 禁止：不使用任意代码执行工具、不允许模型生成 SQL、不让模型决定删除/更新数据。
- 回退：保留现有直接 DeepSeek 客户端和规则 Agent，使用特性开关逐步切换。

### ADR-004：前端路径

- 决策：第 6 周前完成 Streamlit 模块化以保障 Gate A；之后以 Next.js + TypeScript 渐进替换，完成 Gate B。
- 原则：两个前端共用同一 OpenAPI 契约，不复制指标逻辑，不直接访问数据库。

### ADR-005：异步任务边界

- 决策：预计超过 10 秒、需要重试或可能调用外部模型的任务可进入 Celery；普通摘要、分页和规则 Agent 保持同步。
- 事实来源：任务元数据和最终结果写 PostgreSQL，Redis 仅做 broker/状态加速。

## 4. 任务拆解

| 编号 | 任务 | 产出 | 验证 |
| --- | --- | --- | --- |
| P0-001 | 保存工作树清单和测试基线 | 基线记录 | 清单包含修改、未跟踪和临时文件 |
| P0-002 | 修复 Schema 可导入性 | 正确的 Pydantic 类 | `python -m pytest tests/integration/test_api.py` 可收集 |
| P0-003 | 修复 Insight Store 接口 | `delete_dataset`、`cleanup_expired` | 内存与 SQLAlchemy 实现通过同一契约测试 |
| P0-004 | 接入或暂时隔离未完成中间件 | 应用能启动 | `/health` 正常，错误处理不回归 |
| P0-005 | 整理依赖边界 | 运行/开发依赖草案 | 全新虚拟环境可安装 |
| P0-006 | 清理临时补丁文件 | 干净的交付文件列表 | `git status` 不再显示 `.patch` 脚手架 |
| P0-007 | 跑全量基线 | pytest、Agent 评估报告 | 失败有明确归属，不留收集错误 |

## 5. 建议目录目标

```text
backend/
  agent/          # 工具、适配器、Guardrail、编排
  core/           # 配置、安全、中间件、日志、生命周期
  repositories/   # Repository Protocol 与实现
  storage/        # SQLAlchemy Models、Session、迁移集成
  services/       # 用例服务，不直接依赖具体数据库
  routers/        # HTTP 层
frontend/
  streamlit/      # Gate A 模块化页面和组件
web/              # Gate B Next.js 应用
tests/
  unit/
  integration/
  e2e/
  performance/
alembic/
docs/improvement-plan/
```

阶段 0 不要求立即完成目录迁移，但新代码应按此边界放置，避免继续增加根目录单体模块。

## 6. 基线验证命令

```powershell
python -m compileall -q backend frontend evaluation tests
python -m pytest -q
python -m evaluation.evaluate_agent --mode mock --fail-under
```

完成 `pyproject.toml` 后补充：

```powershell
python -m ruff check .
python -m ruff format --check .
```

## 7. 退出条件

- Python 模块均可收集和导入，没有 Schema 语法或循环导入错误。
- 全量测试结果已记录；若有失败，必须形成具体缺陷清单并分配到阶段 1，不能以“环境问题”笼统跳过。
- 临时补丁文件已核对并移除。
- 五项 ADR 已确认，后续实现不再反复更换数据库、缓存、Agent 和前端边界。
- 当前工作树改动按功能分组，具备后续小批次提交的条件。

## 8. 风险与回退

- 若 PostgreSQL 依赖阻塞本地测试，测试仍使用内存 Repository，集成测试使用临时 SQLite；不能因此删除生产 PostgreSQL 设计。
- 若未完成的安全中间件导致应用无法启动，先通过特性开关隔离并保留测试，阶段 2 再正式启用。
- 若当前改动无法一次整理，按“Agent Guardrail → API Schema → Repository → Middleware”顺序拆分，任何一步都保持测试可运行。
