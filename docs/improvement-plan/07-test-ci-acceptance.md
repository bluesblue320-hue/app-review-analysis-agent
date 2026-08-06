# 测试、CI 与验收矩阵

## 1. 质量策略

测试目标不是只追求覆盖率数字，而是证明以下不变量：

- 同一数据与筛选条件在前端、API、缓存和 Agent 中得到一致范围。
- 未授权请求不能访问业务数据。
- 删除、过期、重启、模型故障和 Redis 故障不会造成错误数据或功能整体不可用。
- 任何模型数字和结论都能追溯到成功工具证据。
- 真实评论正文和令牌不会进入日志、缓存任务消息或外部模型前的未脱敏路径。

## 2. 测试分层

| 层级 | 范围 | 工具 | 运行频率 |
| --- | --- | --- | --- |
| 单元 | Guardrail、筛选、序列化、脱敏、cache key、Repository 契约 | pytest | 每次提交 |
| 集成 | FastAPI + DB、Redis、迁移、事务、鉴权 | pytest/Testcontainers 或 Compose | 每个 PR |
| Agent 评估 | 46 个固定 Mock 案例 | evaluation runner | 每个 PR |
| 前端组件 | 表单、状态、错误映射、分页 | pytest/React Testing Library | 每个 PR |
| 端到端 | 登录至删除、AI 降级 | Playwright/Streamlit smoke | 每个 PR 或 nightly |
| 性能 | 10k 上传、摘要、分页、并发 | Locust/k6/pytest-benchmark | release candidate |
| 稳定性 | 重启、清理、外部故障、恢复 | Compose 脚本 | release candidate 48h |

## 3. 必测场景

### 3.1 Agent

- 46/46 固定评估。
- 未来预测、因果归因、流失人数和收入影响明确不可判断。
- 不可回答问题仍调用相关只读工具并列出缺失数据。
- 非法工具、额外参数、超过三次调用全部拒绝。
- 评论内提示注入不能改变系统指令。
- 无来源数字、未知 evidence ID、绝对化结论触发规则降级。
- `limitations` 从编排层传到 API 与前端。

### 3.2 Repository 与数据库

- 服务重启后 dataset/insight 可恢复。
- 上传中任一行写入异常，整个事务回滚。
- 删除数据集级联删除 reviews/insights/agent_runs/jobs。
- 过期边界：到期前可读、到期时不可读、重复清理幂等。
- 并发读取不出现部分数据或跨数据集串读。
- Insight 必须匹配 dataset、scope signature 和 sample size。
- Alembic 空库升级和已存在数据升级。

### 3.3 鉴权、日志与隐私

- 无 Authorization、错误 scheme、错误 token、前后空格边界。
- `/health`、`/ready` 公开且不泄露配置。
- 请求头 ID 合法时复用，非法时生成新 ID；错误体和响应头一致。
- 日志捕获测试断言不含 token、评论正文、邮箱、手机号、身份证和 prompt。
- 所有模型调用前输入已脱敏；未确认外部传输不发请求。

### 3.4 上传

- UTF-8、UTF-8 BOM、GB18030。
- 非法字节、空文件、非 CSV、缺必填列、重复列。
- 10 MB、10,000 行、50 列、5,000 字符的等于边界和超过边界。
- 有效/无效行统计和错误码准确。

### 3.5 Redis

- key 规范化、命中、TTL、schema version、失效。
- 不同数据集/筛选/洞察不串缓存。
- Redis 断开时结果与直算一致。
- 删除或过期后，即使 Redis 残留 value 也不能绕过数据库存在性检查。

### 3.6 前端

- 登录成功/失败/会话过期。
- 上传状态和容量错误。
- 筛选控件变化不请求，提交后只请求一次。
- 分页 offset 及筛选变化归零。
- dataset 失效、过期、删除后的状态清理。
- AI 未配置、模型失败、规则降级和 limitations 展示。

## 4. 覆盖率

- 全项目行覆盖率不低于 80%。
- `backend/agent`、`backend/services`、`backend/core/security*`、`backend/repositories` 建议分别不低于 85%。
- 新增安全、删除、过期和迁移逻辑必须有分支测试。
- 不允许通过大范围 `omit`、`pragma: no cover` 或降低阈值过门。

## 5. GitHub Actions 建议

```text
ci
├─ lint
├─ unit-test (Python support matrix)
├─ integration-postgres-redis
├─ agent-eval
├─ migration-check
├─ frontend-test-build
├─ e2e-compose
└─ image-scan / dependency-audit
```

### PR 必须通过

- Ruff check + format check。
- pytest 完整测试 + coverage 80%。
- Mock Agent `--fail-under`。
- PostgreSQL/Redis 集成测试。
- Alembic migration check。
- Streamlit smoke；Next.js 存在后增加 lint/test/build。
- Compose `/health`、`/ready` 和鉴权冒烟。

性能和 48 小时稳定性可以在 release workflow 执行，但报告必须关联到发布版本。

## 6. 推荐命令

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest --cov=. --cov-report=term-missing --cov-report=xml --cov-fail-under=80
python -m evaluation.evaluate_agent --mode mock --fail-under
alembic upgrade head
docker compose up -d --build
docker compose ps
```

Next.js 引入后：

```powershell
npm ci
npm run lint
npm run test
npm run build
npx playwright test
```

## 7. 验收报告模板

每个发布候选记录：

```text
版本/Commit：
镜像 Digest：
Alembic Revision：
测试总数与结果：
覆盖率：
Agent 评估：
上传 10k 耗时：
摘要 P50/P95/P99：
分页 P50/P95/P99：
48h 稳定性：
备份恢复：
安全检查：
已知限制：
批准人/日期：
```

## 8. 合并与发布阻断条件

任一项出现即阻断：

- 测试收集错误、覆盖率低于 80%、Agent 少于 46/46。
- 生产可在无 token 下启动。
- 日志或错误中出现 token/评论正文/完整模型输入。
- 删除后仍可从缓存或接口读到数据。
- 数据库迁移不能在空库复现。
- DeepSeek 或 Redis 故障导致确定性看板不可用。
- 性能结果未注明环境或无法重复。
