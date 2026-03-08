# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个关键词分析系统，自动分析 Google Trends CSV 数据，使用智谱 GLM AI 进行语义聚类和商业分析。系统识别高价值关键词主题，提供搜索意图、网站类型建议和变现方式分析。

## 目录结构

```
keyword-strategy/
├── search-for-Google-keywords/     # CSV 输入目录（用户放置 Google Trends CSV）
├── analyzer/                       # 分析工具核心
│   ├── analyze.py                 # 主脚本（单文件包含所有逻辑）
│   ├── config.yaml                # 配置文件
│   ├── requirements.txt           # Python 依赖
│   └── run.sh                     # 快速启动脚本
├── analysis/                       # 报告输出（Markdown 格式，永久保留）
└── data/                           # 数据存储
    ├── themes_recent/              # 最近 7 天详细 JSON 数据
    ├── themes_summary/             # 月度汇总
    └── decisions/                  # 决策记录
```

## 常用命令

### 运行分析
```bash
cd analyzer && python3 analyze.py
# 或使用快捷脚本
cd analyzer && ./run.sh
```

### 安装依赖
```bash
pip3 install -r analyzer/requirements.txt
```

### 设置 API Key
```bash
# 方式 1: 使用 .env 文件（推荐）
cp .env.example .env
nano .env  # 填入 ZHIPU_API_KEY

# 方式 2: 环境变量（临时）
export ZHIPU_API_KEY="your-api-key"

# 方式 3: 永久设置（写入 shell 配置）
# 编辑 ~/.zshrc 或 ~/.bashrc，添加:
# export ZHIPU_API_KEY="your-api-key"
```

## 配置说明

编辑 `analyzer/config.yaml` 调整以下关键配置：

- **API 模型**: `api.model` (glm-4.7)
- **并发设置**: `concurrency.max_parallel` (默认 2), `concurrency.batch_size` (默认 200)
- **过滤规则**: `filters.min_value_rising`, `filters.min_value_top`
- **数据保留**: `retention.themes_recent_days` (默认 7 天)
- **评分权重**: `scoring.weights.rising` (0.7), `scoring.weights.top` (0.3)

## 核心架构

### 单文件架构
整个分析逻辑在 `analyzer/analyze.py` 中实现，无需模块化拆分。主要组件：

1. **CSV 处理**: `find_latest_csv()`, `read_csv()`, `filter_keywords()`
2. **AI 分析**: `create_client()`, `call_ai_for_clustering()`, `batch_analyze()`
3. **历史数据**: `load_history_data()`, `cleanup_old_data()`, `get_history_files()`
4. **趋势分析**: `analyze_trends()`
5. **报告生成**: `generate_markdown_report()`, `save_report()`

### 数据流
```
CSV 文件 → 读取关键词 → 过滤 → AI 聚类分析 → 合并去重 → 趋势对比 → 生成报告
```

### AI 聚类处理
- 使用智谱 GLM API (OpenAI 兼容接口)
- 批量并行处理: `batch_analyze()` 分割关键词并使用 `ThreadPoolExecutor` 并发调用
- 内容审核错误处理: `handle_content_filter_error()` 智能分批重试
- Prompt 模板: `create_clustering_prompt()` 定义 AI 分析规则

### CSV 格式要求
必须是 4 列格式：`keyword,related_keywords,value,type`
- `type`: "rising" (飙升趋势) 或 "top" (热门需求)
- `value`: rising 为增长率百分比，top 为相关度分数 (0-100)

## API 端点

使用智谱 GLM 编码套餐专属端点:
```
https://open.bigmodel.cn/api/coding/paas/v4
```

## 数据保留策略

| 数据类型 | 位置 | 保留时间 | 清理方式 |
|---------|------|---------|---------|
| 原始 CSV | search-for-Google-keywords/ | 永久 | 手动管理 |
| 详细 JSON | data/themes_recent/ | 7 天 | `cleanup_old_data()` 自动清理 |
| 月度汇总 | data/themes_summary/ | 永久 | - |
| 分析报告 | analysis/ | 永久 | - |

## 主题评分算法

评分考虑因素 (在 AI prompt 中定义):
- 关键词数量
- rising 类型的平均增长率
- top 类型的平均相关度
- 权重配置: `scoring.weights`

## 重要约束

- **🚨 代码修改原则**: **未经用户明确同意，不得擅自修改任何代码**。即使讨论中提到可能的优化方案，也必须先征得用户确认后再执行。
- **不过滤关键词**: 当前 `filter_keywords()` 保留所有关键词，过滤规则在 config.yaml 中定义但未启用
- **内容审核**: 智谱 GLM 可能触发敏感内容审核 (错误 1301)，系统会自动分批重试
- **最小批次**: 分批重试时最小批次为 20 个关键词
- **Token 限制**: `max_tokens: 128000`, 每批最多 200 个关键词

## 调试技巧

- 被拦截的关键词保存在 `data/rejected_keywords.txt`
- 查看详细 JSON 数据: `data/themes_recent/themes_YYYYMMDD.json`
- 检查配置: `analyzer/config.yaml`
- 检查环境变量: `echo $ZHIPU_API_KEY`

## 翻译功能

代码包含简单中英文翻译字典:
- `translate_keyword_simple()`: 关键词翻译
- `translate_subtheme_simple()`: 细分主题翻译
- 仅覆盖常见词汇，精确匹配优先
