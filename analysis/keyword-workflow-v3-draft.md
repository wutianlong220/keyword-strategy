# Keyword Workflow v3（Prompt-Only Draft）

> 目标：避免“词面像 AI、实际无关”的误判。  
> 核心原则：**先分类（意图）→ 再搜索验证与释义（语义）→ 最后商业化判断（变现）**。  
> 约束：**本流程不用 Python 脚本编写复杂逻辑，核心判断全部基于 Prompt + 搜索结果执行。**

---

## 0) 总体流程

```text
输入 CSV 关键词（只看 related_keywords）
   ↓
Stage 1: 基础意图分类与商业初判（TRASH / SEED / PROJECT）
   ↓
Stage 2: SERP/搜索验证与释义（判断赛道相关性，模糊词/生僻词先释义再判断）
   ↓
Stage 3: 商业化路线定级（仅对赛道相关的词，判断网站 / 数字产品路线）
   ↓
输出：最终合并报表（由人工审查与工具测 KD）
```

---

## 1) Stage 1：关键词分类与商业初判（补齐必须字段）

### 目标
确定搜索意图是否明确，并根据常识判断是否值得进入下一步验证。

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

---

输出JSON格式(不要其他文字):
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
      "eli5_explanation": "就像小孩想要魔法棒一样，大人们想要一个只要输入几个字，就能像变魔术一样生出美丽图画的神奇工具！"
    }},
    {{
      "keyword": "ai",
      "category": "SEED",
      "reason": "概念性搜索，意图极度模糊",
      "confidence_score": 90,
      "user_need": "了解AI概念、寻找相关工具或资讯",
      "trend_label": "稳健",
      "hypothesis": "词本身竞争极大无价值，但可作为父节点向下深挖海量长尾工具词",
      "eli5_explanation": "这就好像有人在搜索引擎里只输入了“玩具”两个字，他们可能是想买玩具，但也可能是想查查玩具有哪些种类，或者单纯看看好玩的玩具图片。"
    }},
    {{
      "keyword": "amazon login",
      "category": "TRASH",
      "reason": "纯品牌导航词",
      "confidence_score": 99,
      "user_need": "登录亚马逊账号",
      "trend_label": "稳健",
      "hypothesis": "毫无中小开发者切入机会与商业价值",
      "eli5_explanation": "大人们只是忘了怎么进入一个叫‘亚马逊’的超级大商场，所以他们在网上搜‘商场的大门在哪儿’，想进去买东西罢了。"
    }}
  ]
}}
```

### Stage 1 路由分流规则 (Confidence Score 是核心标尺)

1. `category=PROJECT 且 confidence_score >= 50` → **强制进入 Stage 2**
2. `confidence_score < 50`（任何类别） → 进入 Stage 2 + 标记 `NEED_REVIEW`，很可能是 AI 不认识的词
3. `category=SEED 且 confidence_score >= 70` → 留在种子池（暂不进 Stage 2，输出为待深挖报告）
4. `category=TRASH 且 confidence_score >= 70` → 剔除池（不进 Stage 2）

---

## 2) Stage 2：SERP验证与智能释义 (关键防误判层)

### 目标
通过搜索引擎的真实返回结果（SERP），验证该词是否属于你的**目标业务赛道（如：AI工具/自动化/出海微产品等）**。  
★ **整合了 V2 中的释义层**：为了应对类似 `schwab ecuador` 这种 AI 本身不懂的组合词或时事词，在判断赛道前**先利用 SERP 结果进行释义**。

### 搜索调优路由
1. **主引擎**：`multi-search-engine` (获取 SERP 前 5 条标题与摘要)。
2. **Fallback 1**: 若主引擎失败，调用 `ollama_web_search` 补充。
3. **Fallback 2**: 实在不行用 `web_fetch` 抓取前一两个网页正文测验。

### Stage 2 Prompt（固定模板）

```text
你是搜索意图校验员与词义解释助手。给定一个关键词与其真实 SERP（搜索引擎结果页面）前列的标题摘要，请判断它是否属于目标赛道（AI工具、自动化软件、数字产品等）。

输入：
- keyword: {related_keyword}
- serp_snippets: [title_and_snippet_1, ...]

任务流程：
1. 先利用 SERP 信息，在 "meaning" 字段用一句话解释这个词到底指什么（如果是知名常规词，可留空；如果是新闻事件/特定机构/模糊组合词，务必基于 SERP 解读）。
2. 结合 "meaning"，判断该词与目标赛道的匹配度 (HIGH/MEDIUM/LOW)。

输出 JSON：
{{
  "meaning": "（按需填写）该词在搜索结果中的实际含义，例如某国军事演习新闻或特定金融机构。常规词留空。",
  "serp_fit": "HIGH|MEDIUM|LOW",
  "reason": "判断赛道匹配度的核心理由",
  "evidence": ["支持该判断的关键 SERP 标题或摘要片段"]
}}

判定标准 (serp_fit)：
- HIGH：结果大部分明确属于目标赛道（如推荐AI工具、某自动化软件评测）
- MEDIUM：混合意图，存在歧义
- LOW：大部分不相关（如影视作品、考试真题、职位招聘、地缘新闻、纯金融机构服务等）
```

---

## 3) Stage 3：商业化路线定级 (仅对通过词执行)

### 触发条件（逻辑死闸）
仅当 `stage2.serp_fit == HIGH` 或 `MEDIUM` 时触发。
*(LOW 词汇绝对禁止传入此阶段，节省 Token 并消除 AI 盲目推荐的幻觉)*

### KD 使用说明（新增）
- KD 查询入口：`https://ahrefs.com/keyword-difficulty`
- 执行时机：**仅 Stage3 触发词** 查询 KD
- 推荐方式：优先使用 relay/browser 自动化填词并读取结果弹窗
- 字段规范：
  - `kd`：0-100 数值，拿不到填 `null`
  - `kd_status`：`OK_RELAY | NO_DATA_RELAY | NO_VALUE | SKIPPED_STAGE3`
  - `kd_source`：固定写 Ahrefs URL
- 使用规则（建议）：
  - `kd <= 20`：优先做（低难）
  - `20 < kd <= 40`：可做（中等）
  - `kd > 40`：谨慎（需强内容/外链/品牌）
  - `kd > 70`：通常仅头部站点可打，独立站慎入

### Stage 3 Prompt（固定模板）

```text
你是商业化策略高级分析师。针对已验证属于目标赛道的高价值搜索词，判断其最适宜的变现开发路线。

输入：
- keyword: {related_keyword}
- context: {整合 stage1 分析和 stage2 serp_fit 证据}

输出 JSON：
{{
  "route": "DIGITAL_PRODUCT|WEBSITE|BOTH|UNSURE",
  "reason": "选择该路线的核心逻辑，需结合搜索趋势",
  "offer_examples": ["可以卖的Prompt集合/插件", "可以做的微型工具站/导航站"]
}}

路线定义：
- DIGITAL_PRODUCT：信息差变现（电子书 / 课程 / Prompt模版 / 咨询库）
- WEBSITE：流量与服务变现（工具站 / 导航站 / 评测博客 / 订阅制SaaS）
- BOTH：均可
- UNSURE：难以判断商业模式

约束：
- 不要重判相关性（相关性已在 Stage2 决定）
- 不相关词（LOW）禁止传入本阶段
```

---

## 4) 核心输出大表与数据持久化优化

### Final Merged Result (阶段数据拍平)
将 Stage 1 到 Stage 3 的数据全部合并到一张大宽表中，作为最终可阅读交付物。

| keyword_root | related | class | conf_score | user_need | eli5_explanation | hypothesis | stage2_meaning | serp_fit | stage2_reason | stage3_route | offer_examples | fallback_used | qa_status |
|---|---|---|---:|---|---|---|---|---|---|---|---|---|---|
| action | ecuador military action | TRASH | 15 | 追地缘热点 | 大人们在看别国打仗的新闻 | 短期流量站 | 某国军事演习新闻 | **LOW** | 新闻检索，非AI工具 | *(不执行)* | *(不执行)* | NONE | PASSED |
| ai | ai image text | PROJECT| 95 | 找图工具 | 想用魔法棒变出好看的画 | 做聚合站 | - | **HIGH** | 明确的AI工具需求 | WEBSITE | 生成器套壳站 | ollama | PASSED |

### 关于持久化的优化与纠偏（告别文件屎山与 KD 幻象）
1. **取消细碎落盘**：Stage 1 到 3 的产出结果直接在 Python 内存/JSON 对象中流转并组装，不要在每个小步骤都写入磁盘。
2. **每批次（如 batch_01）只保留 2 个最终文件**：
   - `final_merged_batch_XX.json`：包含上述所有合并字段的数据大盘。
   - `raw_response_batch_XX.txt`：仅保留大模型回复的原始多层 JSON/文本，作为解析崩溃时的“黑匣子”排错使用。
3. **保留并外包 KD 提取**：Keyword Difficulty (KD) 虽然大模型无法直接获取，但在本工作流中将通过 **OpenClaw** 平台使用 Replay 自动化脚本，在 `https://ahrefs.com/keyword-difficulty` 中全自动查询并抓取填补。大模型纯 Prompt 阶段仅预留好 `kd` 字段空白即可。

---

## 5) 阶段耗时记录（新增）

每次跑批必须记录并输出：
- `stage1_duration_sec`
- `stage2_duration_sec`
- `stage3_duration_sec`
- `stage4_duration_sec`
- `total_duration_sec`

并在最终结果里附一段：
`timing_breakdown: {stage1, stage2, stage3, stage4, total}`

## 6) 数据质量与防漏闸门 (QA)

- 每批次自动抽出包含 `qa_status: NEED_REVIEW` 的词供人工一眼复核（主要针对 `confidence_score < 50` 的词）。
- 若在抽检中发现该批次 `serp_fit` 赛道关联误判率 > 10%，则标记该 JSON 批次为 `FAILED_QA`，需微调 Stage 2 Prompt 或增加限定词后重跑。
