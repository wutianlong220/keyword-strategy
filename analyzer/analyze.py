#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关键词分析系统 - 主脚本
功能: 自动分析 Google Trends CSV,识别高价值关键词主题
"""

import os
import sys
import json
import glob
import yaml
import csv
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple
from openai import OpenAI  # 使用 OpenAI SDK 连接智谱GLM
from dotenv import load_dotenv  # 加载 .env 文件

# ==================== 配置加载 ====================

def load_config() -> Dict[str, Any]:
    """加载配置文件"""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

# 加载 .env 文件
load_dotenv()

CONFIG = load_config()

# ==================== AI Token 配置 ====================
# 统一的 max_tokens 常量，避免硬编码，便于维护
MAX_TOKENS = 32000  # AI 响应最大 tokens 数（分类、翻译统一使用）

# ==================== 路径配置 ====================

BASE_DIR = Path(__file__).parent.parent
CSV_DIR = BASE_DIR / "search-for-Google-keywords"
ANALYSIS_DIR = BASE_DIR / "analysis"
DATA_DIR = BASE_DIR / "data"
THEMES_RECENT_DIR = DATA_DIR / "themes_recent"
THEMES_SUMMARY_DIR = DATA_DIR / "themes_summary"
DECISIONS_DIR = DATA_DIR / "decisions"

# 确保目录存在
for dir_path in [ANALYSIS_DIR, DATA_DIR, THEMES_RECENT_DIR, THEMES_SUMMARY_DIR, DECISIONS_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# ==================== CSV 处理 ====================

def find_latest_csv() -> Tuple[Path, str]:
    """找到最新的 CSV 文件"""
    csv_files = list(CSV_DIR.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"在 {CSV_DIR} 目录下没有找到 CSV 文件")

    # 按修改时间排序
    latest_csv = max(csv_files, key=lambda f: f.stat().st_mtime)
    date_str = latest_csv.stem.split("_")[-1]

    return latest_csv, date_str

def read_csv(csv_path: Path) -> List[Dict[str, Any]]:
    """读取 CSV 文件"""
    keywords = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                keywords.append({
                    'keyword': row['keyword'].strip(),
                    'related_keywords': row['related_keywords'].strip(),
                    'value': int(row['value']),
                    'type': row['type'].strip()
                })
            except (ValueError, KeyError) as e:
                print(f"⚠️  跳过无效行: {row}, 错误: {e}")
                continue

    print(f"✅ 成功读取 {len(keywords)} 个关键词")
    return keywords

def filter_keywords(keywords: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """根据配置过滤关键词（当前不过滤，保留所有关键词）"""

    # 不做任何过滤，返回所有关键词
    print(f"✅ 保留全部 {len(keywords)} 个关键词（不进行过滤）")
    return keywords

# ==================== 历史数据管理 ====================

def get_history_files() -> List[Path]:
    """获取历史分析文件（最近7天）"""
    files = list(THEMES_RECENT_DIR.glob("themes_*.json"))
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files[:CONFIG['history']['comparison_window']]

def load_history_data(date_str: str) -> List[Dict[str, Any]]:
    """加载历史数据"""
    history_files = get_history_files()
    history_data = []

    for f in history_files:
        # 排除今天的数据
        if date_str in f.name:
            continue

        try:
            with open(f, 'r', encoding='utf-8') as file:
                data = json.load(file)
                history_data.append(data)
        except Exception as e:
            print(f"⚠️  无法读取历史文件 {f}: {e}")

    return history_data

def cleanup_old_data():
    """清理过期的详细数据（保留7天）"""
    retention_days = CONFIG['retention']['themes_recent_days']
    cutoff_date = datetime.now() - timedelta(days=retention_days)

    for f in THEMES_RECENT_DIR.glob("themes_*.json"):
        file_date = datetime.fromtimestamp(f.stat().st_mtime)
        if file_date < cutoff_date:
            f.unlink()
            print(f"🗑️  清理过期数据: {f.name}")

# ==================== AI 分类 ====================

def is_content_filter_error(error_msg: str) -> bool:
    """检查是否是内容审核错误"""
    return "1301" in error_msg or "敏感" in error_msg or "contentFilter" in error_msg

def create_classification_prompt(keywords: List[Dict[str, Any]]) -> str:
    """创建关键词分类的 prompt"""
    # 格式化关键词数据
    keywords_text = "\n".join([
        f"{kw['keyword']}|{kw['related_keywords']}|{kw['value']}|{kw['type']}"
        for kw in keywords[:300]  # 每批最多300个
    ])

    prompt = f"""你是关键词分类专家。将以下搜索关键词分为三类。

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

只输出JSON，无其他文字。"""

    return prompt

def classify_keywords(keywords: List[Dict[str, Any]], client) -> Dict[str, List[Dict[str, Any]]]:
    """AI 分类关键词为 SEED/PROJECT/TRASH（并发处理）"""
    batch_size = 300
    max_parallel = CONFIG['concurrency']['max_parallel']  # 从配置读取并发数

    batches = [keywords[i:i+batch_size] for i in range(0, len(keywords), batch_size)]

    print(f"📊 将分 {len(batches)} 批进行分类（并发数：{max_parallel}）...")

    classified = {
        "SEED": [],
        "PROJECT": [],
        "TRASH": []
    }

    def classify_batch(batch: List[Dict[str, Any]], batch_idx: int, total_batches: int, retry_count: int = 0):
        """处理单个批次"""
        print(f"   正在分类批次 {batch_idx}/{total_batches} ({len(batch)}个关键词)...")

        prompt = create_classification_prompt(batch)

        try:
            response = client.chat.completions.create(
                model=CONFIG['api']['model'],
                max_tokens=MAX_TOKENS,
                temperature=0.1,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            content = response.choices[0].message.content

            # 清理可能的 markdown 代码块标记
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)

            # 构建关键词到分类的映射（使用 related_keywords 匹配）
            category_map = {item['keyword']: item['category'] for item in result.get('classification', [])}

            # 分类原始关键词（使用 related_keywords 匹配）
            batch_classified = {'SEED': [], 'PROJECT': [], 'TRASH': []}
            for kw in batch:
                category = category_map.get(kw['related_keywords'], 'SEED')  # 使用 related_keywords 匹配，默认归为 SEED
                batch_classified[category].append(kw)

            seed_count = len(batch_classified['SEED'])
            project_count = len(batch_classified['PROJECT'])
            trash_count = len(batch_classified['TRASH'])

            print(f"   ✅ 批次 {batch_idx} 完成: SEED={seed_count}, PROJECT={project_count}, TRASH={trash_count}")

            return batch_classified

        except Exception as e:
            error_msg = str(e)
            # 检查是否是内容审核错误
            if is_content_filter_error(error_msg):
                current_size = len(batch)

                # 如果已经是最小批次（50个），放弃并归为 SEED
                if current_size <= 50:
                    print(f"   ⚠️  批次 {batch_idx} 内容审核拦截（{current_size}个关键词已达最小批次），默认归为 SEED")
                    return {'SEED': list(batch), 'PROJECT': [], 'TRASH': []}

                # 减小批次到50个并重试
                new_size = 50
                print(f"   ⚠️  批次 {batch_idx} 内容审核拦截，分批重试（{current_size}个 → {new_size}个/批）...")

                # 分批处理
                all_classified = {'SEED': [], 'PROJECT': [], 'TRASH': []}
                sub_batches = [batch[i:i+new_size] for i in range(0, len(batch), new_size)]

                for i, sub_batch in enumerate(sub_batches, 1):
                    print(f"      → 处理子批次 {i}/{len(sub_batches)} ({len(sub_batch)}个关键词)...")
                    sub_result = classify_batch(sub_batch, batch_idx, total_batches, retry_count + 1)
                    # 合并结果
                    for category in ['SEED', 'PROJECT', 'TRASH']:
                        all_classified[category].extend(sub_result[category])

                return all_classified

            # 其他错误：全部归为 SEED
            print(f"   ⚠️  批次 {batch_idx} 分类失败: {e}，默认归为 SEED")
            return {'SEED': list(batch), 'PROJECT': [], 'TRASH': []}

    # 并发处理
    with ThreadPoolExecutor(max_workers=max_parallel) as executor:
        futures = {
            executor.submit(classify_batch, batch, i + 1, len(batches)): i
            for i, batch in enumerate(batches)
        }

        for future in as_completed(futures):
            try:
                batch_result = future.result()
                # 合并结果
                for category in ['SEED', 'PROJECT', 'TRASH']:
                    classified[category].extend(batch_result[category])
            except Exception as e:
                batch_idx = futures[future]
                print(f"   ❌ 批次 {batch_idx} 处理异常: {e}")

    # 统计
    total = len(keywords)
    print(f"\n✅ 分类完成:")
    print(f"   🌱 种子类 (SEED): {len(classified['SEED'])} 个 ({len(classified['SEED'])/total*100:.1f}%)")
    print(f"   🎯 项目类 (PROJECT): {len(classified['PROJECT'])} 个 ({len(classified['PROJECT'])/total*100:.1f}%)")
    print(f"   🗑️  噪音类 (TRASH): {len(classified['TRASH'])} 个 ({len(classified['TRASH'])/total*100:.1f}%)")

    return classified

# ==================== AI 翻译 ====================

def create_translation_prompt(keywords: List[Dict[str, Any]]) -> str:
    """创建翻译 prompt"""
    keywords_text = "\n".join([kw['related_keywords'] for kw in keywords[:400]])

    prompt = f"""将以下英文关键词翻译成中文。这些是搜索关键词，可能是产品、工具、概念等。

关键词列表:
{keywords_text}

输出JSON格式:
{{
  "translations": [
    {{"english": "ai image generator", "chinese": "AI图片生成器"}},
    {{"english": "to do list", "chinese": "待办事项清单"}}
  ]
}}

只输出JSON，无其他文字。"""

    return prompt

def translate_keywords(keywords: List[Dict[str, Any]], client) -> List[Dict[str, Any]]:
    """AI 批量翻译关键词"""
    if not keywords:
        return []

    batch_size = 400
    batches = [keywords[i:i+batch_size] for i in range(0, len(keywords), batch_size)]

    print(f"📝 将分 {len(batches)} 批进行翻译...")

    def translate_batch(batch: List[Dict[str, Any]], batch_idx: int, total_batches: int, retry_count: int = 0) -> bool:
        """翻译单个批次，返回是否成功"""
        print(f"   正在翻译批次 {batch_idx}/{total_batches} ({len(batch)}个关键词)...")

        prompt = create_translation_prompt(batch)

        try:
            response = client.chat.completions.create(
                model=CONFIG['api']['model'],
                max_tokens=MAX_TOKENS,
                temperature=0.1,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            content = response.choices[0].message.content

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)

            # 构建翻译映射
            trans_map = {item['english']: item['chinese'] for item in result.get('translations', [])}

            # 添加翻译到原始数据（使用 related_keywords 匹配）
            for kw in batch:
                kw['chinese'] = trans_map.get(kw['related_keywords'], '')

            print(f"   ✅ 批次 {batch_idx} 完成")
            return True

        except Exception as e:
            error_msg = str(e)
            # 检查是否是内容审核错误
            if is_content_filter_error(error_msg):
                current_size = len(batch)

                # 如果已经是最小批次（50个），放弃
                if current_size <= 50:
                    print(f"   ⚠️  批次 {batch_idx} 内容审核拦截（{current_size}个关键词已达最小批次），翻译留空")
                    for kw in batch:
                        kw['chinese'] = ''
                    return False

                # 减小批次到50个并重试
                new_size = 50
                print(f"   ⚠️  批次 {batch_idx} 内容审核拦截，分批重试（{current_size}个 → {new_size}个/批）...")

                # 分批处理
                sub_batches = [batch[i:i+new_size] for i in range(0, len(batch), new_size)]

                for i, sub_batch in enumerate(sub_batches, 1):
                    print(f"      → 处理子批次 {i}/{len(sub_batches)} ({len(sub_batch)}个关键词)...")
                    translate_batch(sub_batch, batch_idx, total_batches, retry_count + 1)

                return True

            # 其他错误：留空
            print(f"   ⚠️  批次 {batch_idx} 翻译失败: {e}，翻译留空")
            for kw in batch:
                kw['chinese'] = ''
            return False

    # 并发处理翻译
    max_parallel = CONFIG['concurrency']['max_parallel']
    with ThreadPoolExecutor(max_workers=max_parallel) as executor:
        futures = {
            executor.submit(translate_batch, batch, i, len(batches)): i
            for i, batch in enumerate(batches, 1)
        }

        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                batch_idx = futures[future]
                print(f"   ❌ 批次 {batch_idx} 处理异常: {e}")

    print(f"✅ 翻译完成")
    return keywords

# ==================== AI 分析 ====================

def create_client():
    """创建智谱GLM客户端（使用OpenAI兼容接口）"""
    api_key = os.environ.get(CONFIG['api']['api_key_env'])

    if not api_key:
        raise ValueError(
            f"未找到 API Key！\n\n"
            f"请选择以下方式之一设置 API Key：\n"
            f"1. 在项目根目录创建 .env 文件，添加: {CONFIG['api']['api_key_env']}=your-api-key\n"
            f"2. 或在终端设置: export {CONFIG['api']['api_key_env']}='your-api-key'\n\n"
            f"获取智谱GLM API Key: https://open.bigmodel.cn/usercenter/apikeys"
        )

    # 使用 OpenAI SDK 连接智谱GLM
    return OpenAI(
        api_key=api_key,
        base_url="https://open.bigmodel.cn/api/coding/paas/v4",  # GLM编码套餐专属端点
        timeout=1200.0  # 20分钟超时（每批次）
    )

def create_clustering_prompt(keywords: List[Dict[str, Any]]) -> str:
    """创建聚类分析的 prompt"""
    # 格式化关键词数据
    keywords_text = "\n".join([
        f"{kw['keyword']}|{kw['related_keywords']}|{kw['value']}|{kw['type']}"
        for kw in keywords[:200]  # 减少到200个，避免prompt太长
    ])

    prompt = f"""你是关键词分析师。分析以下搜索数据，按主题聚类。

数据格式: 词根|相关词|数值|类型
- rising类型: 数值是增长率百分比
- top类型: 数值是相关度分数(0-100)

**重要**：请对「相关词」（第二列）进行聚类分析，相关词才是用户实际搜索的内容。

数据:
{keywords_text}

要求:
1. ⚠️ **必须返回所有输入的关键词，不得遗漏任何关键词**
2. 将相似关键词归为同一主题
3. 每个主题至少3个关键词
4. 用英文命名主题，并提供中文翻译
5. 识别主题下的细分领域
6. 评分(0-100): 考虑关键词数量、增长率、相关度
7. 分析搜索意图(交易/信息/导航/商业调查)
8. 建议网站类型(工具站/内容站/导航站)
9. 建议变现方式(订阅/广告/联盟营销)

输出JSON格式(不要其他文字):
{{
  "themes": [
    {{
      "name": "AI Image Tools",
      "name_zh": "AI图片工具",
      "score": 95,
      "keywords_count": 25,
      "rising_count": 18,
      "top_count": 7,
      "avg_rising_growth": 800,
      "avg_top_score": 85,
      "search_intent": "交易意图",
      "site_type": "工具站",
      "monetization": "订阅制",
      "opportunity_analysis": "该主题增长迅速，适合做AI图片生成工具站",
      "subthemes": [
        {{
          "name": "AI Image Generator",
          "keywords": [
            {{"keyword": "ai image generator from text", "value": 1200, "type": "rising"}}
          ]
        }}
      ]
    }}
  ]
}}

**注意**：
1. 输出中的keyword字段必须是「相关词」的完整内容
2. ⚠️ **本批次共 {len(keywords)} 个关键词，你必须在所有 subthemes 的 keywords 数组中返回全部 {len(keywords)} 个关键词，不得遗漏**

只输出JSON，无其他文字。"""

    return prompt

def call_ai_for_clustering(keywords: List[Dict[str, Any]], client, retry_count=0) -> Dict[str, Any]:
    """调用智谱GLM进行聚类分析"""
    prompt = create_clustering_prompt(keywords)

    try:
        # 使用智谱GLM的Chat Completions接口（OpenAI兼容）
        response = client.chat.completions.create(
            model=CONFIG['api']['model'],
            max_tokens=CONFIG['api']['max_tokens'],
            temperature=CONFIG['api']['temperature'],
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )

        # 提取响应内容
        content = response.choices[0].message.content

        # 清理可能的 markdown 代码块标记
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        return json.loads(content)

    except json.JSONDecodeError as e:
        print(f"❌ JSON解析失败: {e}")
        # 如果是JSON解析错误，可能是响应不完整，尝试重试
        if retry_count < 2:
            print(f"🔄 正在重试... (第{retry_count + 1}次)")
            import time
            time.sleep(2)  # 等待2秒后重试
            return call_ai_for_clustering(keywords, client, retry_count + 1)
        return {"themes": []}

    except Exception as e:
        error_msg = str(e)
        # 检查是否是敏感内容错误
        if "1301" in error_msg or "敏感" in error_msg or "contentFilter" in error_msg:
            # 智能分批处理
            return handle_content_filter_error(keywords, client, retry_count)
        else:
            print(f"❌ AI 分析失败: {e}")
            if retry_count < 2:
                print(f"🔄 正在重试... (第{retry_count + 1}次)")
                import time
                time.sleep(2)
                return call_ai_for_clustering(keywords, client, retry_count + 1)
            return {"themes": []}

def handle_content_filter_error(keywords: List[Dict[str, Any]], client, retry_count) -> Dict[str, Any]:
    """处理内容审核错误 - 智能分批重试"""
    current_size = len(keywords)

    # 如果已经是最小批次（20个），放弃
    if current_size <= 20:
        print(f"⚠️  内容安全审核拦截，放弃该批次（{current_size}个关键词已达最小批次）")
        print(f"   该批次前5个关键词:")
        for i, kw in enumerate(keywords[:5], 1):
            print(f"     {i}. {kw['keyword']} | {kw['related_keywords']}")

        # 保存被拦截的关键词
        try:
            rejected_file = Path(__file__).parent.parent / "data" / "rejected_keywords.txt"
            with open(rejected_file, 'a', encoding='utf-8') as f:
                f.write(f"\n=== 被拦截批次 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===\n")
                for kw in keywords:
                    f.write(f"{kw['keyword']}|{kw['related_keywords']}|{kw['value']}|{kw['type']}\n")
            print(f"   已保存被拦截的关键词到: {rejected_file}")
        except:
            pass

        return {"themes": []}

    # 计算新的批次大小
    new_size = max(20, current_size // 4)  # 分成4份，但最少20个
    print(f"⚠️  内容安全审核拦截，尝试分批处理（{current_size}个 → {new_size}个/批）")

    # 分批处理
    all_themes = []
    batches = [keywords[i:i+new_size] for i in range(0, len(keywords), new_size)]

    for i, sub_batch in enumerate(batches, 1):
        print(f"   正在处理子批次 {i}/{len(batches)} ({len(sub_batch)}个关键词)...")
        result = call_ai_for_clustering(sub_batch, client, retry_count + 1)
        all_themes.extend(result.get('themes', []))

    return {"themes": all_themes}

def batch_analyze(keywords: List[Dict[str, Any]], client) -> List[Dict[str, Any]]:
    """分批并行分析关键词"""
    batch_size = CONFIG['concurrency']['batch_size']
    max_parallel = CONFIG['concurrency']['max_parallel']

    # 分批
    batches = [keywords[i:i+batch_size] for i in range(0, len(keywords), batch_size)]
    print(f"📊 将分 {len(batches)} 批进行分析")

    all_themes = []

    # 并发处理
    with ThreadPoolExecutor(max_workers=max_parallel) as executor:
        future_to_batch = {
            executor.submit(call_ai_for_clustering, batch, client): i
            for i, batch in enumerate(batches)
        }

        for future in as_completed(future_to_batch):
            batch_idx = future_to_batch[future]
            try:
                result = future.result()
                themes = result.get('themes', [])
                all_themes.extend(themes)
                print(f"✅ 批次 {batch_idx + 1}/{len(batches)} 完成，找到 {len(themes)} 个主题")
            except Exception as e:
                print(f"❌ 批次 {batch_idx + 1} 失败: {e}")

    return all_themes

def merge_and_deduplicate_themes(themes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """合并和去重主题"""
    # 简单去重：按主题名
    seen = {}
    for theme in themes:
        name = theme['name']
        if name not in seen:
            seen[name] = theme
        else:
            # 合并关键词
            existing = seen[name]
            existing['keywords_count'] += theme['keywords_count']
            existing['rising_count'] += theme['rising_count']
            existing['top_count'] += theme['top_count']
            existing['subthemes'].extend(theme.get('subthemes', []))

    # 按得分排序
    merged = list(seen.values())
    merged.sort(key=lambda x: x['score'], reverse=True)

    return merged

# ==================== 趋势分析 ====================

def analyze_trends(
    today_themes: List[Dict[str, Any]],
    history_data: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """分析趋势变化"""
    if not history_data:
        return {
            "status": "首次运行",
            "message": "暂无历史数据可供对比",
            "new_themes": len(today_themes),
            "continuing_themes": 0,
            "disappeared_themes": 0
        }

    # 提取历史主题名
    history_theme_names = set()
    for h in history_data:
        for theme in h.get('themes', []):
            history_theme_names.add(theme['name'])

    # 今天主题名
    today_theme_names = {t['name'] for t in today_themes}

    # 分析
    new_themes = today_theme_names - history_theme_names
    disappeared_themes = history_theme_names - today_theme_names
    continuing_themes = today_theme_names & history_theme_names

    # 分析持续主题的得分变化
    trending_up = []
    trending_down = []

    today_themes_dict = {t['name']: t for t in today_themes}

    for name in continuing_themes:
        today_score = today_themes_dict[name]['score']
        # 简化：假设历史得分相同（实际可以从历史数据读取）
        # 这里可以改进，从历史数据获取真实得分
        pass

    days = len(history_data)
    reliability = "仅供参考" if days < 7 else "趋势可靠"

    return {
        "status": "normal",
        "days_analyzed": days,
        "reliability": reliability,
        "new_themes": len(new_themes),
        "continuing_themes": len(continuing_themes),
        "disappeared_themes": len(disappeared_themes),
        "new_theme_names": list(new_themes),
        "disappeared_theme_names": list(disappeared_themes)
    }

# ==================== 报告生成 ====================

def generate_markdown_report(
    date_str: str,
    themes: List[Dict[str, Any]],
    trend_info: Dict[str, Any],
    keywords_count: int
) -> str:
    """生成 Markdown 报告"""

    lines = []
    lines.append(f"# 关键词分析报告")
    lines.append(f"\n**日期**: {date_str}")
    lines.append(f"**分析关键词数**: {keywords_count}")
    lines.append(f"**识别主题数**: {len(themes)}")
    lines.append("\n---\n")

    # 趋势对比部分
    lines.append("## 📈 趋势对比\n")

    if trend_info['status'] == "首次运行":
        lines.append(f"⚠️ **{trend_info['message']}**")
        lines.append(f"\n从明天开始，将显示趋势变化信息。\n")
    else:
        lines.append(f"**基于**: {trend_info['days_analyzed']} 天数据")
        lines.append(f"**可靠性**: {trend_info['reliability']}")
        lines.append(f"\n")
        lines.append(f"- 🆕 **新出现主题**: {trend_info['new_themes']} 个")
        lines.append(f"- 📊 **持续热门主题**: {trend_info['continuing_themes']} 个")
        lines.append(f"- 📉 **消失主题**: {trend_info['disappeared_themes']} 个")

        if trend_info.get('new_theme_names'):
            lines.append(f"\n**新主题列表**:")
            for name in trend_info['new_theme_names'][:10]:
                lines.append(f"  - {name}")

        lines.append("\n")

    lines.append("---\n")

    # 主题完整列表
    lines.append("## 📊 主题完整列表（按得分排序）\n")

    for i, theme in enumerate(themes, 1):
        # 标记
        markers = []
        if trend_info.get('new_theme_names') and theme['name'] in trend_info['new_theme_names']:
            markers.append("🆕新出现")

        marker_str = f" {', '.join(markers)}" if markers else ""

        lines.append(f"### {i}. {theme.get('name_zh', theme['name'])} [{theme['score']}分]{marker_str}\n")

        lines.append(f"**主题**: {theme['name']}")
        lines.append(f"**关键词数**: {theme['keywords_count']} "
                   f"(飙升: {theme['rising_count']}, 热门: {theme['top_count']})")

        if theme['rising_count'] > 0:
            lines.append(f"**平均增长率**: +{theme['avg_rising_growth']}%")
        if theme['top_count'] > 0:
            lines.append(f"**平均相关度**: {theme['avg_top_score']}")

        # 可选字段，如果存在才添加
        if 'search_intent' in theme:
            lines.append(f"\n**搜索意图**: {theme['search_intent']}")
        if 'site_type' in theme:
            lines.append(f"**网站类型**: {theme['site_type']}")
        if 'monetization' in theme:
            lines.append(f"**变现方式**: {theme['monetization']}")

        lines.append(f"\n**💡 商业机会分析**:")
        lines.append(f"{theme['opportunity_analysis']}")

        # 细分
        if theme.get('subthemes'):
            lines.append(f"\n**📂 细分领域**:")
            for sub in theme['subthemes']:
                # 细分主题名称翻译
                sub_name = sub['name']
                sub_translation = translate_subtheme_simple(sub_name)
                if sub_translation:
                    lines.append(f"\n- **{sub_name}** (*{sub_translation}*) ({len(sub['keywords'])} 个关键词)")
                else:
                    lines.append(f"\n- **{sub_name}** ({len(sub['keywords'])} 个关键词)")

                for kw in sub['keywords'][:5]:  # 只显示前5个
                    type_icon = "📈" if kw['type'] == 'rising' else "🔥"
                    value_str = f"+{kw['value']}%" if kw['type'] == 'rising' else f"{kw['value']}分"

                    # 添加简单的关键词翻译（常见词）
                    keyword = kw['keyword']
                    translation = translate_keyword_simple(keyword)
                    if translation:
                        lines.append(f"  - {type_icon} `{keyword}` - {value_str} - *{translation}*")
                    else:
                        lines.append(f"  - {type_icon} `{keyword}` - {value_str}")

                if len(sub['keywords']) > 5:
                    lines.append(f"  - *还有 {len(sub['keywords'])-5} 个关键词...*")

        lines.append("\n---\n")

    return "\n".join(lines)

def translate_keyword_simple(keyword: str) -> str:
    """简单的关键词翻译（常见词）"""
    # 常见关键词翻译字典
    translations = {
        # List相关
        "to do list": "待办事项清单",
        "voter list": "选民名单",
        "check list": "检查清单",
        "list of us presidents": "美国总统列表",
        "tier list": "等级排名列表",
        "baby list": "婴儿清单",
        "voter list download": "选民名单下载",
        "holiday list 2026": "2026年节假日清单",
        "bucket list": "愿望清单",
        "demon list": "恶魔名单",

        # 常见词汇
        "ai image generator": "AI图片生成器",
        "image ai": "图片AI",
        "background image": "背景图片",
        "search image": "搜索图片",
        "photo editor": "照片编辑器",
        "image compressor": "图片压缩工具",
        "cartoon": "卡通",
        "anime": "动漫",
        "summary": "摘要",
        "action": "动作",
        "advisor": "顾问",
    }

    # 精确匹配
    if keyword.lower() in translations:
        return translations[keyword.lower()]

    # 部分匹配（处理带修饰词的情况）
    key_lower = keyword.lower()
    for en, zh in translations.items():
        if en in key_lower or key_lower in en:
            return zh

    return ""  # 没有找到翻译

def translate_subtheme_simple(subtheme_name: str) -> str:
    """细分主题名称翻译"""
    translations = {
        # 细分主题翻译
        "list creation": "清单创建",
        "list management": "清单管理",
        "voter lists": "选民名单",
        "event lists": "活动清单",
        "miscellaneous lists": "其他清单",
        "ai image generator": "AI图片生成器",
        "ai image editor": "AI图片编辑器",
        "photo editing tools": "照片编辑工具",
        "cartoon search": "卡通搜索",
        "anime characters": "动漫角色",
        "summary tools": "摘要工具",
        "action movies": "动作电影",
        "financial advisors": "财务顾问",
    }

    # 精确匹配
    if subtheme_name.lower() in translations:
        return translations[subtheme_name.lower()]

    # 部分匹配
    key_lower = subtheme_name.lower()
    for en, zh in translations.items():
        if en in key_lower or key_lower in en:
            return zh

    return ""  # 没有找到翻译

def generate_markdown_report_with_classification(
    date_str: str,
    seed_keywords: List[Dict[str, Any]],
    themes: List[Dict[str, Any]],
    trash_keywords: List[Dict[str, Any]],
    trend_info: Dict[str, Any],
    keywords_count: int
) -> str:
    """生成包含分类的 Markdown 报告"""

    lines = []
    lines.append(f"# 关键词分析报告")
    lines.append(f"\n**日期**: {date_str}")
    lines.append(f"**总关键词数**: {keywords_count}")
    lines.append(f"**识别主题数**: {len(themes)}")
    lines.append("\n---\n")

    # 关键词分类统计
    lines.append("## 📊 关键词分类统计\n")
    lines.append(f"- 🌱 **种子类 (SEED)**: {len(seed_keywords)} 个 - 搜索量大但意图不清晰，待深挖")
    lines.append(f"- 🎯 **项目类 (PROJECT)**: {sum(t['keywords_count'] for t in themes)} 个关键词 → {len(themes)} 个主题")
    lines.append(f"- 🗑️ **噪音类 (TRASH)**: {len(trash_keywords)} 个 - 品牌词/导航词，已过滤")
    lines.append("\n---\n")

    # ========== 第一部分：种子关键词 ==========
    lines.append("## 🌱 种子关键词 (SEED) - 待深挖")
    lines.append(f"\n*共 {len(seed_keywords)} 个*")
    lines.append("\n这些关键词搜索量大但意图不清晰，需要进一步研究：")
    lines.append("\n📌 **特征**:")
    lines.append("- 用户搜索的是「概念」或「事物」")
    lines.append("- 无法通过一篇文章彻底解决需求")
    lines.append("- 需要通过下拉词、相关词、SEMrush 等工具深挖长尾词")
    lines.append("\n---\n")

    if seed_keywords:
        # 按分数排序
        sorted_seeds = sorted(seed_keywords, key=lambda x: x['value'], reverse=True)

        # 显示所有种子关键词（移除前100个的限制）
        for i, kw in enumerate(sorted_seeds, 1):
            type_icon = "📈" if kw['type'] == 'rising' else "🔥"
            value_str = f"+{kw['value']}%" if kw['type'] == 'rising' else f"{kw['value']}分"
            chinese = kw.get('chinese', '')
            chinese_str = f" - *{chinese}*" if chinese else ""

            lines.append(f"{i}. {type_icon} **`{kw['related_keywords']}`** - {value_str}{chinese_str}")
            lines.append("")

    lines.append("\n---\n")

    # ========== 第二部分：项目关键词（原有逻辑） ==========
    lines.append("## 🎯 项目关键词 (PROJECT) - 立即可执行")
    lines.append(f"\n*共 {sum(t['keywords_count'] for t in themes)} 个关键词，聚合为 {len(themes)} 个主题*")
    lines.append("\n这些关键词搜索意图明确，可以立即开始项目：")
    lines.append("\n📌 **特征**:")
    lines.append("- 搜索意图极其明确，颗粒度细")
    lines.append("- 通常包含动词或长限定语")
    lines.append("- 可以立刻想象出页面标题")
    lines.append("\n---\n")

    # 趋势对比部分
    lines.append("### 📈 趋势对比\n")

    if trend_info.get('status') == "disabled":
        lines.append(f"⚠️ **历史对比已禁用**")
        lines.append(f"\n{trend_info['message']}")
        lines.append(f"\n**原因**：由于关键词分类标准已优化（基于搜索意图），")
        lines.append(f"旧数据与新数据不兼容，无法进行数值对比。")
        lines.append(f"\n**建议**：积累7天新数据后，可在`config.yaml`中重新启用历史对比：")
        lines.append(f"```yaml")
        lines.append(f"history:")
        lines.append(f"  enabled: true  # 改为true")
        lines.append(f"```")
        lines.append(f"\n")
    elif trend_info['status'] == "首次运行":
        lines.append(f"⚠️ **{trend_info['message']}**")
        lines.append(f"\n从明天开始，将显示趋势变化信息。\n")
    else:
        lines.append(f"**基于**: {trend_info['days_analyzed']} 天数据")
        lines.append(f"**可靠性**: {trend_info['reliability']}")
        lines.append(f"\n")
        lines.append(f"- 🆕 **新出现主题**: {trend_info['new_themes']} 个")
        lines.append(f"- 📊 **持续热门主题**: {trend_info['continuing_themes']} 个")
        lines.append(f"- 📉 **消失主题**: {trend_info['disappeared_themes']} 个")

        if trend_info.get('new_theme_names'):
            lines.append(f"\n**新主题列表**:")
            for name in trend_info['new_theme_names'][:10]:
                lines.append(f"  - {name}")

        lines.append("\n")

    lines.append("---\n")

    # 主题完整列表
    lines.append("### 📊 主题完整列表（按得分排序）\n")

    for i, theme in enumerate(themes, 1):
        # 标记
        markers = []
        if trend_info.get('new_theme_names') and theme['name'] in trend_info['new_theme_names']:
            markers.append("🆕新出现")

        marker_str = f" {', '.join(markers)}" if markers else ""

        lines.append(f"#### {i}. {theme.get('name_zh', theme['name'])} [{theme['score']}分]{marker_str}\n")

        lines.append(f"**主题**: {theme['name']}")
        lines.append(f"**关键词数**: {theme['keywords_count']} "
                   f"(飙升: {theme['rising_count']}, 热门: {theme['top_count']})")

        if theme['rising_count'] > 0:
            lines.append(f"**平均增长率**: +{theme['avg_rising_growth']}%")
        if theme['top_count'] > 0:
            lines.append(f"**平均相关度**: {theme['avg_top_score']}")

        # 可选字段，如果存在才添加
        if 'search_intent' in theme:
            lines.append(f"\n**搜索意图**: {theme['search_intent']}")
        if 'site_type' in theme:
            lines.append(f"**网站类型**: {theme['site_type']}")
        if 'monetization' in theme:
            lines.append(f"**变现方式**: {theme['monetization']}")

        lines.append(f"\n**💡 商业机会分析**:")
        lines.append(f"{theme['opportunity_analysis']}")

        # 细分
        if theme.get('subthemes'):
            lines.append(f"\n**📂 细分领域**:")
            for sub in theme['subthemes']:
                # 细分主题名称翻译
                sub_name = sub['name']
                sub_translation = translate_subtheme_simple(sub_name)
                if sub_translation:
                    lines.append(f"\n- **{sub_name}** (*{sub_translation}*) ({len(sub['keywords'])} 个关键词)")
                else:
                    lines.append(f"\n- **{sub_name}** ({len(sub['keywords'])} 个关键词)")

                for kw in sub['keywords'][:5]:  # 只显示前5个
                    type_icon = "📈" if kw['type'] == 'rising' else "🔥"
                    value_str = f"+{kw['value']}%" if kw['type'] == 'rising' else f"{kw['value']}分"

                    # 添加简单的关键词翻译（常见词）
                    keyword = kw['keyword']
                    translation = translate_keyword_simple(keyword)
                    if translation:
                        lines.append(f"  - {type_icon} `{keyword}` - {value_str} - *{translation}*")
                    else:
                        lines.append(f"  - {type_icon} `{keyword}` - {value_str}")

                if len(sub['keywords']) > 5:
                    lines.append(f"  - *还有 {len(sub['keywords'])-5} 个关键词...*")

        lines.append("\n---\n")

    # ========== 第三部分：噪音关键词 ==========
    lines.append("## 🗑️ 噪音关键词 (TRASH) - 已过滤")
    lines.append(f"\n*共 {len(trash_keywords)} 个*")
    lines.append("\n这些关键词已被过滤，不适合做项目：")
    lines.append("\n📌 **特征**:")
    lines.append("- 大品牌词（如 Amazon, Netflix, Facebook）")
    lines.append("- 纯导航词（如 Login, App download, Sign up）")
    lines.append("- 完全无商业转化潜力的词")
    lines.append("\n---\n")

    if trash_keywords:
        # 按分数排序
        sorted_trash = sorted(trash_keywords, key=lambda x: x['value'], reverse=True)

        # 显示所有噪音关键词（移除前50个的限制）
        for i, kw in enumerate(sorted_trash, 1):
            type_icon = "📈" if kw['type'] == 'rising' else "🔥"
            value_str = f"+{kw['value']}%" if kw['type'] == 'rising' else f"{kw['value']}分"
            chinese = kw.get('chinese', '')
            chinese_str = f" - *{chinese}*" if chinese else ""

            lines.append(f"{i}. {type_icon} **`{kw['related_keywords']}`** - {value_str}{chinese_str}")
            lines.append("")

    return "\n".join(lines)

def save_report_with_classification(
    date_str: str,
    seed_keywords: List[Dict[str, Any]],
    themes: List[Dict[str, Any]],
    trash_keywords: List[Dict[str, Any]],
    trend_info: Dict[str, Any],
    keywords_count: int
):
    """保存分类报告"""
    # 保存 JSON
    json_data = {
        "date": date_str,
        "seed_count": len(seed_keywords),
        "project_count": sum(t['keywords_count'] for t in themes),
        "trash_count": len(trash_keywords),
        "themes": themes
    }
    json_path = THEMES_RECENT_DIR / f"themes_{date_str}.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON 数据已保存: {json_path}")

    # 保存 Markdown 报告
    markdown = generate_markdown_report_with_classification(
        date_str, seed_keywords, themes, trash_keywords, trend_info, keywords_count
    )
    report_path = ANALYSIS_DIR / f"report_{date_str}.md"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(markdown)
    print(f"✅ Markdown 报告已保存: {report_path}")

# 保留原有函数以兼容
def save_report(
    date_str: str,
    themes: List[Dict[str, Any]],
    trend_info: Dict[str, Any],
    keywords_count: int
):
    """保存报告"""
    # 保存 JSON
    json_data = {
        "date": date_str,
        "themes": themes
    }
    json_path = THEMES_RECENT_DIR / f"themes_{date_str}.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON 数据已保存: {json_path}")

    # 保存 Markdown 报告
    markdown = generate_markdown_report(date_str, themes, trend_info, keywords_count)
    report_path = ANALYSIS_DIR / f"report_{date_str}.md"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(markdown)
    print(f"✅ Markdown 报告已保存: {report_path}")

# ==================== 主函数 ====================

def main():
    """主函数"""
    import time
    start_time = time.time()

    print("=" * 60)
    print("🔍 关键词分析系统")
    print("=" * 60)

    try:
        # 1. 找到并读取 CSV
        print("\n📁 正在查找最新的 CSV 文件...")
        csv_path, date_str = find_latest_csv()
        print(f"✅ 找到文件: {csv_path.name}")

        print("\n📖 正在读取 CSV 数据...")
        keywords = read_csv(csv_path)

        print("\n🔍 正在过滤关键词...")
        keywords = filter_keywords(keywords)

        # 2. 创建 AI 客户端
        print("\n🤖 正在连接 AI 服务...")
        client = create_client()
        print("✅ AI 客户端已就绪")

        # 3. AI 分类 (新增)
        print(f"\n🏷️  正在分类关键词（共 {len(keywords)} 个关键词）...")
        classified = classify_keywords(keywords, client)

        seed_keywords = classified['SEED']
        project_keywords = classified['PROJECT']
        trash_keywords = classified['TRASH']

        # 4. AI 翻译 SEED 和 TRASH
        print(f"\n📝 正在翻译种子类和噪音类关键词...")
        if seed_keywords:
            seed_keywords = translate_keywords(seed_keywords, client)
        if trash_keywords:
            trash_keywords = translate_keywords(trash_keywords, client)

        # 5. 加载历史数据 (只针对 PROJECT 类)
        # 检查是否启用历史对比
        history_enabled = CONFIG['history']['enabled']
        history_data = []

        if history_enabled:
            print("\n📚 正在加载历史数据...")
            history_data = load_history_data(date_str)
            if history_data:
                print(f"✅ 找到 {len(history_data)} 天的历史数据")
            else:
                print("⚠️  未找到历史数据（首次运行）")
        else:
            print("\n⚠️  历史对比已禁用（由于分类标准已改变）")
            print("   待积累足够新数据后，可在config.yaml中启用")

        # 6. AI 分析 PROJECT 类 (原有逻辑)
        themes = []
        if project_keywords:
            print(f"\n🧠 正在分析项目类关键词（共 {len(project_keywords)} 个）...")
            themes = batch_analyze(project_keywords, client)

            print(f"\n🔗 正在合并和去重主题...")
            themes = merge_and_deduplicate_themes(themes)
            print(f"✅ 最终识别 {len(themes)} 个主题")
        else:
            print(f"\n⚠️  没有项目类关键词需要分析")

        # 7. 趋势分析
        if history_data:
            print(f"\n📈 正在分析趋势...")
            trend_info = analyze_trends(themes, history_data)
        else:
            print(f"\n⚠️  跳过趋势分析（历史对比已禁用）")
            trend_info = {
                "status": "disabled",
                "message": "历史对比已禁用，由于分类标准已改变。待积累足够新数据后可重新启用。"
            }

        # 8. 保存报告 (修改: 包含三类词)
        print(f"\n💾 正在保存报告...")
        save_report_with_classification(
            date_str,
            seed_keywords,
            themes,
            trash_keywords,
            trend_info,
            len(keywords)
        )

        # 9. 清理旧数据
        print(f"\n🗑️  正在清理过期数据...")
        cleanup_old_data()

        # 完成
        end_time = time.time()
        elapsed_time = end_time - start_time

        print("\n" + "=" * 60)
        print("✅ 分析完成！")
        print("=" * 60)

        # 显示运行时间
        hours = int(elapsed_time // 3600)
        minutes = int((elapsed_time % 3600) // 60)
        seconds = int(elapsed_time % 60)

        if hours > 0:
            time_str = f"{hours}小时{minutes}分{seconds}秒"
        elif minutes > 0:
            time_str = f"{minutes}分{seconds}秒"
        else:
            time_str = f"{seconds}秒"

        print(f"\n⏱️  运行时间: {time_str}")

        print(f"\n📄 查看报告: {ANALYSIS_DIR / f'report_{date_str}.md'}")
        print(f"📊 查看数据: {THEMES_RECENT_DIR / f'themes_{date_str}.json'}")

        # 显示统计
        print(f"\n📊 关键词分类统计:")
        print(f"   🌱 种子类: {len(seed_keywords)} 个")
        print(f"   🎯 项目类: {len(project_keywords)} 个 → {len(themes)} 个主题")
        print(f"   🗑️  噪音类: {len(trash_keywords)} 个")

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
