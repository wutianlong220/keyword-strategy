# Keyword Workflow v4（Streamlined Draft）

> 目标：打造极致轻量级、低Token消耗的关键词分析流水线。
> 核心原则：**一次 Prompt 解决意图分类与商业初判，取消耗时耗力的在线搜索阶段，直接输出最终 JSON 给人工或外部工具。**
> 约束：**本流程不用 Python 脚本编写复杂逻辑，核心判断全部基于 Prompt 执行。**

---

## 0) 总体流程 (极简 2 阶段)

```text
输入 CSV 关键词（只看 related_keywords）
   ↓
Stage 1: 意图分类、商业初判与释义（TRASH / SEED / PROJECT，同时生成变现路线与解释）
   ↓
输出：最终合并后的 JSON 数据表（直接交付，供最后人工审查与使用 OpenClaw 测 KD）
```

---

## 1) 核心处理层：关键词分类与商业初判

### 目标
通过单次大模型推理，直接完成：判定搜索意图、评估商业转化价值、对生僻词进行通俗解释，并对值得做的词直接给出变现路线。

### 输入格式
- `词根|相关词|数值|类型`
- **只对第二列 related_keywords 判断**

### 核心 Prompt（固定模板）

```text
你是顶级关键词战略分析师与商业导师。请对以下搜索关键词进行深度分类与商业价值评估。

数据格式: 词根|相关词|数值|类型
**重要**：务必聚焦「相关词」（第二列）进行判断，这是网民真实搜索的内容。

数据:
{keywords_text}

---

## 评估标准

### 第一步：判断是否为 TRASH (噪音类)
- 纯大品牌词（Amazon Login, Facebook App Download）
- 纯导航词（Sign up, App download, Customer service）
- 无任何中小开发者商业转化潜力
→ 归为 TRASH！

### 第二步：判断搜索意图 (决定是 PROJECT 还是 SEED)
问自己：**我能直接猜出用户想干什么吗？**
- **意图明确 → PROJECT（项目类）**
  - 用户想找具体答案/产品/服务（例：what is a property tax, ai image generator from text）
  - 可以立刻做出页面内容，通常 ≥ 3个单词，包含动词/限定词/疑问词。
- **意图模糊 → SEED（种子类）**
  - 不知道用户具体想要什么，概念太宽泛（例：ai, crm, blockchain）。
  - 需要更多信息才能判断，通常 ≤ 2个单词。

### 第三步：深度商业分析字段 (对每一个词必须输出)
对于每一个词，在分类的同时，你必须输出以下字段：
1. **reason**: 一句话解释你为什么把它归为这个类别。
2. **user_need**：一句话推测用户隐藏的终极需求。
3. **trend_label**：基于输入数值和类型判断趋势（如：爆发/强上升/稳健/冷门）。
4. **eli5_explanation**：(Explain Like I'm 5) 向 5 岁小孩解释人们为什么搜这个词。遇到小众词或品牌词时，必须用这句口吻解释得通俗易懂！
5. **confidence_score (0-100)**：意图越明确越有商业价值，分数应越高；如果是你看不懂的词或乱码，分数低于 50。
6. **route (变现路线)**: 仅当类别为 PROJECT 且置信度高时填写，否则填 NO_RECOMMENDATION。
   - DIGITAL_PRODUCT：信息差变现（电子书/课程/Prompt/咨询）
   - WEBSITE：流量变现（工具站/导航站/SaaS）
   - BOTH：均可
   - UNSURE：难以判断
7. **offer_examples**: 配合 route 给出的具体产品或网页建议（列表形式）。

---

输出JSON格式(不要其他文字):
{{
  "results": [
    {{
      "keyword": "ai image generator from text",
      "category": "PROJECT",
      "reason": "意图极其明确，寻找具体的AI文本生图工具",
      "user_need": "需要一个好用的、可能免费的AI绘图工具完成工作或娱乐",
      "trend_label": "强上升",
      "eli5_explanation": "就像小孩想要魔法棒一样，大人们想要一个只要输入几个字，就能像变魔术一样生出美丽图画的神奇工具！",
      "confidence_score": 95,
      "route": "WEBSITE",
      "offer_examples": ["垂直AI生图导航站", "基于API的简易版生图工具"]
    }},
    {{
      "keyword": "blockchain",
      "category": "SEED",
      "reason": "概念极大，完全无法判断用户具体需求",
      "user_need": "想了解区块链是什么",
      "trend_label": "稳健",
      "eli5_explanation": "大人们听到大家都在谈论一种叫做'区块链'的神秘账本，好奇它到底是什么，所以就去网上搜这个词。",
      "confidence_score": 85,
      "route": "NO_RECOMMENDATION",
      "offer_examples": []
    }}
  ]
}}
```

---

## 2) 阶段数据处理规则

### 数据整理与打标
大模型返回的 JSON 需要在代码中进行一层极其轻量级的后处理处理（打平字段准备输出）：
- `qa_status`: 
  - 如果 `confidence_score < 50`，打标为 `NEED_REVIEW`。
  - 否则打标为 `PASSED`。
- `kd` & `kd_status`: 初始化为空(`null`) 和 `PENDING_OPENCLAW`。

### KD 使用说明（外部处理）
- KD 查询入口：`https://ahrefs.com/keyword-difficulty`
- 提取方式：Keyword Difficulty (KD) 虽然大模型无法直接获取，但在本工作流中将通过 **OpenClaw** 平台使用 Replay 自动化脚本，在上述网址全自动查询并抓取填补。大模型纯 Prompt 阶段仅预留字段即可。

---

## 3) 最终数据持久化 (核心目标：绝不产生碎文件)

此 V4 版本彻除掉了中间一切繁杂搜索验证，内存流转直接产生最终结果。

### 存储规则：
1. **取消所有中间步骤落盘**：内存组装，一次成型。
2. **每批次（如 batch_01）只保留 2 个最终文件**：
   - `final_results_batch_XX.json`：包含上述所有打平字段的数据大盘。
   - `raw_response_batch_XX.txt`：仅保留大模型回复的原始 JSON 文本，作为解析崩溃时的“黑匣子”排错使用。

### 最终交付大表结构 (JSON -> CSV/Markdown 表格)：

| keyword_root | related | class | conf_score | user_need | eli5_explanation | trend | route | offer_examples | qa_status | kd | kd_status |
|---|---|---|---:|---|---|---|---|---|---|---:|---|
| action | ecuador military action | TRASH | 15 | 追地缘热点 | 大人们在看别国打仗的新闻 | 稳健 | NO_REC | [] | NEED_REVIEW | null | PENDING_OPENCLAW |
| ai | ai image text | PROJECT| 95 | 找图工具 | 想用魔法棒变出好看的画 | 强上升 | WEBSITE | [生成器套壳站] | PASSED | null | PENDING_OPENCLAW |
