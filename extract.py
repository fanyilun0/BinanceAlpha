import re
import os
import json

# 从symbol.json文件读取已上币的symbol列表
try:
    with open('symbols/symbol.json', 'r', encoding='utf-8') as f:
        listed_symbols = json.load(f)
    print(f"已加载 {len(listed_symbols)} 个已上币的symbol")
except Exception as e:
    print(f"加载symbol.json失败: {e}，将使用默认空列表")
    listed_symbols = []

# 转换为大写集合，提高查询效率
listed_symbols_set = {s.upper() for s in listed_symbols}

folder = 'advices/all-platforms'
# 匹配带序号和不带序号的格式
pattern = re.compile(r'(?:\d+\.\s+)?\*\*([^\*]+?)\s*\(([A-Z0-9\-]+)\)\*\*')

result = {}
symbol_map = {}  # 用于记录符号到标准化名称的映射
symbol_listed_status = {}  # 记录每个符号是否已上币

for filename in os.listdir(folder):
    if filename.endswith('.md'):
        with open(os.path.join(folder, filename), 'r', encoding='utf-8') as f:
            content = f.read()
            matches = pattern.findall(content)
            for name, symbol in matches:
                # 标准化名称和符号（去除多余空格和开头的序号）
                name = name.strip()
                # 移除名称开头可能存在的序号格式 (如 "1. ", "2. " 等)
                name = re.sub(r'^\d+\.\s+', '', name)
                symbol = symbol.strip().upper()  # 将符号转为大写以避免大小写问题
                
                # 检查符号是否已上币
                is_listed = symbol in listed_symbols_set
                symbol_listed_status[symbol] = is_listed
                
                # 如果这个符号已经出现过，使用第一次遇到的项目名称作为标准名称
                if symbol in symbol_map:
                    standardized_name = symbol_map[symbol]
                else:
                    standardized_name = name
                    symbol_map[symbol] = name
                
                # 创建统一格式的键
                key = f"{standardized_name} ({symbol})"
                result[key] = result.get(key, 0) + 1

# 按出现次数降序排列
sorted_results = sorted(result.items(), key=lambda x: -x[1])

# 输出到控制台
for k, v in sorted_results:
    symbol = k.split('(')[1].split(')')[0]  # 提取括号内的符号
    listed_mark = "🔔 " if symbol_listed_status.get(symbol, False) else ""
    print(f"{listed_mark}{k}: {v} 次")

# 生成Markdown格式的内容
import datetime
current_date = datetime.datetime.now().strftime("%Y-%m-%d")
md_content = f"# Alpha项目频率统计 ({current_date})\n\n"
md_content += "| 项目名称 | 出现次数 | 状态 |\n"
md_content += "| --- | --- | --- |\n"

for k, v in sorted_results:
    symbol = k.split('(')[1].split(')')[0]  # 提取括号内的符号
    listed_status = "🔔 已上币" if symbol_listed_status.get(symbol, False) else ""
    md_content += f"| {k} | {v} | {listed_status} |\n"

# 保存到all-platforms目录
output_file = os.path.join(folder, "alpha_frequency_stats.md")
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(md_content)

print(f"\n统计结果已保存到: {output_file}")