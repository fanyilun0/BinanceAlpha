import re
import os

spots = [
    'ONDO',
    'KMNO'
]

folder = 'advices/all-platforms'
# 匹配带序号和不带序号的格式
pattern = re.compile(r'(?:\d+\.\s+)?\*\*([^\*]+?)\s*\(([A-Z0-9\-]+)\)\*\*')

result = {}
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
                symbol = symbol.strip()
                
                # 如果symbol在spots列表中，则跳过
                if symbol in spots:
                    continue
                
                # 创建统一格式的键
                key = f"{name} ({symbol})"
                result[key] = result.get(key, 0) + 1

# 按出现次数降序排列
sorted_results = sorted(result.items(), key=lambda x: -x[1])

# 输出到控制台
for k, v in sorted_results:
    print(f"{k}: {v} 次")

# 生成Markdown格式的内容
current_date = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
md_content = f"# Alpha项目频率统计 ({current_date})\n\n"
md_content += "| 项目名称 | 出现次数 |\n"
md_content += "| --- | --- |\n"

for k, v in sorted_results:
    md_content += f"| {k} | {v} |\n"

# 保存到all-platforms目录
output_file = os.path.join(folder, "alpha_frequency_stats.md")
with open(output_file, 'w', encoding='utf-8') as f:
    f.write(md_content)

print(f"\n统计结果已保存到: {output_file}")