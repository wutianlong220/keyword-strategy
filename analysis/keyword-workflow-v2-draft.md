# Keyword Workflow v2（Prompt-Only Draft）

> 目标：避免“词面像 AI、实际无关”的误判。  
> 核心原则：**先分类（意图）→ 再搜索验证（语义）→ 最后商业化判断（变现）**。  
> 约束：**本流程不用 Python 脚本，全部基于 Prompt + 搜索结果执行**。

---

## 0) 总体流程（3阶段）

```text
输入 CSV 关键词（只看 related_keywords）
   ↓
Stage 1: 分类（TRASH / SEED / PROJECT）
   ↓
Stage 2: SERP/搜索验证（是否匹配目标赛道）
   ↓
Stage 3: 仅对通过词做变现路线判断（网站 / 数字产品）
   ↓
输出：执行池 + 复核池 + 剔除池
```

---

## 1) Stage 1：关键词分类（只做意图，不做商业化）

### 输入格式
- `词根|相关词|数值|类型`
- rising：数值是增长率%；top：数值是相关度（0-100）
- **只对第二列 related_keywords 判断**

### Stage 1 Prompt（固定模板）

```text
你是关键词分类专家。将以下搜索关键词分为三类。

数据格式: 词根|相关词|数值|类型
- rising类型: 数值是增长率百分比
- top类型: 数值是相关度分数(0-100)

**重要**：请对「相关词」（第二列）进行分类判断，相关词才是用户实际搜索的内容。

数据:
{keywords_text}

---

## 分类标准（按优先级判断）

### 判断流程：从高优先级到低优先级

**第一步：判断是否为 TRASH**
- 大品牌词（Amazon Login, Facebook App）
- 纯导航词（Sign up, Download）
- 无商业价值
→ 归为 TRASH，结束判断

**第二步：判断搜索意图（核心标准）**
问自己：**我能直接猜出用户想干什么吗？**

- **意图明确** → PROJECT
  - 用户想找具体答案/产品/服务
  - 可以立刻做出页面内容

- **意图模糊** → SEED
  - 不知道用户具体想要什么
  - 需要更多信息才能判断

**第三步：用词组长度快速验证（辅助标准）**
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
```
✅ "what is a property tax" → 意图明确（想了解房产税）
✅ "ai image generator from text" → 意图明确（想找AI图片生成工具）
✅ "best running shoes for flat feet 2025" → 意图明确（想找推荐）
✅ "how to remove background from image" → 意图明确（想学方法）
✅ "resident evil requiem voice actors" → 意图明确（想找游戏信息）
✅ "cult leader simulator" → 意图明确（想找具体游戏）
```

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
```
✅ "ai" → 意图模糊（想学？想用？想了解？）
✅ "crm" → 意图模糊（想买？想对比？想学习？）
✅ "blockchain" → 意图模糊（概念太宽泛）
✅ "python" → 意图模糊（想学？想找库？想找工作？）
```

---

### 【TRASH - 噪音类】🗑️

- 大品牌词（Amazon Login, Facebook App Download）
- 纯导航词（Sign up, App download）
- 无商业转化潜力

---

## 判断示例（按决策流程）

| 关键词 | 词数 | 搜索意图 | 分类 | 理由 |
|--------|------|----------|------|------|
| `what is a property tax` | 5个 | 明确（想了解） | PROJECT | 疑问词，意图清晰 |
| `cult leader simulator` | 3个 | 明确（想找游戏） | PROJECT | 具体产品搜索 |
| `resident evil voice actors` | 4个 | 明确（想找信息） | PROJECT | 长尾词，意图明确 |
| `ai` | 1个 | 模糊（太宽泛） | SEED | 概念性，意图不明 |
| `blockchain` | 1个 | 模糊（太宽泛） | SEED | 概念性，意图不明 |
| `python` | 1个 | 模糊（太宽泛） | SEED | 概念性，意图不明 |
| `crm` | 1个 | 模糊（太宽泛） | SEED | 产品类别，意图不明 |
| `amazon login` | 2个 | 导航词 | TRASH | 品牌导航词 |

---

## 输出格式

输出JSON格式(不要其他文字):
{{
  "classification": [
    {{"keyword": "wordle answer feb 27", "category": "PROJECT", "reason": "意图明确，寻找具体答案"}},
    {{"keyword": "ai", "category": "SEED", "reason": "概念性搜索，意图不清晰"}},
    {{"keyword": "resident evil voice actors", "category": "PROJECT", "reason": "长尾词（4个词），意图明确"}}
  ]
}}

只输出JSON，无其他文字。
```

### 输出字段
- `stage1.category`：`TRASH | SEED | PROJECT`
- `stage1.reason`
- `stage1.confidence_score`：`0-100`
- `stage1.user_need`：一句话用户需求
- `stage1.trend_label`：`爆发/强上升/中上升/弱上升`
- `stage1.hypothesis`：在何种假设下值得做/不做

### Stage 1 分流规则（含 confidence_score）

> 不建议“仅低于50才进第二阶段”。更稳妥规则如下：

1. `class=PROJECT` → **强制进入 Stage 2**（无论分数高低）
2. `confidence_score < 50`（任何 class）→ 进入 Stage 2 + `REVIEW`
3. `class=SEED 且 confidence_score >= 70` → 进入观察池（可抽样进 Stage 2）
4. `class=TRASH 且 confidence_score >= 70` → 直接剔除（可不进 Stage 2）

### Stage 1 结果表（建议格式）

| # | keyword_root | related_keywords | value | type | class | confidence_score | 是否立项 | 趋势 | 用户需求 | 理由 | 假设 |
|---|---|---|---:|---|---|---:|---|---|---|---|---|
| 1 | action | ecuador military action | 6000 | rising | TRASH | 15 | NO | 强上升 | 追热点/娱乐消费，非可持续问题求解 | 时效或娱乐导向，商业转化弱 | 仅在做流量站+广告套利且更新极快时可短期尝试，不建议独立开发者 |

---

## 2) Stage 2：SERP/搜索验证（关键防误判层）

### 目标
校验 Stage 1 的 PROJECT/SEED 是否真的属于目标业务赛道（如 AI 工具/自动化）。

### 工具（非 Python）
- 默认：`multi-search-engine`（主搜索入口）
- fallback 2：`ollama_web_search`（快速补充）
- fallback 3：`web_fetch`（抓取结果页正文证据）

### Stage 2 Prompt（固定模板）

```text
你是搜索意图校验员。给定一个关键词和其 SERP 前5条标题，判断该词是否属于“AI工具/自动化”赛道。

输入：
- keyword: {related_keyword}
- serp_titles: [title1, title2, ...]

输出 JSON：
{
  "serp_fit": "HIGH|MEDIUM|LOW",
  "reason": "一句话解释",
  "evidence": ["证据1", "证据2"]
}

判定规则：
- HIGH：结果大部分明确是 AI 工具/自动化
- MEDIUM：混合意图，存在冲突
- LOW：大部分不相关（影视、考试、职位、节日、地缘新闻等）
```

### 输出字段
- `stage2.serp_fit`：`HIGH | MEDIUM | LOW`
- `stage2.reason`
- `stage2.evidence`
- `stage2.serp_titles`

---

## 3) Stage 3：商业化判断（只对通过词执行）

### 触发条件
仅当：
- `stage1.category == PROJECT`
- `stage2.serp_fit in [HIGH, MEDIUM]`

### Stage 3 Prompt（固定模板）

```text
你是商业化策略分析师。仅基于“已验证相关赛道”的关键词，判断最合适的变现路线。

输入：
- keyword: {related_keyword}
- stage2: {serp_fit + evidence}

输出 JSON：
{
  "route": "DIGITAL_PRODUCT|WEBSITE|BOTH|UNSURE",
  "reason": "一句话",
  "offer_examples": ["可卖产品1", "可做页面2"]
}

约束：
- 不要重判相关性（相关性已在 Stage2 决定）
- 不相关词（LOW）禁止进入本阶段
```

### 路线定义
- `DIGITAL_PRODUCT`：电子书 / Prompt / 课程 / 咨询
- `WEBSITE`：工具站 / 内容站 / 咨询站（游戏站可选）
- `BOTH`
- `UNSURE`

---

## 4) 词义解释层（新增：解释模糊词，如“schwab ecuador”）

> 目的：对不熟悉或新词，先解释“它是什么”，再决定是否值得做。

### 触发条件
- 人工看不懂的词
- 新词 / 地域词 / 人名组合词
- Stage2 证据冲突（MEDIUM）

### Explain Prompt（固定模板）

```text
你是关键词释义助手。请解释这个词在搜索语境下通常指什么，并给出是否与我的业务（AI工具/数字产品）相关。

输入：
- keyword: {term}
- serp_titles: [title1, title2, ...]

输出 JSON：
{
  "meaning": "该词最可能含义",
  "context": "常见搜索场景",
  "business_relevance": "HIGH|MEDIUM|LOW",
  "decision_hint": "保留/观察/剔除",
  "reason": "一句话理由"
}
```

### 示例（用于你提到的词）
- `schwab ecuador`：大概率是品牌/机构+地域的事件或新闻语境；通常不属于 AI 工具赛道，优先走解释后剔除或观察。

---

## 5) 搜索路由策略（固定）

1. 默认先用 `multi-search-engine` 获取 SERP 标题与摘要。  
2. 若主搜索失败或结果不可用，则按顺序 fallback：  
   - fallback 1: `ollama_web_search`  
   - fallback 2: `web_fetch`（抓正文证据）
3. **只有在前一步失败/不足时才进入下一步**（不是并行全跑）。
4. 每个关键词必须记录：
   - `search_source`（最终采用的数据源）
   - `fallback_used`（是否触发回退）
   - `fallback_chain`（如 `multi-search-engine -> ollama_web_search`）

---

## 6) Final merged result（合并 Stage 1-4）

> 最终报告只看这一张表，包含 Stage 1-4 全部结果。

| # | keyword_root | related_keywords | value | type | stage1_class | confidence_score | 是否立项 | 趋势 | 用户需求 | stage1_reason | stage1_hypothesis | search_source | fallback_used | fallback_chain | stage2_serp_fit | stage2_evidence | stage2_reason | stage3_route | stage3_offer_examples | kd_source | kd | kd_status | stage4_meaning | stage4_context | stage4_business_relevance | stage4_decision_hint | stage4_reason |
|---:|---|---|---:|---|---|---:|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---:|---|---|---|---|---|---|
| 1 | action | ecuador military action | 6000 | rising | TRASH | 15 | NO | 强上升 | 追热点/娱乐消费 | 时效或娱乐导向，商业转化弱 | 仅流量站可短期尝试 | ollama_web_search | true | multi-search-engine -> ollama_web_search | LOW | 新闻/地缘结果占主导 | 非AI赛道 | - | - | https://ahrefs.com/keyword-difficulty | 0 | SKIPPED_STAGE3 | 地缘新闻短时热点词 | 新闻事件检索 | LOW | 剔除 | 与目标业务无关 |

### 字段规则
- `stage3_*` 仅在 `stage2_serp_fit in [HIGH, MEDIUM]` 时填写。  
- `kd*` 仅在 Stage 3 触发时查询；否则 `kd_status=SKIPPED_STAGE3`。  
- `stage4_*` 用于解释歧义词、品牌词、地域词、人名组合词。

---

## 7) JSON 持久化要求（每批次必须保存）

每次运行都要保存 5 份 JSON（按 batch 范围命名）：

1. `stage1_<range>.json`：仅 Stage1 字段  
2. `stage2_<range>.json`：仅 Stage2 字段（含搜索来源和回退链）  
3. `stage3_<range>.json`：仅 Stage3 字段（含 kd 字段）  
4. `stage4_<range>.json`：仅 Stage4 释义字段  
5. `final_merged_<range>.json`：合并 Stage1-4 的最终结果（主交付）

建议目录：
- `/analysis/experiments/`

命名示例：
- `stage1_81_90_20260308.json`
- `stage2_81_90_20260308.json`
- `stage3_81_90_20260308.json`
- `stage4_81_90_20260308.json`
- `final_merged_81_90_20260308.json`

---

## 8) 质量闸门（发布前必须过）

1. `serp_fit=LOW` 的词，禁止输出 PROJECT 商业建议。  
2. 每批抽样 20 条人工复核。  
3. 若误判率 >10%，该批标记 `FAILED_QA`，不发布。  
4. 低置信度词进入 `REVIEW` 池。

建议字段：
- `qa_status`: `PASSED | FAILED_QA | NEED_REVIEW`
- `review_reason`

---

## 6) 当前共识（与 Wayne 对齐）

- 第一步只做分类，不谈“独立创业者两条赚钱路线”。
- 第二步必须做搜索验证，防止“assistant”等词面误判。
- 第三步才做变现路径（网站/数字产品）。
- 对看不懂词（如 `schwab ecuador`）新增解释层再决策。

---

## 7) 下一步待完善

- [ ] 把 Stage 2 的“目标赛道”做成可配置（AI / 教育 / 金融）
- [ ] `serp_fit` 增加 0-100 分制
- [ ] 固化复核报告模板（包含误判案例）
- [ ] 定义 `REVIEW` 词的二次处理 SLA
