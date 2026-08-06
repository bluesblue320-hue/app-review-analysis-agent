# 部署与运维手册

> 本手册描述目标运行方式。Compose 和脚本落地后，应把示例命令替换为仓库中的真实命令并在暂存环境验证。

## 1. 生产拓扑

```text
Internet/Internal Network
  └─ frontend:8501 或 web:3000（唯一暴露）
       └─ api:8000（内部网络，单 worker）
            ├─ postgres:5432（持久卷）
            ├─ redis:6379（内部网络）
            └─ worker（仅启用异步任务时）
```

单实例 MVP 要求 FastAPI 单 worker；如未来增加 worker，必须先确认所有状态已离开进程内存，清理任务和缓存锁支持多实例。

## 2. 必需 Secret 与配置

生产必需：

- `APP_ENV=production`
- `APP_ACCESS_TOKEN`
- `DATABASE_URL`
- PostgreSQL 用户、密码和数据库名
- Next.js 启用时的 `WEB_SESSION_SECRET`

可选：

- `REDIS_URL`
- `DEEPSEEK_API_KEY`
- `AGENT_PROVIDER=direct|langchain`

Secret 管理原则：

- 不提交 `.env`、Compose override、数据库 dump 或 secret 文件。
- 不把 secret 作为 Docker build args。
- 修改令牌后重启 API/前端会话层，并使旧会话失效。
- 运维排障命令输出中不得打印完整环境变量。

## 3. 首次部署

1. 创建持久卷、内部网络和 secret。
2. 启动 PostgreSQL/Redis，等待健康检查。
3. 执行 Alembic `upgrade head`。
4. 启动 API，确认 `/health` 和 `/ready`。
5. 启动前端；只映射前端端口。
6. 使用合成 CSV 执行登录、上传、摘要、分页、规则 Agent 和删除冒烟。
7. 配置备份计划和日志保留后才允许导入真实授权数据。

示例：

```powershell
docker compose pull
docker compose run --rm migrate alembic upgrade head
docker compose up -d postgres redis api frontend
docker compose ps
```

## 4. 日常健康检查

### 每次部署

- `/api/v1/health` 返回存活。
- `/api/v1/ready` 的 database 为 ok，migration 为 head。
- 无 token 访问业务 API 返回 401。
- 正确 token 可以上传合成数据并查询摘要。
- 删除后相同 dataset ID 返回 `dataset_not_found`。

### 每日

- 5xx 和 401 异常增长。
- API/摘要/分页 P95。
- PostgreSQL 连接、磁盘、慢查询和备份结果。
- Redis 内存、eviction、命中率和错误率。
- Agent fallback、guardrail rejection、模型超时/限流。
- 过期清理成功时间和删除数量。

### 每周

- 随机恢复最近一次数据库备份到隔离环境。
- 检查依赖和镜像漏洞。
- 检查日志中是否意外包含 PII/令牌模式。
- 检查过期数据是否按期消失。

## 5. 备份与恢复

### 备份

- PostgreSQL 每日至少一次逻辑或物理备份，保留策略独立于应用 30 天数据保留。
- 备份加密并限制访问。
- 记录开始时间、结束时间、大小、校验和和结果。
- Redis 不作为业务恢复来源，可不备份缓存；若作为 Celery broker，任务事实仍应在 PostgreSQL。

### 恢复演练

1. 创建隔离 PostgreSQL 实例。
2. 恢复备份，不覆盖生产。
3. 执行 schema revision 检查。
4. 抽样核对 datasets/reviews/insights 计数和外键。
5. 启动兼容版本 API，执行读取和删除测试。
6. 记录 RTO/RPO 和异常。

未完成恢复演练的备份不能视为可用备份。

## 6. 数据删除与过期

### 主动删除

- 通过 API 删除，不手工删 reviews。
- 使用 request ID 跟踪日志，只记录 dataset ID 的安全哈希。
- 确认数据库事务提交、缓存失效、任务取消/失效。
- 不在日志中输出被删评论内容。

### 定时清理

- 启动时一次、每小时一次。
- 每批限制数量，避免长事务。
- 清理失败只记录 error type，并触发告警；下一轮可重试。
- 批量故障时使用受版本控制的管理命令补跑，不直接执行临时生产 SQL。

## 7. 常见故障处理

### API 不 ready

检查顺序：

1. PostgreSQL 是否健康、磁盘是否满。
2. `DATABASE_URL` secret 是否加载，但不要打印值。
3. Alembic revision 是否为 head。
4. 连接池是否耗尽、是否存在长事务。
5. 最近迁移是否兼容当前镜像。

处理：先停止流量或切回上一兼容镜像；数据库变更优先向前修复，不直接 downgrade。

### Redis 故障

预期行为：

- `/ready` 可显示 degraded。
- 摘要和分页直接访问数据库/计算。
- 错误率不应显著上升，P95 可能变慢。

处理：关闭缓存开关或修复 Redis；不要清空数据库，也不要把 Redis 临时改为事实存储。

### DeepSeek 故障

预期行为：

- 确定性看板和规则 Agent 正常。
- Agent 在总超时内 `rule_fallback`。
- 外部模型错误只显示稳定提示，不展示 provider 响应全文。

处理：切换 `AGENT_PROVIDER=direct` 无法解决 provider 本身故障时，禁用外部模型并继续规则模式。

### 摘要数据不一致

1. 对比 dataset ID、filters 规范化结果、scope signature 和算法版本。
2. 绕过 Redis 重新计算。
3. 检查缓存 key 是否缺少 insight/view/算法版本。
4. 检查前端是否在 filters 变化后重置分页和 Query key。

在原因未明确前关闭相关缓存，不能手工修改结果。

### 数据库磁盘接近满

- 暂停新上传，保留读取与删除能力。
- 检查过期清理和备份文件是否占用数据库卷。
- 扩容后运行受控清理。
- 禁止直接删除 PostgreSQL 数据目录文件。

## 8. 日志与告警

建议告警：

| 告警 | 条件建议 | 等级 |
| --- | --- | --- |
| API 5xx | 5 分钟 > 2% | P1 |
| DB not ready | 连续 2 次 | P1 |
| 删除后数据仍可读 | 任意一次 | P0 |
| 日志发现 token/PII | 任意一次 | P0 |
| 摘要 P95 | 15 分钟 > 3 秒 | P2 |
| Redis 错误率 | 10 分钟 > 20% | P2 |
| Agent fallback | 明显高于基线 | P2 |
| 过期清理失败 | 连续 2 个周期 | P2 |
| 备份失败 | 任意计划任务失败 | P1 |

日志保留时间应由内部合规要求确定，但日志不得被当作评论数据备份。

## 9. 发布与回滚检查表

发布前：

- [ ] CI 全绿，Agent 46/46，覆盖率 >= 80%。
- [ ] 迁移在空库和备份恢复库验证。
- [ ] 镜像 digest 和配置变更已记录。
- [ ] 备份成功且最近恢复演练有效。
- [ ] 回滚镜像与前端切换路径可用。

发布后：

- [ ] health/ready 正常。
- [ ] 未授权访问为 401。
- [ ] 合成数据核心旅程通过。
- [ ] 监控无异常 5xx、慢查询或连接泄漏。
- [ ] 删除测试数据并确认级联和缓存失效。

## 10. 安全事件最小响应

若怀疑令牌或评论数据泄露：

1. 立即撤销/轮换访问令牌和相关 provider key。
2. 暂停外部模型调用和新上传，保留必要的只读取证日志。
3. 确认泄露范围、时间和数据集，不把敏感内容复制到协作聊天。
4. 检查日志、缓存、任务消息和错误监控。
5. 按组织内部安全流程通知并记录处置。
6. 修复后通过隐私回归测试再恢复服务。
