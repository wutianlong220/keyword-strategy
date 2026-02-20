# 关键词分析系统 - 快速上手指南

## 🎯 系统已就绪！

你的关键词分析系统已经创建完成。以下是快速上手步骤。

**⚠️ 重要：已配置为使用智谱GLM API**（比Claude更便宜！）

---

## 📋 项目结构

```
keyword-strategy/
├── search-for-Google-keywords/     # 👈 把你的 CSV 放这里
│   └── daily_report_20260220.csv   # 当前已有文件
│
├── analyzer/                       # 分析工具
│   ├── analyze.py                 # 主脚本 ✨
│   ├── config.yaml                # 配置文件
│   ├── run.sh                     # 快速启动
│   ├── requirements.txt           # 依赖包
│   └── README.md                  # 详细文档
│
├── analysis/                       # 📄 报告输出（自动生成）
│
└── data/                           # 💾 数据存储（自动管理）
    ├── themes_recent/              # 最近7天详细数据
    ├── themes_summary/             # 月度汇总
    └── decisions/                  # 决策记录
```

---

## 🚀 使用步骤

### 第一步：设置智谱GLM API Key

你需要一个智谱GLM API Key。

**1. 获取 API Key**
- 访问: https://open.bigmodel.cn/usercenter/apikeys
- 注册并创建 API Key

**2. 设置 API Key（选择一种方式）**

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
export ZHIPU_API_KEY="你的API-Key"
```

**方式 C: 永久设置（写入 shell 配置）**
```bash
# 编辑配置文件
nano ~/.zshrc

# 添加以下行（替换你的 key）
export ZHIPU_API_KEY="你的API-Key"

# 保存后执行
source ~/.zshrc
```

### 第二步：运行分析

你已经有一个 CSV 文件了，可以直接测试：

```bash
cd analyzer
python3 analyze.py
```

或者使用快速启动脚本：
```bash
cd analyzer
./run.sh
```

### 第三步：查看报告

分析完成后，查看生成的报告：

```bash
# 打开 Markdown 报告
open ../analysis/report_20260220.md

# 或用文本编辑器
cat ../analysis/report_20260220.md
```

---

## 📊 报告内容

生成的报告包含：

### 📈 趋势对比
- 新出现主题（首次运行可能没有）
- 持续热门主题
- 消失主题

### 📊 主题完整列表
每个主题包含：
- 🎯 主题名称和得分
- 📈 关键词数量和增长率
- 🎯 搜索意图（交易/信息/导航/商业调查）
- 💻 网站类型建议（工具站/内容站/导航站）
- 💰 变现方式（订阅/AdSense/联盟营销）
- 📂 细分领域和具体关键词

---

## 🔄 日常使用

**每天的工作流程：**

1. **把新的 CSV 放到** `search-for-Google-keywords/`
2. **运行**: `cd analyzer && python3 analyze.py`
3. **查看**: `analysis/report_YYYYMMDD.md`

就这么简单！脚本会自动：
- ✅ 找到最新的 CSV
- ✅ 过滤和聚类分析
- ✅ 对比历史数据
- ✅ 生成完整报告
- ✅ 清理过期数据

---

## ⚙️ 自定义配置

编辑 `analyzer/config.yaml` 可以调整：

- **评分权重** (rising vs top)
- **过滤规则** (最小增长率、相关度)
- **并发设置** (处理速度)
- **数据保留** (历史数据天数)

详细说明见 `analyzer/README.md`

---

## 💰 成本估算

基于智谱GLM API（glm-4-flash）：
- 每天 ~3000 关键词
- 每月成本约 **几元人民币** 🎉
- 比Claude API便宜很多！

---

## 🆘 常见问题

### Q: 提示 "未设置 ZHIPU_API_KEY"
A:
1. 推荐方式：创建 `.env` 文件
   ```bash
   cp .env.example .env
   nano .env  # 填入你的 API Key
   ```

2. 或使用环境变量：
   ```bash
   export ZHIPU_API_KEY="你的API-Key"
   ```

### Q: 智谱GLM API 在哪里获取？
A: https://open.bigmodel.cn/usercenter/apikeys

### Q: CSV 格式不对怎么办？
A: 确保你的 CSV 包含 4 列：`keyword,related_keywords,value,type`

### Q: 第一次运行没有趋势对比？
A: 正常！从第二天开始会有趋势对比

### Q: 想调整聚类规则？
A: 编辑 `analyzer/config.yaml` 中的配置

---

## 📚 更多信息

- 详细文档: [analyzer/README.md](analyzer/README.md)
- 配置说明: [analyzer/config.yaml](analyzer/config.yaml)

---

**准备好了吗？开始你的第一次分析吧！🎉**

```bash
cd analyzer
python3 analyze.py
```
