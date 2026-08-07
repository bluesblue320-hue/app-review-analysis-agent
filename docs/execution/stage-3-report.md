# 阶段 3 报告：Repository、PostgreSQL 与 Alembic（CP3）

> 运行 ID：`upgrade-20260806`
> 日期：2026-08-06
> 总控 Agent 一次启动执行，阶段 3/8

## 状态

- **阶段状态**：passed
- **检查点**：CP3 ✅
- **阶段开始 Commit**：阶段 2 提交（`feat(agent): add Direct/LangChain dual adapters...`）
- **允许进入阶段 4**：是

## 本阶段目标

1. 定义 DatasetRepository 和 InsightRepository Protocol，保留内存实现供单元测试。
2. SQLAlchemy 2 实现：级联删除、唯一约束、内容哈希、insight fingerprint。
3. Alembic 初始迁移（外键、唯一约束、索引）。
4. 上传使用单事务批量插入；任何失败全部回滚。
5. InsightRepository 按 `insight_fingerprint` 查询、原子 insert-or-get-existing、过期同记录刷新。
6. 范围签名：`sha256(content_hash + canonical_filters + analysis_version)`，与 Redis cache key 职责分离。
7. `/ready` 数据库检查端点。
8. 全项目覆盖率不低于阶段 2 的 75% 门禁；Repository/PostgreSQL 相关新增代码覆盖率 >= 80%。

## 实际修改文件

### 新增
| 文件 | 说明 |
| --- | --- |
| `backend/services/repositories.py` | `DatasetRepository`/`InsightRepository` Protocol；`compute_content_hash`/`canonical_filters`/`compute_scope_signature`/`compute_insight_fingerprint`；`ANALYSIS_VERSION` |
| `alembic.ini`、`alembic/env.py`、`alembic/script.py.mako`、`alembic/versions/aeb4cbb3b3b2_*.py` | Alembic 配置与初始迁移（datasets/reviews/insights 全表） |
| `tests/test_repositories.py` | 范围签名稳定性、canonical filters 规范化、fingerprint 固定字段顺序、内存 Repository 去重/过期刷新（22 测试） |
| `tests/test_sqlalchemy_persistence.py` | SQLAlchemy 持久化：重启恢复、级联删除、过期清理幂等、并发 upsert 单记录、唯一冲突 insert-or-get、过期刷新同 ID、迁移 upgrade/downgrade 往返（10 测试） |

### 修改
| 文件 | 改动 |
| --- | --- |
| `backend/storage/database.py` | `DatasetModel` 增加 removed_rows/invalid_rating_rows/invalid_reasons_json/content_hash/analysis_version；`ReviewModel` 增加 created_at + (dataset_id,row_number) 唯一约束；`InsightModel` 增加 provider/model_name/analysis_version/insight_fingerprint（unique） |
| `backend/services/sqlalchemy_dataset_store.py` | 上传时计算 content_hash 并持久化；review 写入 created_at |
| `backend/services/sqlalchemy_insight_store.py` | 完整重写：fingerprint 查询、原子 upsert（唯一冲突回滚后读已有记录）、过期刷新原记录不新增行 |
| `backend/services/insight_store.py` | `InMemoryInsightStore` 增加 find_by_fingerprint/upsert_fingerprint/refresh_expired，保持相同契约（含去重语义） |
| `backend/services/ai_service.py` | 统一 scope 签名（content_hash + canonical_filters + v1）；生成前按 fingerprint 复用未过期洞察 |
| `backend/services/analytics_service.py` | 统一 scope 签名算法，与 AI 洞察一致，修复跨服务 mismatch |
| `backend/services/agent_service.py` | 统一 scope 签名算法 |
| `backend/routers/health.py` | 新增 `/ready` 端点（store 不可达返回 503） |
| `tests/test_insight_store.py` | 更新为新契约：相同 fingerprint 去重返回同一 ID、过期刷新保持同 ID |

## 主要实现

1. **Repository Protocol**：Service 只依赖 `DatasetRepository`/`InsightRepository`，单元测试用内存实现，生产用 SQLAlchemy 实现；内存与 SQL 行为一致（含去重语义）。
2. **范围签名**：上传时计算规范化 `content_hash`；`scope_signature = sha256(content_hash + canonical_filters + analysis_version)`；canonical_filters 对类别去重排序、空值固定表示、关键词去空格、浮点固定格式、JSON 按 key 排序；不包含 insight_id。
3. **Insight fingerprint**：固定字段顺序（dataset_id, scope_signature, sample_size, analysis_version, provider, model_name）JSON 数组 SHA-256；数据库 `UNIQUE(insight_fingerprint)` 保证最终仅一条记录。
4. **原子 insert-or-get-existing**：并发插入触发唯一约束冲突时，保存点回滚冲突语句后重新查询返回已有记录，不产生 500。
5. **过期刷新**：相同 fingerprint 已过期 → 更新原记录 content/provider/model/created_at/expires_at，不新增第二行。
6. **级联删除**：删除 dataset 时 reviews/insights 通过 FK ON DELETE CASCADE 一并清除。
7. **迁移验证**：空数据库 `alembic upgrade head` 建全表；`downgrade base` + `upgrade head` 往返验证通过。
8. **Alembic 接线**：`DATABASE_URL` 从环境变量或 settings 解析，生产不调用 `Base.metadata.create_all` 作为唯一路径（保留 create_all 用于本地 SQLite 集成测试兼容）。

## 实际运行的命令与结果

| 命令 | 退出状态 | 结果 |
| --- | --- | --- |
| `python -m pytest` | 0 | **301 passed, 3 subtests passed**（阶段 2 为 267+3） |
| `coverage run -m pytest` + `coverage report` | 0 | **覆盖率 82%**（2839 stmts，499 未覆盖） |
| `coverage xml` | 0 | coverage.xml 生成 |
| `python -m ruff check .` | 0 | All checks passed |
| `python -m ruff format --check .` | 0 | 已格式化 |
| `python -m evaluation.evaluate_agent --mode mock --adapter direct --fail-under` | 0 | **46/46 通过**（回归保持） |
| `python -m evaluation.evaluate_agent --mode mock --adapter langchain --fail-under` | 0 | **46/46 通过**（回归保持） |
| `alembic upgrade head`（空库） | 0 | datasets/reviews/insights 全表 + 索引/约束 |
| `alembic downgrade base` + `upgrade head` | 0 | 往返验证通过 |

## 测试结果

- 完整 pytest：301 passed + 3 subtests，0 failed。
- 新增 32 个测试：范围签名稳定性（同内容同筛选稳定、筛选/版本/内容变化签名变化、不含 insight_id）；canonical filters 规范化；fingerprint 固定顺序；内存/SQL 双实现去重；并发 4 线程 upsert 最终单记录；唯一冲突返回已有记录不 500；过期刷新同 ID 不新增行；重启恢复 dataset/insight；级联删除清 reviews+insights；过期清理幂等；迁移往返。

## 覆盖率

- **全项目：82%**（高于阶段 2 的 75.53% 与门禁 75%）。
- Repository/PostgreSQL 相关：`repositories.py` 94%、`sqlalchemy_dataset_store.py` 96%、`sqlalchemy_insight_store.py` 83%、`storage/database.py` 95%、`insight_store.py` 95%、`agent_service.py` 100%、`ai_service.py` 81%、`analytics_service.py` 81%。
- 全部达到"新增或修改代码覆盖率 >= 80%"验收要求。

## 门禁是否通过

**通过** ✅

- [x] 完整 pytest 通过（301 + 3）
- [x] 全项目覆盖率 82% >= 75% 门禁
- [x] Repository/PostgreSQL/迁移相关代码覆盖率 >= 80%
- [x] 空 PostgreSQL 执行 `alembic upgrade head`
- [x] 临时数据库 downgrade/upgrade 往返
- [x] 服务重启后 dataset 和 insight 可恢复
- [x] 删除级联清除 reviews 和 insights
- [x] 到期前可读、到期时不可读、重复清理幂等
- [x] 相同 fingerprint 并发请求最终只保存一条 Insight 记录
- [x] 唯一约束冲突执行 insert-or-get-existing，返回已有记录且不产生 500
- [x] 已过期相同 fingerprint 刷新原记录，保持相同 Insight ID
- [x] 相同筛选签名稳定，筛选或 analysis version 变化时签名变化
- [x] `/ready` 端点存在；store 不可达返回 503
- [x] 双 Adapter Mock 46/46 回归保持

## Git 提交

- CP3 阶段提交：见下方（阶段 3 提交消息）

## 下一阶段输入条件

- 阶段 4 可开始。依赖：CP3 通过、PostgreSQL 事实来源、范围签名稳定、删除流程稳定。
- 阶段 4 目标：Redis 分析缓存（Cache Protocol/NullCache/MemoryCache/RedisCache）、Insight 原子短锁、缓存失效与降级、指标记录。
