# 阶段 4：前端与用户体验改造

> 周期：第 5–7 周  
> 目标：先把 Streamlit 改造成可维护的 Gate A 前端，再以 Next.js 渐进替换，避免一次性重写阻塞上线。

## 1. 双轨策略

### Gate A：模块化 Streamlit

第 6 周上线前必须完成：

- 拆分单体 `app.py`。
- 登录和会话令牌隔离。
- 上传进度、有效/无效行提示、过期时间和主动删除。
- 筛选器表单提交，避免控件每次变化都重算。
- 评论独立分页加载。
- AI 外部传输会话确认和降级提示。

### Gate B：Next.js 切换

第 8 周目标：

- Next.js + TypeScript 前端覆盖核心工作流。
- 使用服务端会话/BFF 代理隐藏共享 Bearer 令牌。
- OpenAPI 生成类型，避免手写请求/响应字段漂移。
- Playwright 覆盖登录至删除的端到端流程。

若 Gate B 延迟，Gate A 仍是可部署产品，不影响后端上线。

## 2. Streamlit 模块化

建议目录：

```text
frontend/streamlit/
  session.py             # 登录、会话令牌、数据集状态
  api.py                 # 无全局令牌的 HTTP 调用
  pages/
    upload.py
    dashboard.py
    reviews.py
    insights.py
    agent.py
  components/
    filters.py
    metrics.py
    tables.py
    errors.py
  state.py               # 页面状态和失效处理
app.py                   # 仅负责页面装配
```

边界：

- 页面不直接导入 Pandas 分析函数，所有业务数据来自 FastAPI。
- HTTP Client 不使用带 token 的跨会话缓存。
- `dataset_id` 失效、过期或删除后统一清理摘要、分页、insight 和 Agent UI 状态。
- 筛选条件只在点击“应用筛选”后更新已提交状态。

## 3. 页面和交互

### 3.1 登录

- 密码输入默认隐藏字符。
- 登录只验证访问口令，不建设用户账户系统。
- 令牌保存在当前 Streamlit session；刷新/会话结束后重新输入。
- 401 时清空本地业务状态并返回登录页，不展示服务端内部错误。

### 3.2 上传

- 显示支持编码、格式和四项容量限制。
- 上传期间显示状态：读取、解析、预处理、保存、完成。
- 成功后显示 `original_rows`、`valid_rows`、`invalid_rows`、列数和 `expires_at`。
- 格式/容量错误映射为用户可行动的中文说明，并展示 request ID 供排查。

### 3.3 看板

- 指标卡：评论数、平均评分、差评占比、平均情绪、高风险数。
- 图表：评分分布、情绪分布、趋势、问题优先级、关键词。
- 筛选表单：评分、情绪、类别、关键词、高风险；提供应用与重置按钮。
- 已提交筛选在页面上方形成条件摘要，避免用户不清楚当前分析范围。

### 3.4 评论列表

- 使用 `/analytics/reviews/search` 独立分页。
- view：全部、高风险、评分/情绪不一致。
- 每页 20/50/100 条，最大 100；上一页/下一页由 `next_offset` 控制。
- 切换筛选或 view 时 offset 归零。
- 不通过摘要响应加载全部评论。

### 3.5 AI 洞察与 Agent

- 首次调用外部模型前展示传输说明与“本次会话同意”复选框。
- DeepSeek 未配置时保留规则 Agent，明确标记当前模式，不把它当系统错误。
- 展示回答、limitations、routing、工具调用摘要和 warning；默认不展示原始证据 JSON。
- 模型失败时显示“已使用规则分析继续完成”，不丢弃结果。

### 3.6 数据生命周期

- 明确显示到期时间和剩余天数。
- 主动删除需要二次确认，成功后立即清空本地状态。
- 已过期/已删除的 dataset 返回 404 时，统一引导重新上传。

## 4. Next.js 目标架构

建议技术栈：

- Next.js App Router、TypeScript。
- Tailwind CSS 或现有设计系统，不同时引入多个组件库。
- TanStack Query 管理服务端数据、失效和重试。
- Apache ECharts 或 Recharts；优先选择对中文、词云和大数据量支持更好的方案。
- React Hook Form + Zod 管理筛选和表单校验。
- Playwright 端到端测试。

### 4.1 认证设计

浏览器不直接持久化共享 Bearer token：

1. 用户在登录页提交访问口令至 Next.js Server Action/API Route。
2. 服务端验证后创建短时、HttpOnly、Secure、SameSite 会话 Cookie。
3. Next.js BFF 请求 FastAPI 时在服务端注入 Bearer token。
4. Cookie 中不保存明文共享令牌；会话密钥由独立 `WEB_SESSION_SECRET` 提供。

如果暂不实现 BFF，会话令牌最多存内存，严禁 `localStorage`。

### 4.2 路由

```text
/login
/datasets/new
/datasets/[datasetId]/dashboard
/datasets/[datasetId]/reviews
/datasets/[datasetId]/insights
/datasets/[datasetId]/agent
```

### 4.3 类型契约

- CI 从 FastAPI OpenAPI 生成 TypeScript 类型。
- 生成代码单独目录，不手工修改。
- 前端构建前运行契约 diff；破坏性变化必须显式批准。
- 错误处理统一基于 `error.code` 和 `request_id`，不解析中文 message 做逻辑判断。

## 5. 视觉和可用性标准

- 1440px 桌面为主，兼容 1024px；移动端至少可查看关键指标和评论。
- 颜色不能是风险/情绪的唯一表达，必须同时有文字或图标。
- 表格和表单可键盘操作，焦点可见。
- 图表提供标题、单位、空状态、加载状态和错误状态。
- 大数字使用一致精度；比例显示 `%`，情绪指数明确 0–100。
- 不使用无限滚动替代可定位的评论分页。

## 6. 实施任务

| 编号 | 任务 | Gate | 验收 |
| --- | --- | --- | --- |
| P4-001 | 提取 Streamlit session/API 层 | A | token 不进入共享缓存 |
| P4-002 | 拆分上传、看板、评论、AI、Agent 组件 | A | `app.py` 只负责装配 |
| P4-003 | 筛选改表单提交 | A | 控件变化不触发摘要请求 |
| P4-004 | 接入分页和生命周期 UI | A | 分页、过期、删除状态正确 |
| P4-005 | 接入模型传输确认 | A | 未确认不发外部请求 |
| P4-006 | 建立 Next.js 工程和设计 token | B | lint/build 通过 |
| P4-007 | 实现 BFF 会话 | B | token 不在浏览器存储和日志中 |
| P4-008 | 迁移上传、看板、评论 | B | 与 Streamlit 指标一致 |
| P4-009 | 迁移洞察与 Agent | B | limitations/降级正确展示 |
| P4-010 | Playwright E2E | B | 核心旅程可重复通过 |

## 7. 测试

### Streamlit 冒烟

- 登录成功/失败。
- UTF-8 与 GB18030 上传。
- 筛选只在提交后请求。
- 评论分页前后翻页。
- 数据集过期、主动删除和 401 状态清理。
- DeepSeek 未配置、模型失败、规则降级。

### Next.js

- TypeScript、ESLint、组件测试、生产 build。
- Session Cookie 属性和 CSRF 防护。
- OpenAPI 类型兼容。
- Playwright 覆盖：登录 → 上传 → 筛选 → 分页 → AI/规则 Agent → 删除。
- 使用 API mock 测 UI 边界，使用 Compose 跑至少一组真实端到端测试。

## 8. 退出条件

Gate A：

- Streamlit 单体已拆分，核心功能无回归。
- 筛选不会因每个控件变化重复计算。
- 评论分页、有效/无效行、到期和删除体验完整。
- 会话令牌、外部传输确认和 AI 降级满足安全要求。

Gate B：

- Next.js 核心流程与 Streamlit 等价并通过 Playwright。
- token 不落入 `localStorage`、构建产物、日志或前端错误监控。
- 两个前端在灰度期可并行；Next.js 达标后再停止 Streamlit。

## 9. 回退

- Next.js 发布失败时把入口切回 Streamlit，不回滚后端数据库。
- 新图表与旧指标不一致时以后端 API 响应为准，暂停前端切换。
- BFF 会话异常时不允许退回把 token 放 `localStorage`；应切回 Streamlit 或修复会话层。
