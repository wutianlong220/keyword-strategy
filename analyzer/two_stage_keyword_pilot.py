#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Three-stage keyword workflow pilot
Stage 1: intent classification (TRASH/SEED/PROJECT) 仅做意图分类
Stage 2: SERP evidence + project-fit validation 仅做赛道相关性校验
Stage 3: business-route judgment 仅对通过前两步的 PROJECT 词做变现路线判断
"""

import csv
import json
import re
from pathlib import Path
from datetime import datetime
from urllib.parse import quote_plus
import urllib.request

BASE_DIR = Path('/Volumes/Lexar/Github/keyword-strategy')
CSV_PATH = BASE_DIR / 'search-for-Google-keywords/daily_report_20260307.csv'
OUT_DIR = BASE_DIR / 'analysis/experiments'
OUT_DIR.mkdir(parents=True, exist_ok=True)

TRASH_PATTERNS = [
    r'\blogin\b', r'\bsign\s*up\b', r'\bdownload\b',
    r'\bfacebook\b', r'\bamazon\b', r'\bwhatsapp\b', r'\binstagram\b',
]

AI_POSITIVE_PATTERNS = [
    r'\bai\b', r'chatgpt', r'copilot', r'agent', r'automation',
    r'openai', r'claude', r'gemini', r'llm', r'prompt'
]

NON_AI_HINTS = [
    r'live action', r'anime', r'netflix', r'film', r'filme', r'movie',
    r'assistant manager', r'dental assistant', r'appreciation week',
    r'principal', r'salary', r'apply online', r'hall ticket', r'answer key',
]


def classify_stage1(related_kw: str):
    text = related_kw.lower().strip()
    wc = len([w for w in re.split(r'\s+', text) if w])

    for p in TRASH_PATTERNS:
        if re.search(p, text):
            return 'TRASH', '命中品牌/导航噪音词，商业价值低'

    if wc <= 2:
        return 'SEED', f'词组较短（{wc}词），搜索意图偏模糊'

    return 'PROJECT', f'词组较长（{wc}词），搜索意图更明确，可直接做内容页'


def fetch_duckduckgo_titles(query: str, topn: int = 5):
    url = f'https://html.duckduckgo.com/html/?q={quote_plus(query)}'
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36'
        }
    )
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


def stage2_serp_fit(related_kw: str, serp_titles):
    text = (related_kw + ' ' + ' '.join(serp_titles)).lower()

    has_ai = any(re.search(p, text) for p in AI_POSITIVE_PATTERNS)
    has_non_ai = any(re.search(p, text) for p in NON_AI_HINTS)

    if has_ai and not has_non_ai:
        fit = 'HIGH'
        reason = 'SERP显示与AI助手/自动化高度相关'
    elif has_ai and has_non_ai:
        fit = 'MEDIUM'
        reason = 'SERP存在混合意图，需进一步人工复核'
    else:
        fit = 'LOW'
        reason = 'SERP主要不在AI助手赛道，建议降级或剔除'

    return fit, reason


def stage3_business_route(related_kw: str):
    """仅第三阶段使用：评估变现路线（数字产品 / 站点）"""
    text = related_kw.lower()
    digital_product_patterns = [
        r'template', r'prompt', r'course', r'ebook', r'checklist', r'sop', r'guide'
    ]
    website_patterns = [
        r'generator', r'tool', r'calculator', r'assistant', r'summarizer', r'ai'
    ]

    d_hit = any(re.search(p, text) for p in digital_product_patterns)
    w_hit = any(re.search(p, text) for p in website_patterns)

    if d_hit and w_hit:
        return 'BOTH', '可同时走数字产品与工具站路线'
    if d_hit:
        return 'DIGITAL_PRODUCT', '更适合数字产品（模板/课程/电子书）'
    if w_hit:
        return 'WEBSITE', '更适合网站路线（工具站/内容站）'
    return 'UNSURE', '业务路线不明确，需人工判断'


def run(limit=10):
    rows = []
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, r in enumerate(reader):
            if i >= limit:
                break
            rows.append(r)

    output = []
    for idx, r in enumerate(rows, 1):
        related_kw = r['related_keywords'].strip()
        stage1_cat, stage1_reason = classify_stage1(related_kw)
        serp_titles = fetch_duckduckgo_titles(related_kw, topn=5)
        serp_fit, serp_reason = stage2_serp_fit(related_kw, serp_titles)

        stage3 = None
        if stage1_cat == 'PROJECT' and serp_fit in ('HIGH', 'MEDIUM'):
            route, route_reason = stage3_business_route(related_kw)
            stage3 = {'route': route, 'reason': route_reason}

        output.append({
            'index': idx,
            'keyword': r['keyword'].strip(),
            'related_keywords': related_kw,
            'value': int(r['value']),
            'type': r['type'].strip(),
            'stage1': {
                'category': stage1_cat,
                'reason': stage1_reason,
            },
            'stage2': {
                'serp_fit': serp_fit,
                'reason': serp_reason,
                'serp_titles': serp_titles,
            },
            'stage3': stage3,
            'final_suggestion': (
                '进入第三阶段评估（业务路线）' if stage3 is not None
                else '保留为SEED观察' if stage1_cat == 'SEED'
                else '剔除/TRASH'
            )
        })

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    json_path = OUT_DIR / f'two_stage_pilot_first10_{ts}.json'
    md_path = OUT_DIR / f'two_stage_pilot_first10_{ts}.md'

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({'source_csv': str(CSV_PATH), 'limit': limit, 'results': output}, f, ensure_ascii=False, indent=2)

    lines = [
        '# Two-Stage Keyword Pilot (First 10)',
        '',
        f'- Source: `{CSV_PATH}`',
        f'- Generated: {datetime.now().isoformat()}',
        '',
        '| # | related_keywords | stage1 | serp_fit | final_suggestion |',
        '|---:|---|---|---|---|',
    ]
    for item in output:
        lines.append(
            f"| {item['index']} | {item['related_keywords']} | {item['stage1']['category']} | {item['stage2']['serp_fit']} | {item['final_suggestion']} |"
        )

    lines.append('\n## Sample SERP Evidence')
    for item in output:
        lines.append(f"\n### {item['index']}. {item['related_keywords']}")
        lines.append(f"- Stage1: {item['stage1']['category']} ({item['stage1']['reason']})")
        lines.append(f"- Stage2: {item['stage2']['serp_fit']} ({item['stage2']['reason']})")
        if item['stage2']['serp_titles']:
            for t in item['stage2']['serp_titles'][:3]:
                lines.append(f"  - {t}")
        else:
            lines.append('  - (无SERP结果，建议人工复核)')

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(json_path)
    print(md_path)


if __name__ == '__main__':
    run(limit=10)
