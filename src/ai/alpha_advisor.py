import os
import json
import logging
import time
import random
from typing import Dict, Any, List, Optional
import requests
from datetime import datetime

from config import DEEPSEEK_AI, DATA_DIRS
# 导入调试保存功能
from ai.prompt import save_list_data_for_debug

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AlphaAdvisor:
    """币安Alpha项目投资顾问，基于当天数据生成建议"""
    
    def __init__(self):
        """初始化币安Alpha项目投资顾问"""
        self.api_url = DEEPSEEK_AI.get('api_url')
        self.model = DEEPSEEK_AI.get('model')
        self.api_key = os.getenv('DEEPSEEK_API_KEY', '')
        
        if not self.api_key:
            logger.warning("未设置DEEPSEEK_API_KEY环境变量")
    
    def _prepare_prompt(self, alpha_data: Dict[str, Any]) -> str:
        """准备提示词"""
        crypto_list = alpha_data.get("data", {}).get("cryptoCurrencyList", [])
        date = alpha_data.get("date", "")
        
        # 保存币安Alpha项目列表数据到本地文件以便调试
        save_list_data_for_debug(crypto_list[:20], "alpha_crypto_list")
        
        # 获取平台信息
        platform = None
        # 检查第一个项目的平台信息
        if crypto_list and len(crypto_list) > 0:
            first_crypto = crypto_list[0]
            platform_info = first_crypto.get("platform", {})
            if platform_info:
                platform = platform_info.get("name", "")
                
            # 如果platform为空，则尝试从tags中获取
            if not platform:
                tags = first_crypto.get("tags", [])
                platform_tags = [tag for tag in tags if isinstance(tag, str)]
                
                # 常见区块链平台关键词
                platform_keywords = {
                    "Ethereum": ["ETH", "ERC20", "Ethereum", "ERC-20"],
                    "Solana": ["SOL", "Solana", "SPL"], 
                    "BNB Chain": ["BNB", "BSC", "BEP20", "BEP-20", "Binance Smart Chain"],
                    "Polygon": ["MATIC", "Polygon"],
                    "Avalanche": ["AVAX", "Avalanche"]
                }
                
                # 尝试从tags中识别平台
                for p_name, keywords in platform_keywords.items():
                    if any(any(keyword.lower() in tag.lower() for tag in platform_tags) for keyword in keywords):
                        platform = p_name
                        break
        
        # 构建提示词
        if platform:
            prompt = f"""
作为加密货币分析师，请根据以下{platform}平台上的币安Alpha项目数据（{date}），分析并推荐3-5个最具投资潜力的代币。
分析应基于市值、价格走势、交易量等数据指标，考虑近期表现和未来潜力。请特别关注{platform}生态系统的独特优势和这些代币在该生态中的作用。

以下是当前{platform}平台上的币安Alpha列表中的前{min(len(crypto_list), 20)}个项目（按市值排序）：
"""
        else:
            prompt = f"""
作为加密货币分析师，请根据以下币安Alpha项目数据（{date}），分析并推荐3-5个最具投资潜力的代币。
分析应基于市值、价格走势、交易量等数据指标，考虑近期表现和未来潜力。

以下是当前币安Alpha列表中的前{min(len(crypto_list), 20)}个项目（按市值排序）：
"""
        
        # 添加加密货币数据
        for i, crypto in enumerate(crypto_list[:20], 1):
            name = crypto.get("name", "未知")
            symbol = crypto.get("symbol", "未知")
            rank = crypto.get("cmcRank", "未知")
            
            # 提取价格和价格变化数据（USD）
            quotes = crypto.get("quotes", [])
            usd_quote = next((q for q in quotes if q.get("name") == "USD"), {})
            
            price = usd_quote.get("price", 0)
            percent_change_24h = usd_quote.get("percentChange24h", 0)
            percent_change_7d = usd_quote.get("percentChange7d", 0)
            percent_change_30d = usd_quote.get("percentChange30d", 0)
            market_cap = usd_quote.get("marketCap", 0)
            fdv = price * crypto.get("totalSupply", 0)
            volume_24h = usd_quote.get("volume24h", 0)
            
            # 获取项目平台信息
            platform_info = crypto.get("platform", {})
            platform_name = platform_info.get("name", "") if platform_info else ""
            
            # 添加项目信息
            prompt += f"{i}. {name} ({symbol}):\n"
            prompt += f"   - 排名: {rank}\n"
            if platform_name:
                prompt += f"   - 平台: {platform_name}\n"
            prompt += f"   - 价格: ${price:.6f}\n"
            prompt += f"   - 24小时变化: {percent_change_24h:.2f}%\n"
            prompt += f"   - 7天变化: {percent_change_7d:.2f}%\n"
            prompt += f"   - 30天变化: {percent_change_30d:.2f}%\n"
            prompt += f"   - 市值: ${market_cap:.2f}\n"
            prompt += f"   - 完全稀释估值: ${fdv:.2f}\n"
            prompt += f"   - 24小时交易量: ${volume_24h:.2f}\n"
            
            # 添加项目标签信息
            tags = crypto.get("tags", [])
            if tags and isinstance(tags, list) and all(isinstance(tag, str) for tag in tags):
                prompt += f"   - 标签: {', '.join(tags[:5])}{' ...' if len(tags) > 5 else ''}\n"
                
            prompt += "\n"
        
        # 添加分析要求
        if platform:
            prompt += f"""
请基于以上{platform}平台上的币安Alpha项目数据，提供以下内容：

1. 3-5个推荐投资的{platform}平台代币，包括代币名称、代码和推荐理由
2. 每个代币的投资风险评估（低/中/高）
3. 建议的投资时间范围（短期/中期/长期）
4. 简要分析这些代币在{platform}生态系统中的作用和未来潜力
5. 简要总结当前{platform}平台币安Alpha项目的整体市场状况

分析应该简明扼要，重点突出，便于投资者快速理解和决策。
"""
        else:
            prompt += """
请基于以上数据，提供以下内容：

1. 3-5个推荐投资的代币，包括代币名称、代码和推荐理由
2. 每个代币的投资风险评估（低/中/高）
3. 建议的投资时间范围（短期/中期/长期）
4. 简要总结当前币安Alpha项目的整体市场状况

分析应该简明扼要，重点突出，便于投资者快速理解和决策。
"""
        
        return prompt
    
    def get_investment_advice(self, alpha_data: Dict[str, Any], max_retries=3, retry_delay=2.0, debug=True) -> Optional[str]:
        """获取投资建议
        
        Args:
            alpha_data: 币安Alpha项目数据
            max_retries: 最大重试次数
            retry_delay: 重试间隔时间（秒）
            debug: 是否启用调试模式，保存数据到文件
            
        Returns:
            生成的投资建议文本，如果生成失败则返回None
        """
        if not self.api_key:
            logger.error("未设置DEEPSEEK_API_KEY，无法获取AI建议")
            return None
        
        # 准备提示词
        prompt = self._prepare_prompt(alpha_data)
        
        # 保存提示词供调试
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        prompt_file = os.path.join(DATA_DIRS['prompts'], f"alpha_prompt_{timestamp}.txt")
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt)
        logger.info(f"已保存Alpha提示词到: {prompt_file}")
        
        # 准备API请求参数
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": DEEPSEEK_AI.get('temperature', 0),
            "max_tokens": DEEPSEEK_AI.get('max_tokens', 2048),
            "top_p": DEEPSEEK_AI.get('top_p', 1.0),
            "stream": DEEPSEEK_AI.get('stream', False)
        }
        
        # 尝试请求
        attempt = 0
        while attempt < max_retries:
            try:
                logger.info(f"正在请求AI建议，尝试 {attempt + 1}/{max_retries}")
                response = requests.post(self.api_url, headers=headers, json=payload, timeout=60)
                
                if response.status_code == 200:
                    result = response.json()
                    message = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return message
                else:
                    logger.error(f"API请求失败，状态码: {response.status_code}, 响应: {response.text}")
                    
            except Exception as e:
                logger.error(f"API请求过程中出错: {str(e)}")
            
            # 增加重试次数并等待
            attempt += 1
            if attempt < max_retries:
                delay = retry_delay * (1 + random.random())  # 添加随机抖动
                logger.info(f"等待 {delay:.2f} 秒后重试...")
                time.sleep(delay)
        
        logger.error(f"在 {max_retries} 次尝试后放弃获取AI建议")
        return None
    

        """获取模拟投资建议（当API不可用时使用）"""
        crypto_list = alpha_data.get("data", {}).get("cryptoCurrencyList", [])
        date = alpha_data.get("date", "")
        
        # 随机选择3-5个代币
        sample_size = min(random.randint(3, 5), len(crypto_list))
        selected_cryptos = random.sample(crypto_list[:20], sample_size)
        
        # 风险等级和投资期限选项
        risk_levels = ["低", "中", "高"]
        time_frames = ["短期", "中期", "长期"]
        
        # 构建模拟建议
        advice = f"# 币安Alpha项目投资建议 ({date})\n\n"
        advice += "## 推荐代币\n\n"
        
        for i, crypto in enumerate(selected_cryptos, 1):
            name = crypto.get("name", "未知")
            symbol = crypto.get("symbol", "未知")
            
            # 随机生成风险和期限
            risk = random.choice(risk_levels)
            timeframe = random.choice(time_frames)
            
            # 提取价格数据
            quotes = crypto.get("quotes", [])
            usd_quote = next((q for q in quotes if q.get("name") == "USD"), {})
            percent_change_24h = usd_quote.get("percentChange24h", 0)
            percent_change_7d = usd_quote.get("percentChange7d", 0)
            
            # 根据价格变化生成理由
            if percent_change_7d > 10:
                reason = f"近期强劲上涨趋势，7天内上涨{percent_change_7d:.2f}%"
            elif percent_change_7d > 0:
                reason = f"稳定增长，7天内上涨{percent_change_7d:.2f}%"
            elif percent_change_24h > 0:
                reason = f"24小时内呈现反弹趋势，上涨{percent_change_24h:.2f}%"
            else:
                reason = "当前价格具有较好的入场机会"
            
            advice += f"### {i}. {name} ({symbol})\n"
            advice += f"- **风险等级**: {risk}\n"
            advice += f"- **投资期限**: {timeframe}\n"
            advice += f"- **推荐理由**: {reason}\n\n"
        
        # 添加市场总结
        advice += "## 市场总结\n\n"
        
        # 计算市场整体涨跌情况
        positive_count = sum(1 for crypto in crypto_list[:20] if 
                            next((q.get("percentChange24h", 0) for q in crypto.get("quotes", []) if q.get("name") == "USD"), 0) > 0)
        positive_ratio = positive_count / min(20, len(crypto_list))
        
        if positive_ratio > 0.7:
            market_summary = "当前币安Alpha项目整体呈现强势上涨趋势，大部分代币表现积极。适合积极布局，但注意风险管理。"
        elif positive_ratio > 0.5:
            market_summary = "市场整体稳定向上，部分代币表现出色。建议选择性布局，关注基本面良好的项目。"
        elif positive_ratio > 0.3:
            market_summary = "市场呈现震荡态势，涨跌互现。建议谨慎投资，优先考虑具有实际应用场景的项目。"
        else:
            market_summary = "市场整体承压，多数代币呈下跌趋势。建议以观望为主，等待更好的入场时机。"
        
        advice += market_summary + "\n\n"
        advice += "**免责声明**: 以上建议仅供参考，不构成投资建议。投资前请进行充分的研究和风险评估。"
        
        return advice 