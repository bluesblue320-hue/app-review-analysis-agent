# 阶段 2：持久化、安全与部署

> 周期：第 2–4 周  
> 目标：建立可重启恢复、可删除、可过期、可审计的服务端数据层，并完成内部部署所需的鉴权、脱敏、日志和容器能力。

## 1. 数据层设计

### 1.1 Repository 接口

业务服务只依赖协议，不依赖全局字典、DataFrame 单例或 SQLAlchemy Session：

```python
class DatasetRepository(Protocol):
    def create(self, upload: PreparedDataset) -> DatasetRecord: ...
    def get(self, dataset_id: str) -> DatasetRecord: ...
    def delete(self, dataset_id: str) -> None: ...
    def cleanup_expired(self, now: datetime) -> int: ...
    def ready(self) -> bool: ...
```

至少提供：

- `InMemoryDatasetRepository`：单元测试和快速开发。
- `SqlAlchemyDatasetRepository`：PostgreSQL 生产实现；SQLite 用于本地集成测试。
- Insight Repository 与 Job Repository 采用相同边界。

禁止在 Router 中直接创建 Session，事务必须由 Repository 或 Unit of Work 管理。

### 1.2 表与级联

| 表 | 用途 | 核心字段 |
| --- | --- | --- |
| `datasets` | 上传元数据和生命周期 | `dataset_id`、文件名、原始/有效行数、列定义、状态、`created_at`、`expires_at` |
| `reviews` | 评论和固定分析字段 | `id`、`dataset_id`、`row_number`、评分、内容、时间、版本、情绪、问题类型、风险标签、`extra_json` |
| `insights` | AI 洞察结果 | `insight_id`、`dataset_id`、范围签名、样本数、模型信息、结果 JSON、`expires_at` |
| `agent_runs` | 可审计的 Agent 元数据 | `run_id`、`dataset_id`、routing、intent、工具摘要、限制、状态、耗时；不保存完整提示 |
| `jobs` | 可选异步任务事实记录 | `job_id`、类型、状态、进度、错误类型、创建/完成时间 |

约束：

- `reviews.dataset_id`、`insights.dataset_id`、`agent_runs.dataset_id` 使用外键和 `ON DELETE CASCADE`。
- `(dataset_id, row_number)` 唯一。
- `expires_at`、`dataset_id`、分页/筛选字段建立组合索引，具体索引以查询计划验证为准。
- 原上传字段中固定分析字段独立列存储，其他字段进入 `extra_json`；不要在 payload JSON 中重复保存全部固定字段。
- 数据时间统一存 UTC，API 输出 ISO 8601。

### 1.3 迁移

- 使用 Alembic，不在生产启动时调用 `Base.metadata.create_all`。
- 首次迁移创建表、外键、索引和约束。
- CI 对空库执行 `upgrade head`，再执行 `downgrade -1` 与重新升级的冒烟验证。
- Compose 中使用独立迁移命令或一次性 migration service，API 仅在迁移成功后启动。

## 2. 数据生命周期

- 默认保留 30 天，创建数据集时写入不可为空的 `expires_at`。
- 洞察和 Agent 运行记录不能晚于所属数据集过期时间。
- 应用启动时执行一次清理，此后每小时执行；清理必须幂等。
- 多进程或任务 worker 场景使用数据库 advisory lock 或 Redis 短锁，避免多个实例同时做同一批清理。
- 主动删除 `DELETE /api/v1/datasets/{dataset_id}` 在一个事务内删除数据集及级联记录，提交后再清除缓存。
- 重复删除统一返回 `dataset_not_found`，不泄露该 ID 是否曾经存在。

## 3. 上传安全与校验

固定限制：

| 限制 | 默认值 | 错误码建议 |
| --- | --- | --- |
| 文件大小 | 10 MB | `upload_too_large` |
| 数据行数 | 10,000 | `dataset_row_limit_exceeded` |
| 数据列数 | 50 | `dataset_column_limit_exceeded` |
| 单条评论字符数 | 5,000 | `review_text_too_long` |
| 文件类型 | CSV | `unsupported_file_type` |
| 编码 | UTF-8、UTF-8 BOM、GB18030 | `unsupported_encoding` |

处理顺序：

1. 流式或限长读取，超过 10 MB 立即停止。
2. 先检测 BOM，依次尝试 `utf-8-sig`、`utf-8`、`gb18030`，失败返回明确编码错误。
3. 读取表头后校验列数和必填列。
4. 分块或带上限解析，避免先加载无限行再判断。
5. 校验评论长度、评分和有效行；响应同时返回原始行、有效行、无效行及原因摘要。
6. 在单一事务中写入数据集和评论；任何异常回滚全部数据。

CSV 公式注入属于导出风险：如果未来增加导出，在以 `= + - @` 开头的文本前做安全转义，数据库中仍保留原始授权数据。

## 4. 鉴权与会话

- `/api/v1/health`、`/api/v1/ready` 公开，其余 API 必须验证 `Authorization: Bearer <token>`。
- 使用常量时间比较验证共享令牌。
- `APP_ENV=production` 且 `APP_ACCESS_TOKEN` 为空时，进程拒绝启动。
- Swagger/OpenAPI 在生产默认关闭或同样受鉴权保护。
- Streamlit 使用密码输入框；令牌只放 `st.session_state`，不放 `st.cache_resource`、URL、日志或磁盘。
- 不能缓存包含 Authorization 头的全局 HTTP Client；可共享无状态 transport，但每次请求从当前会话注入令牌。

## 5. PII 脱敏

所有发往 DeepSeek 或其他外部模型的评论样本、标题、工具证据都必须经过同一脱敏器：

| 类型 | 示例 | 输出 |
| --- | --- | --- |
| 中国大陆手机号 | `13812345678` | `[PHONE]` |
| 邮箱 | `name@example.com` | `[EMAIL]` |
| 身份证样式 | 18 位含末位 X | `[CN_ID]` |

要求：

- 脱敏在组装模型消息之前完成，不能依赖提示词要求模型自行脱敏。
- 单元测试覆盖相邻标点、大小写 X、混合文本和非匹配数字。
- 界面首次外部模型调用前展示“数据将发送至外部服务”的说明，并要求当前会话确认。
- 用户未确认时仍允许使用规则 Agent 和确定性看板。
- 日志、Agent Run 和错误详情中不保存脱敏前正文。

## 6. 请求 ID、错误和日志

### 请求 ID

- 接受格式合法的 `X-Request-ID`，否则生成 UUID。
- 响应头始终返回 `X-Request-ID`。
- 统一错误体包含相同 `request_id`。

```json
{
  "error": {
    "code": "dataset_not_found",
    "message": "指定的数据集不存在或已过期。"
  },
  "request_id": "01J..."
}
```

### JSON 日志字段

- `timestamp`、`level`、`service`、`environment`、`event`。
- `request_id`、method、route template、status、duration_ms、error_type。
- 可选 `dataset_id_hash`，不直接记录完整用户输入。

禁止记录 Authorization、Cookie、评论正文、上传文件内容、数据库密码、API Key、完整模型输入输出。

## 7. 健康检查

- `GET /api/v1/health`：仅说明进程存活，不访问数据库/Redis/DeepSeek。
- `GET /api/v1/ready`：检查数据库连接和迁移版本；Redis 若配置为可选缓存，则状态可标记 `degraded` 而非让 API 不可用。
- 两个接口都不返回 URL、用户名、密钥或模型配置详情。

建议响应：

```json
{
  "status": "ready",
  "checks": {"database": "ok", "redis": "degraded"}
}
```

## 8. 容器部署

Gate A Compose 至少包含：

- `frontend`：Streamlit，唯一对宿主机暴露的服务。
- `api`：FastAPI，内部网络，固定单 worker。
- `postgres`：持久卷、健康检查。
- `redis`：内部网络、持久化按用途选择，设置内存和淘汰策略。
- `migrate`：一次性 Alembic 升级任务。

镜像要求：

- 非 root 用户运行。
- 固定依赖版本，生产镜像不包含测试缓存、CSV 示例和密钥。
- API 与前端分别构建，健康检查使用内部服务名。
- `.env` 不进入镜像；通过部署环境或 secret 挂载。

## 9. 实施任务

| 编号 | 任务 | 验收 |
| --- | --- | --- |
| P2-001 | 定义 Repository Protocol 和内存实现 | 服务单测不依赖数据库 |
| P2-002 | 完成 SQLAlchemy 模型和 PostgreSQL 实现 | 重启恢复、事务回滚、并发读通过 |
| P2-003 | 建立 Alembic | 空库可升级，版本可检查 |
| P2-004 | 实现级联删除和 30 天过期 | 删除/过期后数据、洞察、缓存均不可见 |
| P2-005 | 完成上传限制和编码 | 所有限制和编码测试通过 |
| P2-006 | 接入 Bearer 中间件 | 公开路径例外，其余全保护 |
| P2-007 | 实现统一 PII 脱敏 | 所有外部模型路径复用同一函数 |
| P2-008 | 接入请求 ID 和 JSON 日志 | 错误体、响应头、日志一致 |
| P2-009 | 实现 `/ready` | DB 故障返回非 ready；不泄露配置 |
| P2-010 | 完成 Dockerfile/Compose | 重启恢复和健康检查通过 |

## 10. 退出条件

- PostgreSQL 容器重启后数据可查询，事务失败不留下半个数据集。
- 级联删除、30 天过期、每小时清理和重复删除测试通过。
- 鉴权缺失/错误令牌均为 401；令牌不出现在日志、错误和 trace 中。
- 三种编码和四项上传限制全部有自动测试。
- PII 脱敏覆盖所有模型调用路径，并有界面会话确认。
- Compose 只暴露前端，API 为单 worker，`/health` 和 `/ready` 语义正确。

## 11. 风险与回退

- 数据库迁移失败：阻止 API 启动，恢复数据库备份并回滚镜像，不自动执行破坏性 downgrade。
- Redis 不可用：禁用缓存继续服务，不能切到本地不一致写入。
- 清理任务异常：记录错误并继续提供读取；由运维命令补跑，不能在请求线程大批删除。
- 新 Repository 出现回归：开发可切回内存实现，但生产不允许以此绕过持久化验收。
