"""
提示词生成模块 - 为DeepSeek API提供各种场景的提示词模板

此模块负责:
1. 定义和管理各种提示词模板
2. 根据输入参数生成格式化的提示词
3. 提供通用的提示词工具函数
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Union

# 导入配置
from config import DATA_DIRS

# 设置日志
logger = logging.getLogger(__name__)

def save_list_data_for_debug(data_list: List[Dict], filename_prefix: str = "list_data") -> str:
    """保存列表数据到文件用于调试
    
    Args:
        data_list: 要保存的数据列表
        filename_prefix: 文件名前缀
        
    Returns:
        保存的文件路径
    """
    try:
        # 确保调试目录存在
        data_dir = DATA_DIRS.get('data', 'data')
        os.makedirs(data_dir, exist_ok=True)
        
        # 创建文件名
        timestamp = datetime.now().strftime('%Y%m%d')
        filename = f"{filename_prefix}_{timestamp}.json"
        file_path = os.path.join(data_dir, filename)
        
        # 保存到文件
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data_list, f, ensure_ascii=False, indent=2)
        
        logger.info(f"已保存列表数据到: {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"保存列表数据时出错: {str(e)}")
        return "" 