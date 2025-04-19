import aiohttp
import json
import os
import logging
import traceback
from datetime import datetime
import time

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BaseDataCollector:
    """基础数据收集器，提供通用的数据获取和存储功能"""
    
    def __init__(self, data_dir="data", proxy_url=None, use_proxy=True):
        """初始化基础数据收集器"""
        # 设置数据目录
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        
        # 代理设置
        self.proxy = proxy_url
        self.use_proxy = use_proxy
        
        # 请求头
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
    
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
    
    def load_from_json(self, filename):
        """从JSON文件加载数据"""
        file_path = os.path.join(self.data_dir, filename)
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"从{file_path}加载了数据")
                return data
            else:
                logger.warning(f"文件不存在: {file_path}")
                return None
        except Exception as e:
            logger.error(f"加载数据出错: {str(e)}")
            return None
    
    def is_data_expired(self, data, timestamp_key="last_updated", hours=24):
        """检查数据是否过期"""
        if not data or timestamp_key not in data:
            return True
            
        last_updated = data[timestamp_key]
        current_time = int(time.time())
        return (current_time - last_updated) >= hours * 60 * 60 