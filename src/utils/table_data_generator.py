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


# 定义表格列配置
TABLE_COLUMNS = {
    "alpha_list": {
        "columns": ["排名", "名称", "代码", "chain", "合约", "价格($)", "24h变化(%)", "交易量(M$)", "市值(M$)", "VOL/MC", "FDV(M$)", "MC/FDV"],
        "include_fdv": True,
        "title": "币安Alpha项目列表"
    },
    "vol_mc_ratio": {
        "columns": ["排名", "名称", "代码", "chain", "合约", "价格($)", "24h变化(%)", "交易量(M$)", "市值(M$)", "VOL/MC"],
        "include_fdv": False,
        "title": "高流动性项目 (VOL/MC排序)"
    },
    "gainers_losers": {
        "columns": ["排名", "名称", "代码", "chain", "合约", "价格($)", "24h变化(%)", "交易量(M$)", "市值(M$)", "VOL/MC"],
        "include_fdv": False,
        "title": "涨跌幅榜"
    },
    "top_gainers": {
        "columns": ["排名", "名称", "代码", "chain", "合约", "价格($)", "24h变化(%)", "交易量(M$)", "市值(M$)", "VOL/MC"],
        "include_fdv": False,
        "title": "涨幅榜 (24h涨跌幅排序)"
    },
    "top_losers": {
        "columns": ["排名", "名称", "代码", "chain", "合约", "价格($)", "24h变化(%)", "交易量(M$)", "市值(M$)", "VOL/MC"],
        "include_fdv": False,
        "title": "跌幅榜 (24h涨跌幅排序)"
    }
}


def export_table_data(
    crypto_list: List[Dict[str, Any]], 
    table_type: str,
    date: str,
    max_items: Optional[int] = None,
    output_dir: Optional[str] = None
) -> str:
    """
    导出表格数据为JSON文件
    
    Args:
        crypto_list: 加密货币项目列表
        table_type: 表格类型（alpha_list, vol_mc_ratio, gainers_losers, top_gainers, top_losers）
        date: 数据日期
        max_items: 最大项目数量，None表示使用默认值
        output_dir: 输出目录，默认使用 DATA_DIRS['data']
        
    Returns:
        str: 输出文件路径
    """
    # 获取表格配置
    if table_type not in TABLE_COLUMNS:
        raise ValueError(f"不支持的表格类型: {table_type}，支持的类型: {list(TABLE_COLUMNS.keys())}")
    
    config = TABLE_COLUMNS[table_type]
    include_fdv = config["include_fdv"]
    title = config["title"]
    
    # 确定输出目录
    if output_dir is None:
        output_dir = os.path.join(DATA_DIRS.get('data', 'data'), 'tables')
    os.makedirs(output_dir, exist_ok=True)
    
    # 提取并处理数据
    data_list = []
    for crypto in crypto_list:
        crypto_data = _extract_crypto_data(crypto, include_fdv=include_fdv)
        data_list.append(crypto_data)
    
    # 根据表格类型进行特殊处理
    if table_type == "vol_mc_ratio":
        # 按 VOL/MC 比值递减排序
        data_list = [d for d in data_list if d.get("VOL/MC", 0) > 0]
        data_list.sort(key=lambda x: x.get("VOL/MC", 0), reverse=True)
        if max_items is None:
            max_items = 100
            
    elif table_type == "gainers_losers":
        # 分离涨幅和跌幅数据
        gainers = [d for d in data_list if d.get("24h变化(%)", 0) > 0]
        losers = [d for d in data_list if d.get("24h变化(%)", 0) < 0]
        neutral = [d for d in data_list if d.get("24h变化(%)", 0) == 0]
        
        gainers.sort(key=lambda x: x.get("24h变化(%)", 0), reverse=True)
        losers.sort(key=lambda x: x.get("24h变化(%)", 0))
        
        if max_items is None:
            max_items = 100
        
        half_items = max_items // 2
        top_gainers = gainers[:half_items]
        top_losers = losers[:half_items]
        
        # 如果数据不足，用对方补充
        if len(top_gainers) < half_items and len(losers) > half_items:
            top_losers = losers[:max_items - len(top_gainers)]
        elif len(top_losers) < half_items and len(gainers) > half_items:
            top_gainers = gainers[:max_items - len(top_losers)]
        
        data_list = top_gainers + top_losers
        
        # 如果总数据不足，添加零增长的数据
        if len(data_list) < max_items and neutral:
            data_list.extend(neutral[:max_items - len(data_list)])
            
    elif table_type == "top_gainers":
        # 按24h变化递减排序
        data_list.sort(key=lambda x: x.get("24h变化(%)", 0), reverse=True)
        if max_items is None:
            max_items = 50
            
    elif table_type == "top_losers":
        # 按24h变化递增排序
        data_list.sort(key=lambda x: x.get("24h变化(%)", 0))
        if max_items is None:
            max_items = 50
    else:
        # alpha_list 默认按市值排序（原始顺序）
        if max_items is None:
            max_items = 100
    
    # 限制数据量
    data_list = data_list[:max_items]
    
    # 准备输出数据
    output_data = {
        "type": table_type,
        "title": title,
        "date": date,
        "timestamp": datetime.now().strftime('%Y%m%d%H%M%S'),
        "total_count": len(data_list),
        "columns": config["columns"],
        "data": data_list
    }
    
    # 生成文件名
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    filename = f"{table_type}_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    
    # 保存文件
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"已生成表格数据文件: {filepath}")
    return filepath


def export_all_table_types(
    crypto_list: List[Dict[str, Any]], 
    date: str,
    output_dir: Optional[str] = None
) -> Dict[str, str]:
    """
    导出所有类型的表格数据
    
    Args:
        crypto_list: 加密货币项目列表
        date: 数据日期
        output_dir: 输出目录
        
    Returns:
        Dict[str, str]: 表格类型到文件路径的映射
    """
    results = {}
    
    for table_type in TABLE_COLUMNS.keys():
        try:
            filepath = export_table_data(
                crypto_list=crypto_list,
                table_type=table_type,
                date=date,
                output_dir=output_dir
            )
            results[table_type] = filepath
        except Exception as e:
            print(f"导出 {table_type} 表格数据失败: {e}")
            results[table_type] = None
    
    return results


def get_latest_table_data(table_type: str, data_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    获取最新的表格数据
    
    Args:
        table_type: 表格类型
        data_dir: 数据目录，默认使用 DATA_DIRS['data']/tables
        
    Returns:
        Dict[str, Any]: 表格数据，如果不存在则返回None
    """
    if data_dir is None:
        data_dir = os.path.join(DATA_DIRS.get('data', 'data'), 'tables')
    
    if not os.path.exists(data_dir):
        return None
    
    # 查找该类型的所有文件
    files = [f for f in os.listdir(data_dir) 
             if f.startswith(f"{table_type}_") and f.endswith(".json")]
    
    if not files:
        return None
    
    # 按文件名排序（时间戳在文件名中）
    files.sort(reverse=True)
    latest_file = os.path.join(data_dir, files[0])
    
    # 读取文件
    with open(latest_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return data


