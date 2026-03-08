# Keyword Workflow v5（High-Value SERP Draft）

> 目标：在 v4（纯 Prompt、无搜索）与 v3（全量 SERP）之间找到最佳平衡点。
> 核心原则：**Stage 1 分类并筛出高价值词 → Stage 2 仅对高价值词执行 SERP + 商业化（合并为一步）→ 其余词直接输出。**
> 约束：**不用 Python 写复杂逻辑，核心判断全部基于 Prompt + 搜索结果执行。**

---

## 0) 总体流程

```text
输入 CSV 关键词（only related_keywords）
   ↓
Stage 1: 意图分类 + 商业初判 + 高价值标记（TRASH / SEED / PROJECT，同时输出 priority）
   ↓
┌──────────────────────────────────────────────────┐
│  priority = HIGH_VALUE（PROJECT + conf ≥ 70）    │
│      ↓                                           │
│  Stage 2: SERP 验证 + 商业路线（合并单步）       │
└──────────────────────────────────────────────────┘
   ↓                         ↓
HIGH_VALUE 词               其余词
（带 serp_fit + route）     （无 SERP，直接输出）
   ↓                         ↓
         合并输出：最终宽表 JSON
```

**Token 节省逻辑：**
- TRASH / SEED → 跳过 Stage 2（节省 100% SERP Token）
- PROJECT + conf < 70 → 跳过 Stage 2（节省部分 SERP Token，同时标注 `NEED_REVIEW`）
- 只有 PROJECT + conf ≥ 70 → 进入 Stage 2（SERP + 商业化一次性完成）

---

## 1) Stage 1：意图分类与高价值标记

### 目标
批量分类关键词，同时在 Stage 1 内部直接判定是否进入 Stage 2（标记 `priority`），取消单独路由步骤。

### 输入格式
- `词根|相关词|数值|类型`
- **只对第二列 related_keywords 判断**

### Stage 1 Prompt（固定模板）

```text
你是关键词意图分类专家与商业分析师。请分析并分类以下搜索关键词。

数据格式: 词根|相关词|数值|类型
**重要**：务必聚焦「相关词」（第二列）进行判断，这是网民真实搜索的内容。

数据:
{keywords_text}

---

## 分类与评分标准

### 第一步：判断是否为 TRASH (噪音类)
- 纯大品牌词（Amazon Login, Facebook App Download）
- 纯导航词（Sign up, App download, Customer service）
- 无任何中小开发者商业转化潜力
→ 归为 TRASH，结束判断（置信度拉高）

### 第二步：判断搜索意图 (核心)
问自己：**我能直接猜出用户想干什么吗？**
- **意图明确 → PROJECT（项目类）**
  - 用户想找具体答案/产品/服务
  - 可以立刻做出页面内容
- **意图模糊 → SEED（种子类）**
  - 不知道用户具体想要什么
  - 概念太宽泛，需要更多信息才能判断

### 第三步：用词组长度快速验证（辅助标准）
- **≤ 2个单词** → 倾向于 SEED
- **≥ 3个单词** → 倾向于 PROJECT
- **≥ 5个单词** → 几乎肯定是 PROJECT

---

### 【PROJECT - 项目类】✅
**搜索意图明确**（核心特征）：
- 能直接猜出用户想干什么
- 可以立刻想象出页面标题和内容

**词组结构**（快速判断）：
- 通常 ≥ 3个单词
- 包含修饰语、限定词、动词
- 包含疑问词（what, how, where, who, when）

**典型例子**：
- ✅ "what is a property tax" → 意图明确（想了解房产税）
- ✅ "ai image generator from text" → 意图明确（想找AI图片生成工具）
- ✅ "best running shoes for flat feet 2025" → 意图明确（想找推荐）
- ✅ "how to remove background from image" → 意图明确（想学方法）
- ✅ "resident evil requiem voice actors" → 意图明确（想找游戏信息）
- ✅ "cult leader simulator" → 意图明确（想找具体游戏）

---

### 【SEED - 种子类】🌱
**搜索意图模糊**（核心特征）：
- 无法直接猜出用户想干什么
- 概念太宽泛，可能是多种意图

**词组结构**（快速判断）：
- 通常 ≤ 2个单词
- 概念性词汇（行业、产品类别）
- 没有具体限定词

**典型例子**：
- ✅ "ai" → 意图模糊（想学？想用？想了解？）
- ✅ "crm" → 意图模糊（想买？想对比？想学习？）
- ✅ "blockchain" → 意图模糊（概念太宽泛）
- ✅ "python" → 意图模糊（想学？想找库？想找工作？）

---

### 【TRASH - 噪音类】🗑️
- 大品牌词（Amazon Login, Facebook App Download）
- 纯导航词（Sign up, App download）
- 无商业转化潜力

---

### 判断示例（按决策流程综合参考）

| 关键词 | 词数 | 搜索意图 | 分类 | 理由 |
|--------|------|----------|------|------|
| `what is a property tax` | 5个 | 明确（想了解） | PROJECT | 疑问词，意图清晰 |
| `cult leader simulator` | 3个 | 明确（想找游戏） | PROJECT | 具体产品搜索 |
| `ai` | 1个 | 模糊（太宽泛） | SEED | 概念性，意图不明 |
| `amazon login` | 2个 | 导航词 | TRASH | 品牌导航词 |

---

### 第四步：生成商业初判字段（重要附加要求）
对于每一个词，在分类的同时，你必须同时输出以下字段：
- **trend_label**：基于输入数值和类型判断趋势（如：爆发/强上升/稳健/冷门）
- **user_need**：一句话推测用户隐藏的终极需求
- **hypothesis**：这个词在什么假设场景下值得做网站或数字产品？
- **confidence_score (0-100)**：你对上述分类和商业推测的自信程度。意图越明确越有商业价值，分数应越高；如果是你看不懂的词或乱码，分数应极低。
- **eli5_explanation**：(Explain Like I'm 5) 试着给 5 岁小孩解释人们为什么搜这个词（tell me as I am 5, explain why they search this）。特别是遇到非常规的小众词汇或品牌词汇时，必须用这句口吻解释得极其通俗易懂！

### 第五步：标记 priority（v5 新增，Stage 2 分流核心）
根据分类结果与置信度，自动打上 priority 标签：

| 条件                                         | priority      | 后续行动         |
|----------------------------------------------|---------------|------------------|
| PROJECT 且 confidence_score ≥ 70             | HIGH_VALUE    | 进入 Stage 2     |
| PROJECT 且 50 ≤ confidence_score < 70        | NORMAL        | 跳过 Stage 2     |
| 任何类别且 confidence_score < 50             | NEED_REVIEW   | 跳过 Stage 2     |
| SEED 且 confidence_score ≥ 70                | SEED_POOL     | 跳过 Stage 2     |
| TRASH 且 confidence_score ≥ 70               | DISCARD       | 跳过 Stage 2     |

---

输出JSON格式（不要其他文字）:
{{
  "stage1_results": [
    {{
      "keyword": "ai image generator from text",
      "category": "PROJECT",
      "reason": "意图极其明确，寻找具体的AI文本生图工具",
      "confidence_score": 95,
      "user_need": "需要一个好用的、可能免费的AI绘图工具完成工作或娱乐",
      "trend_label": "强上升",
      "hypothesis": "如果是做垂直类的聚合导航站或细分套壳工具，极具流量和付费价值",
      "eli5_explanation": "就像小孩想要魔法棒一样，大人们想要一个只要输入几个字，就能像变魔术一样生出美丽图画的神奇工具！",
      "priority": "HIGH_VALUE"
    }},
    {{
      "keyword": "ai",
      "category": "SEED",
      "reason": "概念性搜索，意图极度模糊",
      "confidence_score": 90,
      "user_need": "了解AI概念、寻找相关工具或资讯",
      "trend_label": "稳健",
      "hypothesis": "词本身竞争极大无价值，但可作为父节点向下深挖海量长尾工具词",
      "eli5_explanation": "这就好像有人在搜索引擎里只输入了"玩具"两个字，他们可能是想买玩具，但也可能是想查查玩具有哪些种类，或者单纯看看好玩的玩具图片。",
      "priority": "SEED_POOL"
    }},
    {{
      "keyword": "amazon login",
      "category": "TRASH",
      "reason": "纯品牌导航词",
      "confidence_score": 99,
      "user_need": "登录亚马逊账号",
      "trend_label": "稳健",
      "hypothesis": "毫无中小开发者切入机会与商业价值",
      "eli5_explanation": "大人们只是忘了怎么进入一个叫'亚马逊'的超级大商场，所以他们在网上搜'商场的大门在哪儿'，想进去买东西罢了。",
      "priority": "DISCARD"
    }}
  ]
}}
```

---

## 2) Stage 2：SERP 验证 + 商业路线（合并单步，仅 HIGH_VALUE 触发）

### 触发条件（硬性死闸）
**仅当 `priority = HIGH_VALUE` 时执行。其余词（NORMAL / NEED_REVIEW / SEED_POOL / DISCARD）严格跳过，直接进入最终输出。**

### 搜索调优路由
1. **主引擎**：`multi-search-engine`（获取 SERP 前 5 条标题与摘要）
2. **Fallback 1**：主引擎失败 → `ollama_web_search` 补充
3. **Fallback 2**：均失败 → `web_fetch` 抓取前两个网页正文

### Stage 2 Prompt（固定模板）

```text
你是搜索意图校验员与商业化策略分析师。给定一个高价值关键词与其真实 SERP 结果，完成以下两项任务（合并为一次判断）：

输入：
- keyword: {related_keyword}
- stage1_context: {stage1 中的 user_need + reason + trend_label}
- serp_snippets: [title_and_snippet_1, title_and_snippet_2, ...]

---

## 任务一：SERP 验证（赛道匹配）

1. 先在 "meaning" 字段用一句话解释这个词的实际含义
   - 常规词可留空
   - 新闻事件/特定机构/模糊组合词 → 必须基于 SERP 解读
2. 判断 serp_fit：该词与目标赛道（AI工具、自动化软件、数字产品等）的匹配度
   - HIGH：大部分结果明确属于目标赛道
   - MEDIUM：混合意图，存在歧义
   - LOW：大部分不相关（影视、考试、新闻、纯金融等）

## 任务二：商业路线定级（仅当 serp_fit 为 HIGH 或 MEDIUM 时填写）

判断该词最适宜的变现路线：
- DIGITAL_PRODUCT：信息差变现（电子书/课程/Prompt模版/咨询）
- WEBSITE：流量变现（工具站/导航站/评测博客/SaaS）
- BOTH：均可
- UNSURE：难以判断

约束：
- serp_fit = LOW 时，route 固定填 NO_RECOMMENDATION，offer_examples 填 []
- 不要重判赛道相关性以外的问题（Stage 1 已决定）

---

输出JSON格式（不要其他文字）：
{{
  "meaning": "（按需）该词实际含义，常规词留空",
  "serp_fit": "HIGH|MEDIUM|LOW",
  "serp_reason": "赛道匹配判断的核心理由",
  "serp_evidence": ["支持该判断的关键 SERP 标题或摘要片段"],
  "route": "DIGITAL_PRODUCT|WEBSITE|BOTH|UNSURE|NO_RECOMMENDATION",
  "route_reason": "选择该路线的核心逻辑",
  "offer_examples": ["具体产品/页面建议1", "具体产品/页面建议2"]
}}
```

---

## 3) 数据处理与输出规则

### 字段合并逻辑
将 Stage 1 与 Stage 2（若执行）的字段在内存中平铺合并，一次性生成最终宽表。

**对于跳过 Stage 2 的词，字段填充默认值：**

| 字段           | 默认值                     |
|----------------|---------------------------|
| meaning        | `null`                    |
| serp_fit       | `SKIPPED`                 |
| serp_reason    | `null`                    |
| serp_evidence  | `[]`                      |
| route          | `NO_RECOMMENDATION`       |
| route_reason   | `null`                    |
| offer_examples | `[]`                      |

### QA 打标规则
- `confidence_score < 50` → `qa_status: NEED_REVIEW`
- 其余 → `qa_status: PASSED`

### KD 查询（外部 OpenClaw 处理）
- 仅对 `serp_fit = HIGH 或 MEDIUM` 的词查询 KD（即真正通过验证的高价值词）
- 入口：`https://ahrefs.com/keyword-difficulty`
- 字段：`kd`（数值或 null）、`kd_status`（`OK_RELAY | NO_DATA_RELAY | PENDING_OPENCLAW`）

---

## 4) 最终输出结构

### 存储规则
每批次只产生 **1 个文件**，不产生任何中间文件：
- `final_results_batch_XX.json`：所有字段平铺的数据大盘

所有 Stage 中间结果（Stage 1 原始 JSON、Stage 2 原始回复、搜索引擎返回摘要）均**只在内存中流转**，批次完成后直接丢弃，不落盘。

### 最终宽表示例

| keyword_root | related | class | priority | conf_score | user_need | hypothesis | eli5 | trend | serp_fit | route | offer_examples | qa_status | kd | kd_status |
|---|---|---|---|---:|---|---|---|---|---|---|---|---|---:|---|
| action | ecuador military action | TRASH | DISCARD | 15 | 追地缘热点 | 无商业价值 | 大人们看别国打仗的新闻 | 稳健 | SKIPPED | NO_REC | [] | NEED_REVIEW | null | — |
| ai | ai image generator | PROJECT | HIGH_VALUE | 95 | 找AI生图工具 | 做垂直聚合导航站或套壳工具 | 想要魔法棒变出漂亮图 | 强上升 | HIGH | WEBSITE | [生成器套壳站] | PASSED | null | PENDING_OPENCLAW |
| ai | ai writing | PROJECT | NORMAL | 62 | 找AI写作工具 | 可做写作辅助工具站 | 想让电脑帮我写字 | 上升 | SKIPPED | NO_REC | [] | PASSED | null | — |

---

## 5) 耗时记录

每批次必须输出：
- `stage1_duration_sec`
- `stage2_duration_sec`（仅统计真正执行了 SERP 的词）
- `stage2_skipped_count`（跳过 Stage 2 的词数量）
- `total_duration_sec`

```json
"timing_breakdown": {
  "stage1_sec": 12.3,
  "stage2_sec": 18.7,
  "stage2_skipped_count": 43,
  "stage2_executed_count": 17,
  "total_sec": 31.0
}
```

---

## 6) v5 vs 历史版本对比

| 维度             | v3（全量 SERP）     | v4（无 SERP）       | v5（精准 SERP）          |
|-----------------|---------------------|---------------------|--------------------------|
| SERP 覆盖范围   | 所有 PROJECT 词     | 无                  | 仅 HIGH_VALUE（conf≥70） |
| Stage 数量      | 3（分开执行）       | 1                   | 2（Stage2 合并）         |
| Token 消耗      | 高                  | 最低                | 中（精准触发）           |
| 商业路线准确性  | 高（有 SERP 验证）  | 中（纯 AI 推断）    | 高（高价值词有验证）     |
| 误判风险        | 低                  | 中（无验证）        | 低（高价值词都验过）     |
| 碎词 SERP 浪费  | 有                  | 无                  | 无（低质词直接跳过）     |
