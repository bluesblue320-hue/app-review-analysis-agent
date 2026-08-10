# 简历描述（基于仓库内可追溯的测试与报告）

> 原则：只引用当前代码、最新 GitHub Actions 或明确标注为历史阶段的报告；Live 模型、备份恢复或性能数据未实际复测时，不把它们写成当前验证结果。

## 描述 1（AI Agent / 全栈工程）

> 独立设计并落地 App Store 中文评论分析 Agent，采用 React 19 + TypeScript + FastAPI 实现前后端分离架构；构建 Direct / LangChain 双 Agent Adapter，共享受控 Orchestrator，实现工具白名单、Pydantic 参数校验、单次规划最多调用 3 个只读分析工具、证据 ID 校验、数字 Grounding 与规则降级。Direct / LangChain 双路径均通过 46/46 固定 Mock Agent 评估。

证据：`evaluation/evaluate_agent.py`、`backend/agent/`、`docs/execution/stage-2-report.md`、GitHub Actions `Mock Agent evaluation (Direct/LangChain)`。

## 描述 2（数据与可靠性）

> 基于 SQLAlchemy 2 + Alembic 构建 PostgreSQL 持久层，以 scope signature 与 insight fingerprint 实现分析范围和 AI 洞察幂等识别；结合 PostgreSQL UNIQUE 约束、原子 insert-or-get-existing 和 Redis Insight 短锁控制并发重复生成，Redis 故障时自动降级并由数据库保证最终一致性。

历史性能基准：10,000 行上传 P95 24.8s、预热摘要 P95 56ms、分页 P95 2.6ms。以上数据来自 React 迁移前阶段 5 的既有 benchmark，本轮未重新运行，不代表 React 迁移后的前端性能复测结果。

证据：`docs/execution/stage-3-report.md`、`docs/execution/stage-4-report.md`、`docs/execution/stage-5-report.md`。

## 描述 3（前端与工程交付）

> 将原 Streamlit UI 迁移为 React 19 + TypeScript SPA，使用 TanStack Query 构建 Typed API 数据层，完成数据上传、筛选、KPI、ECharts 可视化、服务端评论分页、AI Insight 和 Agent 执行详情等页面；通过 Nginx 反向代理统一 `/api` 边界并在服务端注入 Bearer Token，避免共享 Secret 进入浏览器 Bundle；使用多阶段 Docker 构建和 Docker Compose 编排 React/Nginx、FastAPI、PostgreSQL 与 Redis，并通过 GitHub Actions 分别执行 Python、前端与生产镜像构建质量门禁。

证据：`web/`、`Dockerfile.web`、`Dockerfile.api`、`nginx.conf.template`、`docker-compose.yml`、`.github/workflows/ci.yml`。

## 当前验证口径

- 前后端合计 **360+ 项自动化测试**：Python 使用 pytest（356 tests + 3 subtests），Frontend 使用 Vitest + React Testing Library（13 tests），当前普通测试总数为 369。
- 最新 Linux CI 的 Python 工程覆盖率为 **91.90%（约 92%）**，并设置 **80% 覆盖率硬门禁**。
- Direct / LangChain 固定 Mock Agent Eval 均为 **46/46**。
- GitHub Actions 集成 pytest、Vitest、ESLint、TypeScript Typecheck、Ruff、PostgreSQL/Alembic、Redis Integration、Agent Mock Eval、Dockerfile.api/Dockerfile.web 构建与 Compose 配置校验。
- `APP_ACCESS_TOKEN` 仅保护 Nginx → FastAPI 的共享服务访问，不代表用户登录、JWT、RBAC、OAuth 或多用户权限系统。

## 注意事项

- Live DeepSeek 对比未执行前，不得引用 Live 延迟、稳定性、成本或成功率数字。
- `pg_dump / pg_restore` 工具链已实现，但没有真实演练结果时不得声称备份恢复已通过。
- 历史 benchmark 必须明确其阶段和复测状态；不得表述为 React 迁移后的重新测量。
- 若未来 CI 指标未通过，应修复实现或删除简历数字，不得降低门禁来匹配宣传。
