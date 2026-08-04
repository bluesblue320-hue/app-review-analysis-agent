# App 评论舆情分析 Agent

一个基于 Python、Streamlit 和中文 NLP 的应用商店评论分析工具。上传 CSV 评论数据后，可以查看评分与情绪健康度、问题分类、关键词、风险评论和趋势，并通过自然语言 Agent 继续提问与下钻分析。

## 核心功能

- 上传 CSV 后自动完成中文分词、情绪评分和问题分类。
- 展示评论数、平均星级、差评占比、平均情绪和高风险评论数。
- 支持按评分、情绪、问题类型、关键词和高风险标签筛选。
- 提供评分分布、情绪分布、关键词对比、趋势和问题优先级分析。
- 可选接入 DeepSeek，生成结构化 AI 洞察与产品建议。
- 内置自然语言分析 Agent，可回答差评聚类、风险评论、版本对比、趋势、产品建议和分析报告等问题。
- Agent 默认分析完整上传数据，也可以主动切换为分析当前看板筛选结果。

## Agent 分析范围

Agent 提供两种分析口径：

- `完整上传数据`：默认选项，结论基于清洗后的全部有效评论。
- `当前筛选结果`：评分、情绪、问题类型、关键词和高风险筛选会同步影响 Agent 结论。

页面会明确显示当前分析范围和样本数。如果当前筛选结果为空，Agent 会阻止执行并提示放宽筛选条件。AI 洞察仅在数据范围一致时复用，避免把局部结论误用为整体结论。

## 技术栈

- Python
- Streamlit
- Pandas
- jieba
- SnowNLP
- scikit-learn
- pyecharts
- DeepSeek API（可选）

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/bluesblue320-hue/app-review-analysis-agent.git
cd app-review-analysis-agent
```

### 2. 创建虚拟环境

Windows PowerShell：

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. 安装依赖

```bash
python -m pip install -r requirements.txt
```

### 4. 启动应用

```bash
streamlit run app.py
```

浏览器通常会自动打开 `http://localhost:8501`。

## 数据格式

上传文件必须是 CSV，并至少包含以下两列：

| 字段 | 必需 | 说明 |
| --- | --- | --- |
| `评分` | 是 | 1～5 星评分 |
| `内容` | 是 | 评论正文 |
| `时间` / `日期` / `评论时间` / `发布时间` | 否 | 用于趋势分析 |
| `版本` | 否 | 用于版本对比 |
| `标题` | 否 | 用于展示评论标题 |

示例：

```csv
时间,评分,版本,标题,内容
2026-07-01,1,9.2.0,无法登录,更新后一直提示登录失败
2026-07-02,5,9.2.0,体验不错,页面流畅而且内容推荐很准确
```

程序会在内存中生成 `分词内容`、`情绪指数`、`问题类型` 和 `风险标签` 等分析字段，不要求上传文件提前包含这些列。

## 配置 DeepSeek AI 洞察（可选）

不配置 API Key 也可以使用本地看板和自然语言 Agent 的统计分析功能。若要生成 DeepSeek AI 洞察，请在项目根目录创建 `.env`：

```env
DEEPSEEK_API_KEY=你的_API_Key
AI_PROVIDER=deepseek
AI_MODEL=deepseek-v4-flash
```

也可以在 Windows PowerShell 当前会话中设置：

```powershell
$env:DEEPSEEK_API_KEY="你的_API_Key"
$env:AI_MODEL="deepseek-v4-flash"
streamlit run app.py
```

`.env` 已加入 `.gitignore`，请勿将真实 API Key 提交到 GitHub。

## 获取示例评论数据

项目包含一个 App Store 评论采集脚本，默认抓取小红书中国区 App Store 最近 5 页评论：

```bash
python spider.py
```

运行后会生成 `xiaohongshu_reviews.csv`。如需采集其他应用，请先修改 `spider.py` 中的 `app_id` 和 `max_pages`。请遵守目标平台的使用条款、访问频率限制及相关法律法规。

## 项目结构

```text
.
├── app.py                 # Streamlit 页面与交互入口
├── agent_workflow.py      # 自然语言 Agent 与分析流程
├── intent_router.py       # 用户问题意图识别
├── ai_analysis.py         # DeepSeek AI 洞察调用与解析
├── visual_analysis.py     # 看板指标、筛选和可视化数据处理
├── nlp_analysis.py        # 离线 NLP 分析脚本
├── spider.py              # App Store 评论采集脚本
├── requirements.txt       # Python 依赖
└── tests/                 # 自动化测试
```

## 运行测试

```bash
python -m pytest -v
```

当前测试覆盖 Agent 意图路由、分析工作流、AI 洞察范围匹配、看板集成、评估框架和可视化数据处理等关键逻辑。

## 使用流程

1. 启动应用并在左侧上传 CSV。
2. 使用侧边栏筛选器查看局部评论表现。
3. 按需生成 DeepSeek AI 洞察。
4. 在自然语言 Agent 区域选择分析范围。
5. 输入问题，例如“差评主要集中在哪些问题？”或“帮我生成一份评论分析报告”。

## Agent 评估

仓库内置可重复运行的 Agent 自动化评估（`evaluation/`），用于量化验证路由、工具选择、参数提取、非法工具拦截、数字可信度和降级能力。默认 Mock 模式不调用真实 DeepSeek，可安全用于本地开发和 CI：

```bash
python -m evaluation.evaluate_agent --mode mock
python -m evaluation.evaluate_agent --mode mock --fail-under
python -m evaluation.evaluate_agent --mode live --output-dir evaluation/reports/live
```

详细说明见 `evaluation/README.md`。

## 数据与安全说明

- 原始 CSV、处理后的 CSV、日志、虚拟环境和 `.env` 默认不会提交到 GitHub。
- 上传数据由当前 Streamlit 进程处理；启用 DeepSeek AI 洞察时，程序会选取部分评论样本发送给配置的 API。
- 在使用真实用户评论前，请自行完成隐私、数据授权与合规评估。
