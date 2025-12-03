import os
import json
import logging
import aiohttp
import traceback
import time
from datetime import datetime
from typing import Dict, Any, Optional

from config import MARKET_SENTIMENT

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BinanceAlphaCollector:
    """币安Alpha项目列表数据收集器"""
    
    def __init__(self, data_dir="data", proxy_url=None, use_proxy=True):
        """初始化币安Alpha项目列表数据收集器"""
        self.data_dir = data_dir
        self.data_file = os.path.join(data_dir, "binance_alpha_data.json")
        self.api_url = MARKET_SENTIMENT.get('binance_alpha_url')
        
        # 代理设置
        self.proxy = proxy_url
        self.use_proxy = use_proxy
        
        # 请求头
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        # 确保数据目录存在
        os.makedirs(data_dir, exist_ok=True)
    
    async def fetch_data(self, url, params=None, use_proxy=None):
        """通用数据获取方法，支持代理配置"""
        if use_proxy is None:
            use_proxy = self.use_proxy
            
        try:
            async with aiohttp.ClientSession(headers=self.headers) as session:
                if use_proxy and self.proxy:
                    logger.info(f"使用代理 {self.proxy} 请求 {url}")
                    async with session.get(url, params=params, proxy=self.proxy, timeout=30) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            logger.error(f"请求失败，状态码: {response.status}, URL: {url}")
                            return None
                else:
                    logger.info(f"不使用代理请求 {url}")
                    async with session.get(url, params=params, timeout=30) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            logger.error(f"请求失败，状态码: {response.status}, URL: {url}")
                            return None
        except Exception as e:
            logger.error(f"获取数据出错: {url}, 错误: {str(e)}")
            logger.debug(traceback.format_exc())
            return None
    
    def save_to_json(self, data, filename):
        """保存数据到JSON文件"""
        file_path = os.path.join(self.data_dir, filename)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            logger.info(f"数据已保存到: {file_path}")
            return True
        except Exception as e:
            logger.error(f"保存数据出错: {str(e)}")
            return False
    
    async def get_binance_alpha_data(self) -> Optional[Dict[str, Any]]:
        """获取币安Alpha项目列表数据"""
        logger.info("正在获取币安Alpha项目列表数据...")
        
        params = {
            'start': 1,
            'limit': 200,
            'sortBy': 'market_cap',
            'sortType': 'desc',
            'convert': 'USD,BTC,ETH',
            'cryptoType': 'all',
            'tagType': 'all',
            'audited': 'false',
            'aux': 'ath,atl,high24h,low24h,num_market_pairs,cmc_rank,date_added,tags,platform,max_supply,circulating_supply,self_reported_circulating_supply,self_reported_market_cap,total_supply,volume_7d,volume_30d,volume_change_24h,volume_change_7d,volume_change_30d',
            'tagSlugs': 'binance-alpha'
        }
        
        try:
            response_data = await self.fetch_data(self.api_url, params)
            
            if not response_data or 'data' not in response_data:
                logger.error("获取币安Alpha项目列表数据失败: 无效响应")
                return None
            
            # 提取币安Alpha项目列表数据
            alpha_data = response_data.get('data', {})
            
            # 添加时间戳
            timestamp = int(time.time())
            formatted_date = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
            
            # 格式化结果数据
            result = {
                "timestamp": timestamp,
                "date": formatted_date, 
                "data": alpha_data,
                "total_count": alpha_data.get("totalCount", 0),
                "source": "CoinMarketCap"
            }
            
            # 保存到文件
            self.save_to_json(result, "binance_alpha_data.json")
            
            return result
        
        except Exception as e:
            logger.error(f"获取币安Alpha项目列表数据出错: {str(e)}")
            return None