"""
加密货币数据格式化工具
用于统一处理加密货币数据的提取和格式化
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple


def extract_basic_info(crypto: Dict[str, Any]) -> Dict[str, Any]:
    """
    从加密货币数据中提取基本信息
    
    Args:
        crypto: 加密货币数据字典
        
    Returns:
        包含基本信息的字典
    """
    name = crypto.get("name", "未知")
    symbol = crypto.get("symbol", "未知")
    rank = crypto.get("cmcRank", "未知")
    
    # 提取价格和价格变化数据（USD）
    quotes = crypto.get("quotes", [])
    usd_quote = next((q for q in quotes if q.get("name") == "USD"), {})
    
    # 如果找不到名为"USD"的报价，尝试使用索引2（假设这是USD）
    if not usd_quote and len(quotes) > 2:
        usd_quote = quotes[2]
    
    price = usd_quote.get("price", 0)
    percent_change_24h = usd_quote.get("percentChange24h", 0)
    percent_change_7d = usd_quote.get("percentChange7d", 0)
    percent_change_30d = usd_quote.get("percentChange30d", 0)
    volume_24h = usd_quote.get("volume24h", 0)
    volume_7d = usd_quote.get("volume7d", 0)
    volume_30d = usd_quote.get("volume30d", 0)
    percentChange24h = usd_quote.get("percentChange24h", 0)
    percentChange7d = usd_quote.get("percentChange7d", 0)
    percentChange30d = usd_quote.get("percentChange30d", 0)
    # 计算市值
    market_cap = usd_quote.get("marketCap", 0)
    if market_cap == 0:
        market_cap = usd_quote.get("selfReportedMarketCap", 0)
    # 计算完全稀释估值(FDV)
    fdv = usd_quote.get("fullyDilluttedMarketCap", 0)
    # 添加除零检查
    mc_fdv_ratio = 0
    if fdv > 0:
        mc_fdv_ratio = market_cap / fdv
    
    # 获取项目平台信息
    platform_info = crypto.get("platform", {})
    platform_name = platform_info.get("name", "") if platform_info else ""
    
    # 获取项目标签
    tags = crypto.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        tags = []
    
    return {
        "name": name,
        "symbol": symbol,
        "rank": rank,
        "price": price,
        "percent_change_24h": percent_change_24h,
        "percent_change_7d": percent_change_7d, 
        "percent_change_30d": percent_change_30d,
        "market_cap": market_cap,
        "fdv": fdv,
        "mc_fdv_ratio": mc_fdv_ratio,
        "volume_24h": volume_24h,
        "volume_7d": volume_7d,
        "volume_30d": volume_30d,
        "percentChange24h": percentChange24h,
        "percentChange7d": percentChange7d,
        "percentChange30d": percentChange30d,
        "platform_name": platform_name,
        "tags": tags
    }


def format_project_detailed(crypto: Dict[str, Any]) -> str:
    """
    格式化项目信息为详细文本格式（适用于alpha_advisor.py）
    
    Args:
        crypto: 加密货币数据字典
        
    Returns:
        格式化后的文本
    """
    info = extract_basic_info(crypto)
    
    project_text = f"{info['name']} ({info['symbol']}):\n"
    #project_text += f"   - 排名: {info['rank']}\n"
    #project_text += f"   - 价格: ${info['price']:.6f}\n"
    project_text += f"   - 价格变化[权重35%]: 24h {info['percent_change_24h']:.2f}% | 7d {info['percent_change_7d']:.2f}% | 30d {info['percent_change_30d']:.2f}%\n"
    project_text += f"   - 交易量[权重45%]: 24h ${info['volume_24h']:.2f} | 7d ${info['volume_7d']:.2f} | 30d ${info['volume_30d']:.2f}\n"
    project_text += f"   - MC: ${info['market_cap']:.2f}\n"
    # 添加除零检查
    vol_mc_ratio = 0.0
    if info['market_cap'] > 0:
        vol_mc_ratio = info['volume_24h'] / info['market_cap']
    project_text += f"   - VOL/MC(24h): {vol_mc_ratio:.4f}\n"
    project_text += f"   - FDV: ${info['fdv']:.2f}\n"
    project_text += f"   - MC/FDV[权重10%]: {info['mc_fdv_ratio']:.2f}\n"
    # 添加项目标签信息（可能与监管合规性相关）
    if info['tags']:
        project_text += f"   - 标签[权重10%]: {', '.join(info['tags'][:5])}{' ...' if len(info['tags']) > 5 else ''}\n"
    
    return project_text


def format_project_summary(crypto: Dict[str, Any], index: int, listing_status: Optional[Dict[str, bool]] = None) -> str:
    """
    格式化项目信息为简洁摘要（适用于main.py）
    
    Args:
        crypto: 加密货币数据字典
        index: 项目序号
        listing_status: 币安上市状态信息
        
    Returns:
        格式化后的文本
    """
    info = extract_basic_info(crypto)
    symbol = info['symbol']
    
    # 添加涨跌图标
    change_emoji = "🟢" if info['percent_change_24h'] >= 0 else "🔴"
    
    message = f"{index}. {info['name']} ({symbol}) - 📈 CMC排名: {info['rank']}\n"
    
    # 添加上市状态信息
    if listing_status and listing_status.get("is_listed") == True:
        message += f"   🔔 已上线币安\n"
    
    message += f"   💰 价格: ${info['price']:.2f}, 24h变化: {change_emoji} {info['percent_change_24h']:.2f}%\n"
    
    # 安全计算市值和FDV（百万美元）
    market_cap_m = 0
    if info['market_cap'] > 0:
        market_cap_m = info['market_cap'] / 1000000
    
    fdv_m = 0
    if info['fdv'] > 0:
        fdv_m = info['fdv'] / 1000000
    
    message += f"   💎 MC: ${market_cap_m:.2f}M, FDV: ${fdv_m:.2f}M, MC/FDV: {info['mc_fdv_ratio']:.2f}\n"
    
    return message


def save_crypto_data(data: List[Dict[str, Any]], filename: Optional[str] = None, prefix: str = "crypto_data") -> str:
    """
    保存加密货币数据到本地文件
    
    Args:
        data: 加密货币数据列表
        filename: 文件名，如果为None则自动生成
        prefix: 文件名前缀
        
    Returns:
        保存的文件路径
    """
    if filename is None:
        # 创建一个基于时间的文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.json"
    
    # 确保数据目录存在
    data_dir = os.path.join(os.getcwd(), "data")
    os.makedirs(data_dir, exist_ok=True)
    
    file_path = os.path.join(data_dir, filename)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    return file_path


def load_crypto_data(filename: str) -> List[Dict[str, Any]]:
    """
    从本地文件加载加密货币数据
    
    Args:
        filename: 文件名
        
    Returns:
        加密货币数据列表
    """
    file_path = os.path.join(os.getcwd(), "data", filename)
    
    if not os.path.exists(file_path):
        return []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_crypto_list_by_platform(platform_projects: Dict[str, List[Dict[str, Any]]], base_dir: Optional[str] = None) -> Dict[str, str]:
    """
    将按平台分类的加密货币列表保存到对应文件
    
    Args:
        platform_projects: 按平台分类的加密货币列表字典
        base_dir: 基础目录，默认为当前目录下的data目录
        
    Returns:
        Dict[str, str]: 每个平台对应的保存路径
    """
    if base_dir is None:
        base_dir = os.path.join(os.getcwd(), "data", "platforms")
    
    # 确保目录存在
    os.makedirs(base_dir, exist_ok=True)
    
    # 获取当前时间戳
    timestamp = datetime.now().strftime("%Y%m%d")
    
    # 保存每个平台的项目列表
    saved_paths = {}
    for platform, projects in platform_projects.items():
        if not projects:  # 跳过空列表
            continue
            
        # 格式化平台名称用于文件名
        platform_str = platform.lower().replace(' ', '_')
        filename = f"{platform_str}_projects_{timestamp}.json"
        file_path = os.path.join(base_dir, filename)
        
        # 保存项目列表
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump({
                "platform": platform,
                "date": timestamp,
                "count": len(projects),
                "projects": projects
            }, f, ensure_ascii=False, indent=2)
        
        saved_paths[platform] = file_path
    
    return saved_paths


def load_crypto_list_by_platform(platform: str, date: Optional[str] = None, base_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    加载特定平台的加密货币列表
    
    Args:
        platform: 平台名称
        date: 日期字符串（格式：YYYYMMDD），如果为None则加载最新的
        base_dir: 基础目录，默认为当前目录下的data/platforms目录
        
    Returns:
        List[Dict[str, Any]]: 平台对应的加密货币列表
    """
    if base_dir is None:
        base_dir = os.path.join(os.getcwd(), "data", "platforms")
    
    # 确保目录存在
    if not os.path.exists(base_dir):
        return []
    
    # 格式化平台名称
    platform_str = platform.lower().replace(' ', '_')
    
    # 如果指定了日期，直接尝试加载
    if date:
        filename = f"{platform_str}_projects_{date}.json"
        file_path = os.path.join(base_dir, filename)
        
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("projects", [])
        return []
    
    # 如果没有指定日期，查找最新的文件
    files = [f for f in os.listdir(base_dir) if f.startswith(f"{platform_str}_projects_") and f.endswith(".json")]
    
    if not files:
        return []
    
    # 按文件名排序（日期在文件名中，所以按文件名排序等同于按日期排序）
    files.sort(reverse=True)
    latest_file = os.path.join(base_dir, files[0])
    
    with open(latest_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        return data.get("projects", []) 