# AI 加密货币投资顾问模块

本模块提供基于大型语言模型的加密货币投资分析和建议功能。通过整合历史价格数据、AHR999指数和恐惧贪婪指数，使用DeepSeek R1模型生成专业的投资建议。

## 模块结构

```
ai/
├── __init__.py         # 包初始化文件
├── deepseek.py         # DeepSeek API核心接口
├── advisor.py          # 投资顾问实现
├── cli.py              # 命令行工具
├── README.md           # 本文档
└── docs/               # 文档目录
    ├── example_deepseek_prompt.md     # 示例提示词
    ├── example_deepseek_response.md   # 示例响应
    ├── crypto_ai_advisor_summary.md   # 功能总结
    └── ai_implementation_complete.md  # 实现详情
```

## 主要组件

### 1. DeepSeekAPI (`deepseek.py`)

提供与DeepSeek R1模型的API交互功能：

```python
from ai.deepseek import DeepseekAPI

# 初始化API
api = DeepseekAPI(api_key="your_api_key")

# 生成文本
response = api.generate_text("你好，请介绍一下比特币")

# 获取投资建议
advice = api.generate_investment_advice(data_json_string)
```

### 2. 投资顾问 (`advisor.py`)

提供加密货币投资建议功能：

```python
from ai.advisor import DeepseekAdvisor

# 初始化顾问
advisor = DeepseekAdvisor()

# 获取投资建议
advice = advisor.get_investment_advice("data/daily_data.json", months=6)
```

### 3. 命令行工具 (`cli.py`)

提供命令行界面：

```bash
# 基本用法
python -m ai.cli

# 指定API密钥
python -m ai.cli -k your_api_key

# 显示投资建议
python -m ai.cli -v

# 查看帮助
python -m ai.cli --help
```

## 使用示例

### 从Python代码调用

```python
import os
from ai import DeepseekAdvisor

# 设置API密钥
os.environ["DEEPSEEK_API_KEY"] = "your_api_key"

# 初始化顾问
advisor = DeepseekAdvisor()

# 获取投资建议
advice = advisor.get_investment_advice("data/daily_data.json")
print(advice)
```

### 从命令行调用

```bash
# 设置API密钥
set DEEPSEEK_API_KEY=your_api_key  # Windows
# 或
export DEEPSEEK_API_KEY=your_api_key  # Linux/macOS

# 运行工具
python -m ai.cli
```

## 配置参数

### 环境变量

- `DEEPSEEK_API_KEY`: DeepSeek API密钥
- `DEEPSEEK_API_URL`: 自定义API URL（可选）

### 命令行参数

- `-k/--api-key`: 指定API密钥
- `-u/--api-url`: 指定API URL
- `-i/--input-file`: 指定历史数据文件
- `-o/--output-file`: 指定输出文件
- `-m/--months`: 指定分析月数
- `-v/--view`: 在终端显示生成的建议
- `-s/--skip-reorganize`: 跳过数据重组步骤

## 文档

- [示例提示词](docs/example_deepseek_prompt.md): DeepSeek模型提示词示例
- [示例响应](docs/example_deepseek_response.md): DeepSeek模型响应示例
- [功能总结](docs/crypto_ai_advisor_summary.md): AI顾问功能总结
- [实现详情](docs/ai_implementation_complete.md): 实现详细信息 