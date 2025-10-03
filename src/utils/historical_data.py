import asyncio
import os
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from ..collectors import BinanceAlphaCollector
from config import PROXY_URL, USE_PROXY

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BinanceAlphaDataCollector:
    """币安Alpha数据收集器，专注于获取当前币安Alpha项目数据"""
    
    def __init__(self, data_dir="data"):
        """初始化币安Alpha数据收集器"""
        self.data_dir = data_dir
        self.data_file = os.path.join(data_dir, "binance_alpha_data.json")
        
        # 确保数据目录存在
        os.makedirs(data_dir, exist_ok=True)
        
        # 初始化币安Alpha项目收集器
        self.binance_alpha_collector = BinanceAlphaCollector(data_dir, proxy_url=PROXY_URL, use_proxy=USE_PROXY)
    
    async def collect_current_data(self) -> Dict[str, Any]:
        """收集当前币安Alpha数据"""
        logger.info("开始收集当前币安Alpha数据...")
        
        # 获取币安Alpha数据
        binance_alpha_data = await self.binance_alpha_collector.get_binance_alpha_data()
        
        if not binance_alpha_data:
            logger.error("获取币安Alpha数据失败")
            return {}
        
        # 保存数据
        self.save_data(binance_alpha_data)
        
        return binance_alpha_data
    
    def save_data(self, data: Dict[str, Any]) -> bool:
        """保存币安Alpha数据"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            logger.info(f"币安Alpha数据已保存到: {self.data_file}")
            return True
        except Exception as e:
            logger.error(f"保存币安Alpha数据出错: {str(e)}")
            return False
    
    def load_data(self) -> Optional[Dict[str, Any]]:
        """加载币安Alpha数据"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"从本地文件加载币安Alpha数据: {self.data_file}")
                return data
            else:
                logger.warning(f"币安Alpha数据文件不存在: {self.data_file}")
                return None
        except Exception as e:
            logger.error(f"加载币安Alpha数据出错: {str(e)}")
            return None
    
    async def get_latest_data(self) -> Dict[str, Any]:
        """获取最新的币安Alpha数据（每次都从API获取最新数据）
        
        Returns:
            最新的币安Alpha数据
        """
        logger.info("获取最新的币安Alpha数据")
        return await self.collect_current_data()