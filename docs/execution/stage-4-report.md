# 阶段 4 报告：Redis 分析缓存与 Insight 短锁（CP4）

> 运行 ID：`upgrade-20260806`
> 日期：2026-08-07
> 总控 Agent 一次启动执行，阶段 4/8

## 状态

- **阶段状态**：passed
- **检查点**：CP4 ✅
- **阶段开始 Commit**：阶段 3 提交（`feat(storage): persist datasets reviews and insights with PostgreSQL`）
- **允许进入阶段 5**：是

## 本阶段目标

1. 完成 Cache Protocol、NullCache、MemoryCache 和 RedisCache。
2. 按 Key 规范缓存摘要（`ara:{env}:v1:analytics:{dataset_id}:{scope_signature}:{analysis_type}:{insight_id_or_none}`）。
3. 读取缓存前验证 PostgreSQL 数据集存在性。
4. 缓存值包含 schema version，且严格 JSON 序列化。
5. 数据集 key 索引 + 最佳努力失效，不使用 `KEYS`。
6. Insight 原子短锁：token 安全释放、自动 TTL；锁只减少重复模型调用，不承担数据唯一性。
7. 获取锁前按 `insight_fingerprint` 查询 PostgreSQL，获得锁后再次查询；命中未过期记录则不调用模型。
8. Redis get/set/delete/lock 异常全部降级；由 PostgreSQL 唯一约束和 insert-or-get-existing 继续保证不产生重复 Insight 行。
9. 记录 cache hit、cache error、锁竞争、模型调用次数和实时计算耗时（结构预留）。

## 实际修改文件

### 新增
| 文件 | 说明 |
| --- | --- |
| `tests/test_redis_cache_integration.py` | 热缓存一致性、schema version 失效、筛选隔离、数据集失效、Redis 断开降级、短锁（8 测试） |

### 修改
| 文件 | 改动 |
| --- | --- |
| `backend/services/cache_service.py` | 重写：Cache Protocol（get/set/delete+ttl）、`NullCache`/`MemoryCache`/`RedisCache`、`InsightLock` 原子短锁（Redis SET NX EX + token 安全释放 pipeline、MemoryCache 本地锁、NullCache 直通）、`analytics_cache_key`/`insight_lock_key`/`dataset_keys_key`/`_env_tag`/`build_cache`；`CACHE_SCHEMA_VERSION` |
| `backend/services/analytics_service.py` | 缓存 key 改为 scope_signature + analysis_type + insight_id 规范；读取缓存前先 `store.get` 验证数据集存在；缓存值包装 `schema_version + payload`；`_valid_cache_payload` 校验 |
| `backend/services/ai_service.py` | 生成洞察前先查 fingerprint 复用；进入 `InsightLock` 短锁后再次查询；锁内调用模型并 upsert |

## 主要实现

1. **Cache 三实现**：`NullCache`（无 Redis 时 no-op）、`MemoryCache`（线程安全、TTL、测试/本地）、`RedisCache`（decode_responses、异常全部吞掉返回 None/继续）。`build_cache` 按 Redis URL > Memory > Null 选择。
2. **Key 规范**：`ara:{env}:v1:analytics:{dataset_id}:{scope_signature}:{analysis_type}:{insight_id}`；`ara:{env}:v1:lock:insight:{dataset_id}:{scope_signature}`；`ara:{env}:v1:dataset-keys:{dataset_id}`。不使用 `KEYS`（scan_iter + count 批次）。
3. **缓存值 schema version**：`{"schema_version": 1, "payload": {...}}`，版本不匹配视为 miss。
4. **失效**：`invalidate_dataset` 用 scan_iter 按数据集前缀批量删除缓存与锁；Redis 异常降级为尽力而为。
5. **Insight 短锁**：`InsightLock.acquire` Redis 用 `SET key token NX EX ttl` 原子抢占；token 安全释放用 WATCH/MULTI 校验 token 一致才 DEL；MemoryCache 用 `_entries` + monotonic TTL 模拟；NullCache 直通（靠数据库约束兜底）。锁只做成本优化，不承诺消除所有重复调用。
6. **锁流程**：ai_service 获取锁前按 fingerprint 查 PostgreSQL（命中未过期直接复用）→ 获取锁 → 再次查询（并发方可能已写入）→ 命中复用 → 未命中调模型 → `create`（内部 upsert 唯一约束兜底）。
7. **降级保证**：Redis 全部异常吞掉：读失败→miss、写失败→忽略、锁获取失败→放行（数据库唯一约束保证最终单行）。

## 实际运行的命令与结果

| 命令 | 退出状态 | 结果 |
| --- | --- | --- |
| `python -m pytest` | 0 | **326 passed, 3 subtests passed**（阶段 3 为 301+3） |
| coverage（三批次合并） | 0 | **覆盖率 82.61%**（2978 stmts，line-rate 0.8261） |
| `python -m coverage xml` | 0 | coverage.xml 生成 |
| `python -m ruff check .` | 0 | All checks passed |
| `python -m ruff format --check .` | 0 | 已格式化 |
| `python -m evaluation.evaluate_agent --mode mock --adapter direct --fail-under` | 0 | **46/46 通过**（回归保持） |
| `python -m evaluation.evaluate_agent --mode mock --adapter langchain --fail-under` | 0 | **46/46 通过**（回归保持） |

## 测试结果

- 完整 pytest：326 passed + 3 subtests，0 failed。
- cache_service 单元测试 31 个：Null/Memory/Redis 三实现、TTL 过期、删除、异常吞掉、scan 失效、lock 互斥/token 安全释放/TTL 恢复/上下文释放、Redis 锁 acquire/release/失败放行。
- 阶段 4 集成测试 8 个：冷→热缓存一致性、schema version 变化失效、不同筛选不串缓存、数据集失效后重建、Redis down 时分析仍可用、短锁排他、上下文释放、缓存值 JSON 可序列化。

## 覆盖率

- **全项目：82.61%**（高于阶段 3 的 82% 与门禁 75%）。
- 阶段 4 核心：`cache_service.py` 90%、`ai_service.py` 80%、`analytics_service.py` 83%、`repositories.py` 94%、`sqlalchemy_dataset_store.py` 96%、`sqlalchemy_insight_store.py` 83%。
- 全部达到"Redis、Cache Protocol、失效和短锁相关新增或修改代码覆盖率 >= 80%"验收要求。

## 已知限制（如实登记）

- Windows 环境下全量 `coverage run -m pytest` 偶发原生 Segfault（与 pandas/jieba 原生扩展冲突），本次采用三批次互斥测试文件合并测量（批次间无重叠），覆盖率 82.61% 为确定性结果；该问题不影响测试本身（326 全通过）。
- 阶段 4 未接入真实 Redis 实例（环境无 Redis 服务），Redis 行为通过 mock redis-py 客户端验证；真实 Redis 集成验收留在阶段 5/6 部署环境。

## 门禁是否通过

**通过** ✅

- [x] 完整 pytest 通过（326 + 3）
- [x] 全项目覆盖率 82.61% >= 阶段 3（82%）与门禁 75%
- [x] Cache Protocol + Null/Memory/Redis 三实现
- [x] 缓存 key 规范（scope_signature + analysis_type + insight_id），不使用 KEYS
- [x] 读取缓存前验证数据集存在性
- [x] 缓存值含 schema version 且严格 JSON 序列化
- [x] Insight 原子短锁：token 安全释放、自动 TTL
- [x] 获取锁前按 fingerprint 查询、获得锁后再次查询；命中未过期不调模型
- [x] Redis get/set/delete/lock 异常全部降级，不返回 500
- [x] Redis 关闭时允许重复模型调用，但 PostgreSQL 唯一约束保证最终单条 Insight
- [x] 锁持有者异常后可由 TTL 恢复
- [x] 双 Adapter Mock 46/46 回归保持

## Git 提交

- CP4 阶段提交：见下方（阶段 4 提交消息）

## 下一阶段输入条件

- 阶段 5 可开始。依赖：CP4 通过、Redis 缓存与短锁稳定、删除/过期流程稳定。
- 阶段 5 目标：GitHub Actions 完善（PostgreSQL/Redis 集成、迁移、Compose 冒烟）、API/Streamlit Dockerfile 与 Compose、结构化 JSON 日志、10,000 行合成夹具、性能脚本、故障演练、备份恢复演练。
