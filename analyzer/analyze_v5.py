#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V5 关键词分析系统 — 三阶段管道 (V3)

Stage 0: 预过滤 — 规则筛除 TRASH（品牌词/导航词），秒出
Stage 1: SERP 搜索 + AI 用户意图 — 搜 DuckDuckGo → AI 分析用户到底想干什么
Stage 2: AI 分类 + 路线 — 基于意图+SERP 判断 PROJECT/SEED + 变现路线

每个阶段的中间结果保存到磁盘，支持批量断点续跑。
"""

import os
import sys
import csv
import json
import re
import time
import argparse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import quote_plus

import yaml
from openai import OpenAI
from dotenv import load_dotenv

# ==================== 初始化 ====================

load_dotenv()

BASE_DIR = Path(__file__).parent.parent  # keyword-strategy/
ANALYZER_DIR = Path(__file__).parent
TRENDSPY_DIR = Path("/Volumes/Lexar/Github/trendspy-related-keywords")
DATA_DIR = BASE_DIR / "data"  # keyword-strategy/data/

def load_config() -> Dict[str, Any]:
    config_path = ANALYZER_DIR / "config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

CONFIG = load_config()

V5_CFG = CONFIG.get('v5_pipeline', {})
DEFAULT_BATCH_SIZE = V5_CFG.get('batch_size', 20)
SEARCH_TOPN = V5_CFG.get('stages', {}).get('stage2_serp', {}).get('search_topn', 5)
RESUME_ENABLED = V5_CFG.get('resume', True)

# OUTPUT_DIR 和 INTERMEDIATE_DIR 在找到 CSV 后动态设置
OUTPUT_DIR: Optional[Path] = None
INTERMEDIATE_DIR: Optional[Path] = None

def setup_output_dir(date_str: str):
    """根据 CSV 日期设置输出目录: keyword-strategy/data/batches_YYYYMMDD/"""
    global OUTPUT_DIR, INTERMEDIATE_DIR
    OUTPUT_DIR = DATA_DIR / f"batches_{date_str}"
    INTERMEDIATE_DIR = OUTPUT_DIR / "intermediates"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)

# ==================== AI 客户端 ====================

MAX_TOKENS = 32000

def create_client() -> OpenAI:
    provider = CONFIG['api'].get('provider', 'zhipu')
    if provider == 'zhipu':
        api_key = os.environ.get(CONFIG['api']['api_key_env'])
        if not api_key:
            raise ValueError(f"未找到 API Key！请设置环境变量 {CONFIG['api']['api_key_env']}")
        return OpenAI(api_key=api_key, base_url="https://open.bigmodel.cn/api/coding/paas/v4", timeout=1200.0)
    elif provider == 'ollama':
        api_config = CONFIG['api'].get('ollama', {})
        return OpenAI(api_key="ollama", base_url=api_config.get('base_url', "http://localhost:11434/v1"), timeout=1200.0)
    else:
        raise ValueError(f"不支持的 AI 提供商: {provider}")

# ==================== CSV 读取 ====================

def find_latest_csv() -> Path:
    """在 trendspy-related-keywords/data_YYYYMMDD/ 下找最新的 daily_report CSV。"""
    # 找最新的 data_YYYYMMDD 目录
    data_dirs = sorted([
        d for d in TRENDSPY_DIR.iterdir()
        if d.is_dir() and re.match(r'data_\d{8}$', d.name)
    ], key=lambda d: d.name, reverse=True)

    if not data_dirs:
        raise FileNotFoundError(f"在 {TRENDSPY_DIR} 下没有找到 data_YYYYMMDD 目录")

    for data_dir in data_dirs:
        csv_files = [f for f in data_dir.glob("daily_report_*.csv") if not f.name.startswith("._")]
        if csv_files:
            csv_path = max(csv_files, key=lambda f: f.stat().st_mtime)
            # 提取日期并设置输出目录
            date_match = re.search(r'(\d{8})', data_dir.name)
            if date_match:
                setup_output_dir(date_match.group(1))
            return csv_path

    raise FileNotFoundError(f"在 {data_dirs[0]} 下没有找到 daily_report_*.csv")

def load_batch_from_csv(csv_path: Path, offset: int, batch_size: int) -> Tuple[List[Dict], bool]:
    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, r in enumerate(reader):
            if i < offset:
                continue
            if len(rows) >= batch_size:
                return rows, True
            rows.append({
                'index': i + 1,
                'keyword_root': r['keyword'].strip(),
                'related_keywords': r['related_keywords'].strip(),
                'value': int(r['value']),
                'type': r['type'].strip(),
            })
    return rows, False

def compute_trend(value: int, kw_type: str) -> str:
    if kw_type == 'rising':
        if value >= 5000: return '爆发'
        if value >= 500: return '强上升'
        if value >= 200: return '上升'
        if value >= 100: return '中上升'
        return '弱上升'
    else:
        if value >= 50: return '稳健'
        return '冷门'

# ==================== Stage 0: 预过滤 TRASH ====================

TRASH_PATTERNS = [
    r'\blogin\b', r'\bsign\s*up\b', r'\bdownload\b', r'\bapp\s+store\b',
    r'\bfacebook\b', r'\bamazon\b', r'\bwhatsapp\b', r'\binstagram\b',
    r'\bnetflix\b', r'\byoutube\b', r'\btiktok\b', r'\bspotify\b',
    r'\bgoogle\s+play\b', r'\bapple\s+store\b',
]

def stage0_trash_filter(kw: Dict) -> bool:
    """返回 True 如果是 TRASH。"""
    text = kw['related_keywords'].lower().strip()
    for p in TRASH_PATTERNS:
        if re.search(p, text):
            return True
    return False

# ==================== Stage 1: SERP 搜索 + AI 用户意图 ====================

def fetch_duckduckgo_titles(query: str, topn: int = 5) -> List[str]:
    url = f'https://html.duckduckgo.com/html/?q={quote_plus(query)}'
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36'
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
    except Exception:
        return []
    titles = re.findall(r'<a[^>]*class="result__a"[^>]*>(.*?)</a>', html, flags=re.I | re.S)
    clean = []
    for t in titles:
        t = re.sub(r'<.*?>', '', t)
        t = re.sub(r'\s+', ' ', t).strip()
        if t:
            clean.append(t)
    return clean[:topn]


def _build_stage1_prompt(kw: Dict) -> str:
    """Stage 1 prompt: 基于 SERP 分析用户意图。"""
    serp_list = "\n".join([f"  {i+1}. {t}" for i, t in enumerate(kw['serp_titles'])])

    return f"""你是搜索意图分析专家。

用户搜索了: "{kw['related_keywords']}"

以下是 DuckDuckGo 真实搜索结果标题:
{serp_list}

请分析:

1. **meaning**: 结合搜索结果，这个关键词真正指的是什么？用一句话中文总结。
2. **user_need**: 搜索这个词的用户，具体想解决什么问题？要非常具体，不要泛泛而谈。用中文。
3. **hypothesis**: 基于用户需求，我们可以做什么网站/产品来满足？一句话中文。

输出 JSON（不要其他文字）:
{{"meaning": "...", "user_need": "...", "hypothesis": "..."}}"""


def stage1_intent(kw: Dict, client: OpenAI) -> Dict:
    """Stage 1: 搜索 + AI 分析用户意图。"""
    # 搜索
    kw['serp_titles'] = fetch_duckduckgo_titles(kw['related_keywords'], topn=SEARCH_TOPN)

    if not kw['serp_titles']:
        return {'meaning': None, 'user_need': '', 'hypothesis': ''}

    # AI 分析意图
    prompt = _build_stage1_prompt(kw)
    try:
        response = client.chat.completions.create(
            model=CONFIG['api']['model'],
            max_tokens=MAX_TOKENS,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content or ""
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return json.loads(content)
    except Exception as e:
        print(f"      ⚠️  Stage 1 AI 失败: {e}")
        return {'meaning': None, 'user_need': '', 'hypothesis': ''}

# ==================== Stage 2: AI 分类 + 路线 ====================

def _build_stage2_prompt(kw: Dict) -> str:
    """Stage 2 prompt: 基于用户意图 + SERP 做分类和路线判断。"""
    serp_list = "\n".join([f"  {i+1}. {t}" for i, t in enumerate(kw.get('serp_titles', []))])
    meaning = kw.get('meaning') or '(未知)'
    user_need = kw.get('user_need') or '(未知)'

    return f"""你是 SEO 关键词分类专家。根据以下信息判断此关键词的分类和变现路线。

## 关键词
- 相关词: {kw['related_keywords']}
- 含义: {meaning}
- 用户需求: {user_need}
- 趋势: {kw['trend']}（数值 {kw['value']}，{kw['type']} 类型）

## SERP 搜索结果
{serp_list}

---

## 分类标准

### 判断流程

**第一步：判断搜索意图**
问自己：**能直接猜出用户想干什么吗？**

- **意图明确** → PROJECT
  - 用户想找具体答案/产品/服务
  - 可以立刻想象出页面标题和内容
  - 是新兴需求、长期需求或季节性需求（不是一次性短期热点）

- **意图模糊** → SEED
  - 不知道用户具体想要什么
  - 概念太宽泛，可能是多种意图

**第二步：词组长度验证（辅助）**
- ≤ 2个单词 → 倾向 SEED
- ≥ 3个单词 → 倾向 PROJECT
- ≥ 5个单词 → 几乎肯定 PROJECT

### 判断示例
| 关键词 | 分类 | 理由 |
|--------|------|------|
| what is a property tax | PROJECT | 疑问词，意图清晰 |
| ai image generator from text | PROJECT | 想找工具，意图明确 |
| ai | SEED | 概念性，意图不明 |
| crm | SEED | 产品类别，太宽泛 |

---

## SERP 赛道判断

判断 SERP 结果是否与「AI工具/自动化/数字产品」赛道匹配:
- **serp_fit = HIGH**: SERP 主要是 AI/工具/自动化内容
- **serp_fit = MEDIUM**: 混合意图
- **serp_fit = LOW**: 非 AI 赛道

**规则**: 如果 serp_fit 为 LOW，route 必须为 NO_RECOMMENDATION。

---

输出 JSON（不要其他文字）:
{{
  "class": "PROJECT 或 SEED",
  "serp_fit": "HIGH / MEDIUM / LOW",
  "serp_reason": "一句话解释赛道判断（中文）",
  "route": "WEBSITE / DIGITAL_PRODUCT / BOTH / NO_RECOMMENDATION",
  "route_reason": "一句话解释路线建议（中文）或 null",
  "offer_examples": ["具体产品示例", "..."] 或 []
}}"""


def stage2_classify_route(kw: Dict, client: OpenAI) -> Dict:
    """Stage 2: AI 分类 + 路线判断。"""
    prompt = _build_stage2_prompt(kw)
    try:
        response = client.chat.completions.create(
            model=CONFIG['api']['model'],
            max_tokens=MAX_TOKENS,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content or ""
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        result = json.loads(content)

        # 强制规则: LOW → NO_RECOMMENDATION
        if result.get('serp_fit') == 'LOW':
            result['route'] = 'NO_RECOMMENDATION'
            result['offer_examples'] = []

        return result
    except Exception as e:
        print(f"      ⚠️  Stage 2 AI 失败: {e}")
        return {
            'class': 'SEED',
            'serp_fit': 'LOW',
            'serp_reason': None,
            'route': 'NO_RECOMMENDATION',
            'route_reason': None,
            'offer_examples': [],
        }

# ==================== 保存/加载 ====================

def _batch_label(offset: int, batch_size: int) -> str:
    return f"{offset + 1:04d}_{offset + batch_size:04d}"

def save_intermediate(data: Any, stage_name: str, batch_label: str):
    path = INTERMEDIATE_DIR / f"{stage_name}_batch_{batch_label}.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"   💾 中间结果: {path.name}")

def save_final_results(results: List[Dict], batch_label: str,
                       timing: Dict, csv_path: str, batch_size: int):
    data = {
        "source_csv": str(csv_path),
        "batch_range": batch_label.replace('_', '-'),
        "batch_size": batch_size,
        "timing_breakdown": timing,
        "results": results,
    }
    path = OUTPUT_DIR / f"final_results_batch_{batch_label}.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"   ✅ 最终结果: {path.name}")
    return path

def load_progress() -> Dict:
    progress_path = OUTPUT_DIR / "progress.json"
    if progress_path.exists():
        with open(progress_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_progress(csv_path: str, offset: int, total_batches: int, total_processed: int):
    progress = {
        "current_file": str(csv_path),
        "next_offset": offset,
        "done": total_processed,
        "last_run_at": datetime.now().astimezone().isoformat(),
        "total_batches": total_batches,
        "total_words_processed": total_processed,
    }
    path = OUTPUT_DIR / "progress.json"
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)

# ==================== 主流程 ====================

def process_single_keyword(kw: Dict, client: OpenAI) -> Dict:
    """处理单个关键词，走完 Stage 0 → 1 → 2。"""
    kw['trend'] = compute_trend(kw['value'], kw['type'])

    # ===== Stage 0: TRASH 过滤 =====
    if stage0_trash_filter(kw):
        return {
            'keyword_root': kw['keyword_root'],
            'related': kw['related_keywords'],
            'value': kw['value'],
            'type': kw['type'],
            'trend': kw['trend'],
            'class': 'TRASH',
            'meaning': None,
            'user_need': None,
            'hypothesis': None,
            'serp_fit': 'SKIPPED',
            'serp_reason': '品牌/导航噪音词',
            'serp_evidence': [],
            'route': 'NO_RECOMMENDATION',
            'route_reason': None,
            'offer_examples': [],
            'kd': None,
            'kd_status': 'SKIPPED',
        }

    # ===== Stage 1: SERP 搜索 + 用户意图 =====
    s1 = stage1_intent(kw, client)
    kw['meaning'] = s1.get('meaning')
    kw['user_need'] = s1.get('user_need', '')
    kw['hypothesis'] = s1.get('hypothesis', '')
    time.sleep(0.5)  # SERP 限速

    # ===== Stage 2: 分类 + 路线 =====
    s2 = stage2_classify_route(kw, client)

    # serp_evidence 直接用真实 SERP 标题（不让 AI 编）
    serp_evidence = kw.get('serp_titles', [])[:3]
    serp_fit = s2.get('serp_fit', 'LOW')

    return {
        'keyword_root': kw['keyword_root'],
        'related': kw['related_keywords'],
        'value': kw['value'],
        'type': kw['type'],
        'trend': kw['trend'],
        'class': s2.get('class', 'SEED'),
        'meaning': kw.get('meaning'),
        'user_need': kw.get('user_need'),
        'hypothesis': kw.get('hypothesis'),
        'serp_fit': serp_fit,
        'serp_reason': s2.get('serp_reason'),
        'serp_evidence': serp_evidence,
        'route': s2.get('route', 'NO_RECOMMENDATION'),
        'route_reason': s2.get('route_reason'),
        'offer_examples': s2.get('offer_examples', []),
        'kd': None,
        'kd_status': 'PENDING_OPENCLAW' if serp_fit in ('HIGH', 'MEDIUM') else 'SKIPPED',
    }


def process_batch(keywords: List[Dict], client: OpenAI, batch_label: str,
                  csv_path: str, batch_size: int) -> Optional[Path]:
    """处理一批关键词。"""
    timing = {}
    t_start = time.time()

    final_results = []
    trash_count = 0
    search_count = 0

    for i, kw in enumerate(keywords, 1):
        print(f"   [{i}/{len(keywords)}] {kw['related_keywords']}", end=" ", flush=True)
        t_kw = time.time()

        result = process_single_keyword(kw, client)
        final_results.append(result)

        elapsed_kw = round(time.time() - t_kw, 1)

        if result['class'] == 'TRASH':
            print(f"→ TRASH (跳过, {elapsed_kw}s)")
            trash_count += 1
        else:
            search_count += 1
            print(f"→ {result['class']}/{result['serp_fit']} ({elapsed_kw}s)")

    timing['total_sec'] = round(time.time() - t_start, 1)
    timing['trash_count'] = trash_count
    timing['search_count'] = search_count

    # 保存中间结果
    save_intermediate(final_results, "all_stages", batch_label)

    # 保存最终结果
    result_path = save_final_results(final_results, batch_label, timing, csv_path, batch_size)

    print(f"\n   ⏱️  批次耗时: {timing['total_sec']}s "
          f"(TRASH={trash_count}, 搜+AI={search_count})")

    return result_path


def run(batch_size: int = DEFAULT_BATCH_SIZE, limit: Optional[int] = None):
    """主入口。"""
    start_time = time.time()

    print("=" * 60)
    print("🔍 V5 关键词分析（三阶段管道 V3）")
    print("   Stage 0: TRASH 预过滤")
    print("   Stage 1: SERP 搜索 → AI 分析用户意图")
    print("   Stage 2: AI 分类 + 变现路线")
    print("=" * 60)

    csv_path = find_latest_csv()
    print(f"\n📁 CSV: {csv_path.name}")

    print(f"🤖 连接 AI ({CONFIG['api'].get('provider', 'ollama')})...")
    client = create_client()
    print("✅ AI 就绪")

    # 续跑
    offset = 0
    total_batches = 0
    if RESUME_ENABLED:
        progress = load_progress()
        if progress and progress.get('current_file') == str(csv_path):
            offset = progress.get('next_offset', 0)
            total_batches = progress.get('total_batches', 0)
            if offset > 0:
                print(f"📌 续跑: offset={offset}")

    batch_count = 0
    total_processed = offset

    while True:
        if limit is not None and total_processed >= limit:
            print(f"\n🛑 已达 limit={limit}")
            break

        current_batch_size = batch_size
        if limit is not None:
            current_batch_size = min(batch_size, limit - total_processed)

        keywords, has_more = load_batch_from_csv(csv_path, total_processed, current_batch_size)
        if not keywords:
            print(f"\n✅ 全部处理完毕")
            break

        batch_label = _batch_label(total_processed, len(keywords))
        batch_count += 1
        total_batches += 1

        print(f"\n{'='*50}")
        print(f"📦 批次 #{total_batches}: {batch_label} ({len(keywords)} 个)")
        print(f"{'='*50}")

        existing_path = OUTPUT_DIR / f"final_results_batch_{batch_label}.json"
        if existing_path.exists():
            print(f"   ⏭️  已存在，跳过")
            total_processed += len(keywords)
            save_progress(str(csv_path), total_processed, total_batches, total_processed)
            if not has_more:
                break
            continue

        process_batch(keywords, client, batch_label, csv_path, len(keywords))

        total_processed += len(keywords)
        save_progress(str(csv_path), total_processed, total_batches, total_processed)

        if not has_more:
            break

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"✅ 完成！{batch_count} 批, {total_processed - offset} 个关键词, "
          f"{int(elapsed // 60)}分{int(elapsed % 60)}秒")
    print(f"📁 {OUTPUT_DIR}")
    print(f"{'='*60}")


# ==================== CLI ====================

def main():
    parser = argparse.ArgumentParser(description="V5 关键词分析 — 三阶段管道")
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--no-resume', action='store_true')
    args = parser.parse_args()

    global RESUME_ENABLED
    if args.no_resume:
        RESUME_ENABLED = False

    run(batch_size=args.batch_size, limit=args.limit)

if __name__ == '__main__':
    main()
