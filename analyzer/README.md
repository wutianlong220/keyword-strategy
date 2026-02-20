# 关键词分析系统

自动化分析 Google Trends CSV 数据，识别高价值关键词主题，帮助你发现网站商机。

## 功能特点

- ✅ **AI 智能聚类**: 使用智谱GLM AI 深度理解关键词语义，自动识别主题
- ✅ **商业洞察**: 自动分析搜索意图、网站类型、变现方式
- ✅ **趋势追踪**: 自动对比历史数据，识别新兴趋势和持续热点
- ✅ **并行处理**: 支持并发分析，快速处理大批量数据
- ✅ **完全自动化**: 一键运行，从 CSV 到完整报告
- ✅ **中文报告**: 全中文商业分析和建议

## 快速开始

### 1. 安装依赖

```bash
cd analyzer
pip3 install -r requirements.txt
```

### 2. 设置智谱GLM API Key

你需要一个智谱GLM API Key。

**获取 API Key:**
1. 访问: https://open.bigmodel.cn/usercenter/apikeys
2. 注册/登录
3. 创建 API Key

**方式 A: 使用 .env 文件（推荐，最简单）**
```bash
# 1. 复制示例文件
cp .env.example .env

# 2. 编辑 .env 文件
nano .env

# 3. 填入你的 API Key
ZHIPU_API_KEY=你的API-Key

# 4. 保存（Ctrl+X，然后 Y，然后 Enter）
```

**方式 B: 使用环境变量（临时）**
```bash
export ZHIPU_API_KEY="your-api-key-here"
```

**方式 C: 永久设置（写入 shell 配置）**
```bash
# 编辑配置文件
nano ~/.zshrc  # 或 nano ~/.bashrc

# 添加以下行
export ZHIPU_API_KEY="your-api-key-here"

# 保存后执行
source ~/.zshrc  # 或 source ~/.bashrc
```

### 3. 放置 CSV 文件

将你的 Google Trends CSV 文件放到 `search-for-Google-keywords/` 目录下。

**文件命名格式**: `daily_report_YYYYMMDD.csv`
- 例如: `daily_report_20260220.csv`

### 4. 运行分析

```bash
cd analyzer
python analyze.py
```

### 5. 查看报告

分析完成后，查看生成的报告：

```bash
# Markdown 报告（人类可读）
open ../analysis/report_20260220.md

# JSON 数据（程序可读）
cat ../data/themes_recent/themes_20260220.json
```

## 目录结构

```
keyword-strategy/
├── search-for-Google-keywords/     # 👈 放置你的 CSV 文件
│   └── daily_report_*.csv
│
├── analyzer/                       # 分析脚本
│   ├── analyze.py                 # 主脚本
│   ├── config.yaml                # 配置文件
│   ├── requirements.txt           # 依赖
│   └── README.md                  # 本文档
│
├── analysis/                       # 📄 分析报告（永久保留）
│   └── report_*.md
│
└── data/                           # 数据存储
    ├── themes_recent/              # 最近7天详细数据
    ├── themes_summary/             # 月度汇总（永久）
    └── decisions/                  # 决策记录（永久）
```

## 工作流程

```
你做:
1. 每天把新 CSV 放到 search-for-Google-keywords/
2. 运行: python analyze.py
3. 查看报告

脚本自动:
1. ✅ 找到最新 CSV
2. ✅ 过滤关键词
3. ✅ 调用 AI 进行聚类分析
4. ✅ 识别主题、细分、商业机会
5. ✅ 对比历史数据
6. ✅ 生成完整报告
7. ✅ 清理过期数据
```

## 配置说明

编辑 `analyzer/config.yaml` 可以调整：

### 评分权重
```yaml
scoring:
  weights:
    rising: 0.7   # 飙升趋势权重
    top: 0.3      # 热门需求权重
```

### 过滤规则
```yaml
filters:
  min_value_rising: 100    # rising 最小增长率
  min_value_top: 20        # top 最小相关度
```

### 并发设置
```yaml
concurrency:
  max_parallel: 3  # 并发数
  batch_size: 500  # 每批处理数量
```

## 报告示例

生成的 Markdown 报告包含：

### 📈 趋势对比
- 新出现主题
- 持续热门主题
- 消失主题

### 📊 主题完整列表
每个主题包含：
- 📊 主题名称（中英文）
- 🎯 得分（0-100）
- 📈 关键词数量和增长率
- 🎯 搜索意图分析
- 💡 适合的网站类型
- 💰 变现方式建议
- 📂 细分领域机会
- 🔥 具体关键词列表

## 成本估算

基于智谱GLM API 定价（glm-4-flash）：
- 每天约 3000 个关键词
- 每月成本约 **几元人民币**（非常便宜！）
- 智谱GLM比Claude更省钱

## 模型选择

编辑 `config.yaml` 可以选择不同模型：

```yaml
api:
  model: glm-4-flash  # 快速便宜，推荐！
  # model: glm-4-plus  # 更强大
  # model: glm-5  # 最新旗舰
```

## 数据保留策略

| 数据类型 | 位置 | 保留时间 |
|---------|------|---------|
| 原始 CSV | search-for-Google-keywords/ | 永久 |
| 详细分析 | data/themes_recent/ | 7 天 |
| 月度汇总 | data/themes_summary/ | 永久 |
| 决策记录 | data/decisions/ | 永久 |
| 分析报告 | analysis/ | 永久 |

## 常见问题

### Q: 如何获取智谱GLM API Key？
A: 访问 https://open.bigmodel.cn/usercenter/apikeys 注册并创建 API Key

### Q: 提示 "未设置 ZHIPU_API_KEY"
A: 创建 `.env` 文件并填入 API Key：
```bash
cp .env.example .env
nano .env  # 填入你的 API Key
```

### Q: 第一次运行没有历史数据怎么办？
A: 没问题！第一次运行会生成初始报告，从第二天开始会显示趋势对比

### Q: CSV 文件格式有什么要求？
A: 必须包含 4 列：`keyword,related_keywords,value,type`

### Q: 可以调整聚类算法吗？
A: 聚类由 AI 完成，你可以通过修改 `config.yaml` 中的 prompt 参数来调整

### Q: 如何只分析特定类型的关键词？
A: 修改 `config.yaml` 中的 `filters` 配置

## 未来功能

- [ ] 月度自动汇总
- [ ] 决策记录功能
- [ ] Web Dashboard
- [ ] 邮件通知

## 技术支持

如有问题，请检查：
1. API Key 是否正确设置
2. CSV 文件格式是否正确
3. 依赖是否完整安装

---

**祝你的关键词分析顺利！🚀**
