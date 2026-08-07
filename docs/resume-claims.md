# 简历描述（基于仓库内可追溯的测试与报告）

> 原则：三条描述只引用实际测试、性能报告和 Live 对比结果；任何数字均可在 `evaluation/reports/`、`docs/execution/` 中找到证据。Live 对比未执行前，不引用 Live 相关数字。

## 描述 1（工程能力）

> 独立设计并落地一个 App Store 中文评论舆情分析 Agent（Streamlit + FastAPI + PostgreSQL + Redis）：实现 Direct / LangChain 双 Agent Adapter 共享同一受控 Orchestrator（工具白名单、Pydantic 参数校验、单次规划最多选择 3 个只读分析工具、规则降级），通过 46/46 固定 Mock 评估作为 CI 确定性门禁，全项目测试 340+ 通过、覆盖率 82.76%（80% 硬门禁）。

证据：`evaluation/reports/mock-gate/`（46/46 × 2）、`docs/execution/stage-2-report.md`、`docs/execution/stage-5-report.md`。

## 描述 2（数据与可靠性）

> 以 SQLAlchemy 2 + Alembic 实现 PostgreSQL 持久化：`insight_fingerprint` 唯一约束配合原子 insert-or-get-existing 与过期同 ID 刷新，保证并发洞察最终仅一条记录；范围签名（content_hash + canonical_filters + analysis_version）统一 ai/analytics/agent 三服务；Redis 分析缓存与 Insight 短锁全部故障降级，由数据库约束兜底；10,000 行上传 P95 24.8s、预热摘要 P95 56ms、分页 P95 2.6ms（目标全部达标）。

证据：`docs/execution/stage-3-report.md`、`docs/execution/stage-4-report.md`、`evaluation/reports/perf/benchmark.json`。

## 描述 3（交付与安全）

> 完成从单体到组件化的 Streamlit 重构（559 行 → 91 行装配 + 20 个组件），接入 Bearer 鉴权、request ID、结构化 JSON 日志（不含 token/PII/评论正文）、PII 脱敏；交付 Docker Compose 生产部署（仅前端暴露、API 先迁移后启动）、GitHub Actions 全链路 CI（含 PostgreSQL/Redis service 容器与迁移往返）、6/6 故障演练与 pg_dump 备份恢复演练。

证据：`docs/execution/stage-1-report.md`、`docs/execution/stage-5-report.md`、`docs/execution/stage-6-report.md`、`evaluation/reports/failure-drill/report.json`。

## 注意事项

- Live 对比（Direct/LangChain 各 3 次 + comparison.md）未执行前，不得在简历/README 中引用 Live 相关延迟、稳定性或成本数字。
- 若某一指标未来未通过，从简历与 README 中删除该数字，不修改测试门槛来匹配宣传。
