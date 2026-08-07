# 阶段 7 报告：README、演示与求职交付（CP7）

> 运行 ID：`upgrade-20260806`
> 日期：2026-08-07
> 总控 Agent 一次启动执行，阶段 7/8（最终阶段）

## 状态

- **阶段状态**：passed（文档/演示材料/门禁全部交付；Live 对比因外部依赖未执行，如实登记）
- **检查点**：CP7 ✅（代码/文档/门禁部分）
- **阶段开始 Commit**：阶段 6 提交（`feat(frontend): improve Streamlit evidence pagination...`）
- **8 阶段升级全部完成**：CP0 → CP7

## 本阶段目标

1. README 记录项目背景、架构、八个工具、双 Adapter、评估、数据库、Redis、降级和限制。
2. 增加本地、Docker、测试、迁移和评估命令。
3. 保存 Direct/LangChain Mock `46/46` 报告，明确其是确定性 CI 门禁。
4. 按阶段 2 冻结案例规范完成最终 Live 对比（Direct/LangChain 各 3 次 + `comparison.md`）——**外部依赖阻塞，如实登记**。
5. 准备五分钟演示数据和演示脚本。
6. 准备架构图、故障降级图和关键指标截图。
7. 形成三条只引用实际测试、性能报告和 Live 对比结果的简历描述。

## 实际交付物

### 新增 / 修改
| 文件 | 说明 |
| --- | --- |
| `README.md` | 全面重写：架构、八个工具、双 Adapter、API、本地/Docker/测试/迁移/评估命令、数据模型、Redis 契约、降级行为、已知限制、基线数字 |
| `.env.example` | 生产环境变量模板（APP_ACCESS_TOKEN 必填等） |
| `docs/architecture.svg` | 系统架构图（Streamlit → API Client → FastAPI → Repository/Redis/Agent → PG/Redis/DeepSeek） |
| `docs/degradation.svg` | 故障降级图（规则路由 / Tool Calling / 降级 / Redis 故障 / PG 兜底 / PG 不可用 503） |
| `docs/resume-claims.md` | 三条简历描述，每条附证据文件路径与"未测量不引用"原则 |
| `evaluation/generate_diagrams.py` | 可复现的 SVG 图生成脚本 |
| `evaluation/reports/mock-gate/direct|langchain/` | Direct/LangChain Mock 46/46 报告（summary.json/report.md/cases.jsonl） |
| `evaluation/reports/mock-gate/README.md` | 说明 Mock 为确定性 CI 门禁、复现命令、指标 |
| `evaluation/reports/live-comparison/comparison.md` | Live 对比模板：阻塞原因、复现命令、待填清单、约定指标、原则 |

## 五分钟演示流程（README + 组件已支持）

```text
1. 登录并上传评论 CSV（render_upload_section）
2. 查看确定性看板与评论分页（render_health_metrics + render_review_pagination）
3. 简单问题展示规则路由（routing 显示）
4. 复杂问题展示 LangChain 多工具调用（tool_calls 展开）
5. 不可回答问题展示 limitations（render_agent_section）
6. 展示 evidence_call_ids 与 Tool Trace（evidence_caption）
7. 关闭 Redis 展示实时计算降级（NullCache 直通）
8. 切换 Direct/LangChain Adapter（AGENT_ADAPTER 环境变量）
9. 展示 46/46 评估与 CI（evaluation/reports/mock-gate/）
```

## 关键指标汇总（全部可追溯）

| 指标 | 数值 | 证据 |
| --- | --- | --- |
| 完整 pytest | 340 passed + 3 subtests | 本仓库 |
| 全项目覆盖率 | 82.76%（80% 硬门禁） | docs/execution/stage-5-report.md |
| Direct Mock | 46/46 | evaluation/reports/mock-gate/direct/ |
| LangChain Mock | 46/46 | evaluation/reports/mock-gate/langchain/ |
| 10,000 行上传 P95 | 24.8s（< 30s） | evaluation/reports/perf/benchmark.json |
| 预热摘要 P95 | 56ms（< 3s） | evaluation/reports/perf/benchmark.json |
| 分页 limit=100 P95 | 2.6ms（< 1s） | evaluation/reports/perf/benchmark.json |
| 规则 Agent P95 | 188ms（< 3s） | evaluation/reports/perf/benchmark.json |
| 故障演练 | 6/6 通过 | evaluation/reports/failure-drill/report.json |

## 门禁是否通过

**通过** ✅

- [x] README 全面重写（架构/八个工具/双 Adapter/评估/数据库/Redis/降级/限制/命令）
- [x] 本地、Docker、测试、迁移、评估命令全部可执行（本机验证 pytest/Ruff/evaluate）
- [x] Direct/LangChain Mock 46/46 报告存档并注明为确定性 CI 门禁
- [x] 架构图与故障降级图生成
- [x] 三条简历描述，均附证据路径，遵守"未测量不引用"
- [x] 演示流程九步均有组件/文档支撑
- [x] 最终回归：340 passed + 3 subtests，Ruff 全绿，双 Adapter Mock 46/46

**未执行（外部依赖，不视为通过）**：
- [ ] Live 对比（Direct/LangChain 各 3 次 + comparison.md 填充）——需 `DEEPSEEK_API_KEY` + 网络；模板与命令已就绪（`evaluation/reports/live-comparison/comparison.md`）

## 已知限制（如实登记）

- Live 对比未执行；`docs/resume-claims.md` 与 README 均未引用任何 Live 数字（遵守主文档回退原则）。
- 本机无 Docker 守护进程 / PostgreSQL / Redis 实例：Compose 语法已校验，部署环境（CI Linux / 目标机器）完成实际启动验收。
- Windows coverage 追踪器不稳定已登记；CI Linux 以 80% 硬门禁最终复核。

## Git 提交

- CP7 阶段提交：见下方（阶段 7 提交消息）

## 项目升级总结（CP0 → CP7）

| 阶段 | 主题 | 测试 | 覆盖率 |
| --- | --- | --- | --- |
| CP0 | 基线 | 145+3 | 64% |
| CP1 | Agent 可靠性/数据质量/CI/安全 | 180+3 | 70% |
| CP2 | Direct/LangChain 双 Adapter | 267+3 | 75.53% |
| CP3 | PostgreSQL + Repository + Alembic | 301+3 | 82% |
| CP4 | Redis 缓存 + Insight 短锁 | 326+3 | 82.61% |
| CP5 | CI/Compose/日志/性能/故障 | 329+3 | 82.76% |
| CP6 | Streamlit 组件化 | 340+3 | - |
| CP7 | README/演示/求职交付 | 340+3 | 80% 门禁（CI 复核） |
