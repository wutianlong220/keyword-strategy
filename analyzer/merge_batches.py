#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并批次 JSON 文件
用于在 API 失败或返回非 JSON 格式导致分析中断时，手动修复 raw.txt 或 JSON 文件后，将它们合并为最终的分析报告。

用法: python merge_batches.py <日期字符串> [原始关键词总数]
例如: python merge_batches.py 20260303 500
"""

import sys
import json
from pathlib import Path

# 添加当前目录到路径
base_dir = Path(__file__).parent.parent
sys.path.append(str(base_dir / "analyzer"))

from analyze import merge_and_deduplicate_themes, analyze_trends, load_history_data, save_report

def main():
    if len(sys.argv) < 2:
        print("❌ 请提供批次对应的日期字符串！")
        print("用法: python merge_batches.py <日期字符串> [关键词总数]")
        print("例如: python merge_batches.py 20260303 500")
        sys.exit(1)
        
    date_str = sys.argv[1]
    keywords_count = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    
    data_dir = base_dir / "data"
    batch_dir = data_dir / f"batches_{date_str}"
    
    if not batch_dir.exists():
        print(f"❌ 找不到批次目录: {batch_dir}")
        sys.exit(1)
        
    print(f"📁 正在读取目录下的分批结果: {batch_dir.name}")
    
    all_themes = []
    success_count = 0
    
    # 按照名称排序读取所有 _parsed.json 文件
    json_files = sorted(list(batch_dir.glob("batch_*_parsed.json")))
    
    if not json_files:
        print(f"⚠️ 在该目录下没有找到任何 batch_*_parsed.json 文件。")
        print(f"你可以将 batch_*_raw_XXXX.txt 中正确的 JSON 结构手动保存为 _parsed.json 文件。")
        sys.exit(1)
        
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # 有些模型可能返回字典里包着 themes
                if isinstance(data, dict):
                    themes = data.get("themes", [])
                elif isinstance(data, list):
                    themes = data
                else:
                    themes = []
                    
                all_themes.extend(themes)
                success_count += 1
                print(f"  ✅ 成功读取 {json_file.name} (包含 {len(themes)} 个主题)")
        except Exception as e:
            print(f"  ❌ 读取或解析 {json_file.name} 失败: {e}")
            
    if not all_themes:
        print("❌ 未找到任何有效的主题数据，无法生成最终报告！")
        sys.exit(1)
        
    print(f"\n🔗 正在合并和去重共 {len(all_themes)} 个主题 (来自 {success_count} 个批次)...")
    themes = merge_and_deduplicate_themes(all_themes)
    print(f"✅ 最终识别整理 {len(themes)} 个主题")
    
    print("\n📈 正在分析趋势...")
    history_data = load_history_data(date_str)
    trend_info = analyze_trends(themes, history_data)
    
    print("\n💾 正在保存最终报告...")
    save_report(date_str, themes, trend_info, keywords_count)
    
    print("\n" + "=" * 60)
    print("✅ 分析合并完成！")
    print("=" * 60)

if __name__ == "__main__":
    main()
