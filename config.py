# Webhook配置
import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 添加默认值和类型检查
WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')  # 设置默认空字符串

# 根据环境变量判断是否在Docker中运行
IS_DOCKER = os.getenv('IS_DOCKER', 'false').lower() == 'true'

# 根据运行环境选择代理地址
PROXY_URL = 'http://host.docker.internal:7890' if IS_DOCKER else 'http://127.0.0.1:7890'
USE_PROXY = True

# 文件路径配置
DATA_DIRS = {
    'prompts': 'prompts',           # 提示词保存目录
    'responses': 'responses',       # AI响应内容保存目录
    'advices': 'advices',           # AI建议保存目录
    'records': 'investment_records', # 投资建议记录保存目录
    'debug': 'debug_logs',          # 调试日志保存目录
    'data': 'data',                 # 市场数据保存目录
    'reports': 'reports'            # 报告保存目录
}

# 市场情绪指标配置
MARKET_SENTIMENT = {
    # API端点
    'binance_alpha_url': 'https://api.coinmarketcap.com/data-api/v3/cryptocurrency/listing',  # 币安Alpha项目列表API
}

# DeepSeek AI 配置
DEEPSEEK_AI = {
    'api_url': os.getenv('DEEPSEEK_API_URL', 'https://api.deepseek.com/v1/chat/completions'),
    'model': os.getenv('DEEPSEEK_MODEL', 'deepseek-reasoner'),
    'temperature': 0,
    'max_tokens': 4096,
    'top_p': 1.0,
    'stream': False
}
