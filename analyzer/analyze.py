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
        base_url="https://open.bigmodel.cn/api/coding/paas/v4"  # GLM编码套餐专属端点
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

数据:
{keywords_text}

要求:
1. 将相似关键词归为同一主题
2. 每个主题至少3个关键词
3. 用英文命名主题，并提供中文翻译
4. 识别主题下的细分领域
5. 评分(0-100): 考虑关键词数量、增长率、相关度
6. 分析搜索意图(交易/信息/导航/商业调查)
7. 建议网站类型(工具站/内容站/导航站)
8. 建议变现方式(订阅/广告/联盟营销)

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
            {{"keyword": "ai image generator", "value": 1200, "type": "rising"}}
          ]
        }}
      ]
    }}
  ]
}}

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

        # 2. 加载历史数据
        print("\n📚 正在加载历史数据...")
        history_data = load_history_data(date_str)
        if history_data:
            print(f"✅ 找到 {len(history_data)} 天的历史数据")
        else:
            print("⚠️  未找到历史数据（首次运行）")

        # 3. 创建 AI 客户端
        print("\n🤖 正在连接 AI 服务...")
        client = create_client()
        print("✅ AI 客户端已就绪")

        # 4. AI 分析
        print(f"\n🧠 正在进行分析（共 {len(keywords)} 个关键词）...")
        themes = batch_analyze(keywords, client)

        print(f"\n🔗 正在合并和去重主题...")
        themes = merge_and_deduplicate_themes(themes)
        print(f"✅ 最终识别 {len(themes)} 个主题")

        # 5. 趋势分析
        print(f"\n📈 正在分析趋势...")
        trend_info = analyze_trends(themes, history_data)

        # 6. 保存报告
        print(f"\n💾 正在保存报告...")
        save_report(date_str, themes, trend_info, len(keywords))

        # 7. 清理旧数据
        print(f"\n🗑️  正在清理过期数据...")
        cleanup_old_data()

        # 完成
        print("\n" + "=" * 60)
        print("✅ 分析完成！")
        print("=" * 60)
        print(f"\n📄 查看报告: {ANALYSIS_DIR / f'report_{date_str}.md'}")
        print(f"📊 查看数据: {THEMES_RECENT_DIR / f'themes_{date_str}.json'}")

        # 显示前5个主题
        print(f"\n🏆 Top 5 高潜力主题:")
        for i, theme in enumerate(themes[:5], 1):
            print(f"  {i}. {theme.get('name_zh', theme['name'])} - {theme['score']}分")

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
