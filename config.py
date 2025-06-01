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
    'all-platforms': 'advices/all-platforms', # 所有平台建议保存目录
    'records': 'investment_records', # 投资建议记录保存目录
    'debug': 'debug_logs',          # 调试日志保存目录
    'data': 'data',                 # 市场数据保存目录
    'symbols': 'symbols'            # 符号保存目录
}

# 区块链平台配置
BLOCKCHAIN_PLATFORMS = {
    "BNB Chain": ["BNB", "BSC", "BEP20", "BEP-20", "Binance Smart Chain", "币安智能链", "bnb-chain-ecosystem", "binance-chain"],
    "Solana": ["SOL", "Solana", "SPL", "索拉纳", "solana-ecosystem"], 
    "Ethereum": ["ETH", "ERC20", "Ethereum", "ERC-20", "ERC 20", "以太坊", "ethereum-ecosystem"],
    #"Base": ["Base", "Base-Ecosystem", "base-ecosystem"],
}

# 要查询的区块链平台
# 留空数组表示查询所有BLOCKCHAIN_PLATFORMS中定义的平台
# 填入平台名数组则只查询指定的平台，例如: ["Ethereum", "Solana"]
PLATFORMS_TO_QUERY = []

# 需要屏蔽的代币列表
# 可以使用符号(symbol)、名称(name)或ID进行匹配
# 例如: ["BTC", "Bitcoin", "ETH", "Ethereum"]
BLOCK_TOKEN_LIST = ["AITECH","BROCCOLI"]

# 市场情绪指标配置
MARKET_SENTIMENT = {
    # API端点
    'binance_alpha_url': 'https://api.coinmarketcap.com/data-api/v3/cryptocurrency/listing',  # 币安Alpha项目列表API
}

# DeepSeek AI 配置
DEEPSEEK_AI = {
    'api_url': os.getenv('DEEPSEEK_API_URL', 'https://api.deepseek.com/v1/chat/completions'),
    'model': os.getenv('DEEPSEEK_MODEL', 'deepseek-reasoner'),
    'api_key': os.getenv('DEEPSEEK_API_KEY', ''),
    'temperature': 0,
    'max_tokens': 32000,
    'top_p': 1.0,
    'stream': False,
    'timeout': int(os.getenv('DEEPSEEK_API_TIMEOUT', '600'))  # API请求超时时间(秒)
}
