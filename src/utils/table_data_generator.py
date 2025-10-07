"""
表格数据生成工具
用于将加密货币数据导出为JSON格式供前端渲染
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from config import DATA_DIRS
from src.utils.image_generator import _extract_crypto_data


# 定义统一的表格列配置（与图片列保持一致）
TABLE_COLUMNS = ["排名", "名称", "代码", "chain", "合约", "价格($)", "24h变化(%)", "交易量(M$)", "市值(M$)", "VOL/MC", "FDV(M$)", "MC/FDV"]


def export_table_data(
    crypto_list: List[Dict[str, Any]], 
    date: str,
    max_items: Optional[int] = None,
    output_dir: Optional[str] = None
) -> str:
    """
    导出表格数据为JSON文件（统一格式，包含所有列）
    
    Args:
        crypto_list: 加密货币项目列表
        date: 数据日期
        max_items: 最大项目数量，默认为100
        output_dir: 输出目录，默认使用 DATA_DIRS['data']/tables
        
    Returns:
        str: 输出文件路径
    """
    # 确定输出目录
    if output_dir is None:
        output_dir = os.path.join(DATA_DIRS.get('data', 'data'), 'tables')
    os.makedirs(output_dir, exist_ok=True)
    
    # 设置默认最大项目数
    if max_items is None:
        max_items = 100
    
    # 提取并处理数据（包含所有FDV数据）
    data_list = []
    for crypto in crypto_list[:max_items]:
        crypto_data = _extract_crypto_data(crypto, include_fdv=True)
        data_list.append(crypto_data)
    
    # 准备输出数据
    output_data = {
        "title": f"币安Alpha项目列表 - {date}",
        "date": date,
        "timestamp": datetime.now().strftime('%Y%m%d%H%M%S'),
        "total_count": len(data_list),
        "columns": TABLE_COLUMNS,
        "data": data_list
    }
    
    # 生成文件名
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    filename = f"alpha_table_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    
    # 保存文件
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"已生成表格数据文件: {filepath}")
    return filepath




def get_latest_table_data(data_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    获取最新的表格数据
    
    Args:
        data_dir: 数据目录，默认使用 DATA_DIRS['data']/tables
        
    Returns:
        Dict[str, Any]: 表格数据，如果不存在则返回None
    """
    if data_dir is None:
        data_dir = os.path.join(DATA_DIRS.get('data', 'data'), 'tables')
    
    if not os.path.exists(data_dir):
        return None
    
    # 查找所有表格文件
    files = [f for f in os.listdir(data_dir) 
             if f.startswith("alpha_table_") and f.endswith(".json")]
    
    if not files:
        return None
    
    # 按文件名排序（时间戳在文件名中）
    files.sort(reverse=True)
    latest_file = os.path.join(data_dir, files[0])
    
    # 读取文件
    with open(latest_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return data


