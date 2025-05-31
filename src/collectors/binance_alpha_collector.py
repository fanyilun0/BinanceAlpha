import os
import json
import logging
import requests
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from .base_collector import BaseDataCollector
from config import MARKET_SENTIMENT

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BinanceAlphaCollector(BaseDataCollector):
    """币安Alpha项目列表数据收集器"""
    
    def __init__(self, data_dir="data", proxy_url=None, use_proxy=True):
        """初始化币安Alpha项目列表数据收集器"""
        super().__init__(data_dir, proxy_url, use_proxy)
        self.data_file = os.path.join(data_dir, "binance_alpha_data.json")
        self.api_url = MARKET_SENTIMENT.get('binance_alpha_url', 'https://api.coinmarketcap.com/data-api/v3/cryptocurrency/listing')
    
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
            'aux': 'ath,atl,high24h,low24h,num_market_pairs,cmc_rank,date_added,tags,platform,max_supply,circulating_supply,self_reported_circulating_supply,self_reported_market_cap,total_supply,volume_7d,volume_30d',
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
    
    