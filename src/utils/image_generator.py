"""
图片生成工具
用于将数据转换为图片格式
"""

import os
import io
import base64
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Callable
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端
import pandas as pd
import numpy as np
from config import DATA_DIRS
from src.utils.binance_symbols import is_token_listed, check_futures_listing


def _extract_crypto_data(crypto: Dict[str, Any], include_fdv: bool = True) -> Dict[str, Any]:
    """
    从加密货币数据中提取关键信息
    
    Args:
        crypto: 单个加密货币的原始数据
        include_fdv: 是否包含 FDV 和 MC/FDV 比率数据
        
    Returns:
        Dict[str, Any]: 提取并格式化后的数据字典
    """
    # 提取基本数据
    name = crypto.get("name", "未知")
    symbol = crypto.get("symbol", "未知")
    rank = crypto.get("cmcRank", "未知")
    chain = crypto.get("platform", {}).get("name", "未知")
    
    # 检查是否上线现货
    is_listed = is_token_listed(symbol)
    
    # 检查合约交易对
    futures_info = check_futures_listing(symbol)
    has_futures = futures_info.get("has_futures", False)
    
    # 提取价格和价格变化数据（USD）
    quotes = crypto.get("quotes", [])
    usd_quote = next((q for q in quotes if q.get("name") == "USD"), {})
    
    # 如果找不到名为"USD"的报价，尝试使用索引2（假设这是USD）
    if not usd_quote and len(quotes) > 2:
        usd_quote = quotes[2]
    
    # 提取数据
    price = usd_quote.get("price", 0)
    percent_change_24h = usd_quote.get("percentChange24h", 0)
    volume_24h = usd_quote.get("volume24h", 0)
    
    # 计算市值
    market_cap = usd_quote.get("marketCap", 0)
    if market_cap == 0:
        market_cap = usd_quote.get("selfReportedMarketCap", 0)
    
    # 计算VOL/MC比率
    vol_mc_ratio = volume_24h / market_cap if market_cap > 0 else 0
    
    # 基础数据
    data = {
        "排名": rank,
        "名称": name,
        "代码": symbol,
        "chain": chain,
        "现货": "是" if is_listed else "否",
        "合约": "是" if has_futures else "否",
        "价格($)": round(price, 4),
        "24h变化(%)": round(percent_change_24h, 2),
        "交易量(M$)": round(volume_24h / 1000000, 2),
        "市值(M$)": round(market_cap / 1000000, 2),
        "VOL/MC": round(vol_mc_ratio, 2),
    }
    
    # 如果需要包含 FDV 数据
    if include_fdv:
        fdv = usd_quote.get("fullyDilluttedMarketCap", 0)
        mc_fdv_ratio = market_cap / fdv if fdv > 0 else 0
        data["FDV(M$)"] = round(fdv / 1000000, 2)
        data["MC/FDV"] = round(mc_fdv_ratio, 2)
    
    return data


def _apply_cell_colors(df: pd.DataFrame, highlight_top_vol_mc: bool = False) -> List[List[str]]:
    """
    为表格单元格应用颜色映射
    
    Args:
        df: 数据框
        highlight_top_vol_mc: 是否高亮显示前3名的 VOL/MC 数值
        
    Returns:
        List[List[str]]: 单元格颜色列表
    """
    cell_colors = []
    for i in range(len(df)):
        row_colors = ['white'] * len(df.columns)
        
        # 设置24h变化的颜色 - 使用阈值区间
        if "24h变化(%)" in df.columns:
            change_index = df.columns.get_loc("24h变化(%)")
            change_value = df.iloc[i, change_index]
            
            # 根据涨跌幅度使用不同颜色
            if change_value >= 50:
                row_colors[change_index] = '#00b050'  # 暴涨：深绿色
            elif change_value >= 20:
                row_colors[change_index] = '#92d050'  # 大涨：中绿色
            elif change_value > 0:
                row_colors[change_index] = '#d8f3dc'  # 小涨：浅绿色
            elif change_value <= -50:
                row_colors[change_index] = '#c00000'  # 暴跌：深红色
            elif change_value <= -20:
                row_colors[change_index] = '#ff6b6b'  # 大跌：中红色
            elif change_value < 0:
                row_colors[change_index] = '#ffccd5'  # 小跌：浅红色
        
        # 设置"现货"列的颜色
        if "现货" in df.columns:
            spot_index = df.columns.get_loc("现货")
            is_spot_listed = df.iloc[i, spot_index]
            
            if is_spot_listed == "是":
                row_colors[spot_index] = '#d8f3dc'  # 浅绿色
        
        # 设置"合约"列的颜色
        if "合约" in df.columns:
            futures_index = df.columns.get_loc("合约")
            has_futures_value = df.iloc[i, futures_index]
            
            if has_futures_value == "是":
                row_colors[futures_index] = '#e0f7fa'  # 浅蓝色
        
        # 设置VOL/MC比值的颜色渐变（前3名高亮）
        if highlight_top_vol_mc and i < 3 and "VOL/MC" in df.columns:
            vol_mc_index = df.columns.get_loc("VOL/MC")
            row_colors[vol_mc_index] = '#fff3cd'  # 浅黄色高亮
        
        cell_colors.append(row_colors)
    
    return cell_colors


def create_base_image_options(
    data: List[Dict[str, Any]], 
    title: str,
    filename_prefix: str,
    header_color: str = '#2a9d8f',
    highlight_top_vol_mc: bool = False
) -> Tuple[str, str]:
    """
    创建基础表格图片的通用函数
    
    该函数封装了图片生成的公共逻辑，包括：
    - 设置 matplotlib 样式
    - 创建 DataFrame 和表格
    - 应用颜色映射
    - 保存图片并返回路径和 base64 编码
    
    Args:
        data: 格式化后的数据列表
        title: 图片标题
        filename_prefix: 文件名前缀（如 'alpha_list' 或 'top_vol_mc_ratio'）
        header_color: 表头背景颜色（默认为青绿色）
        highlight_top_vol_mc: 是否高亮显示前3名的 VOL/MC 数值（默认为 False）
        
    Returns:
        Tuple[str, str]: (图片路径, 图片base64编码)
    """
    # 确保目录存在
    image_dir = DATA_DIRS.get('images', 'images')
    os.makedirs(image_dir, exist_ok=True)
    
    # 创建DataFrame
    df = pd.DataFrame(data)
    
    # 设置样式
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei']
    plt.rcParams['axes.unicode_minus'] = False
    
    # 根据数据量和列数调整图片尺寸
    rows = len(data)
    fig_width = 18
    fig_height = 0.5 * rows + 1
    
    # 创建图表
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    
    # 隐藏轴
    ax.axis('tight')
    ax.axis('off')
    
    # 添加标题 - 向下移动并减少与表格的间距
    plt.title(title, fontsize=16, fontweight='bold', pad=10, y=0.98)
    
    # 应用颜色映射
    cell_colors = _apply_cell_colors(df, highlight_top_vol_mc)
    
    # 创建表格
    the_table = ax.table(
        cellText=df.values,
        colLabels=df.columns,
        cellLoc='center',
        loc='upper center',
        cellColours=cell_colors
    )
    
    # 设置表格样式
    the_table.auto_set_font_size(False)
    the_table.set_fontsize(11)
    the_table.scale(1, 1.5)
    
    # 调整列宽
    for i in range(len(df.columns)):
        the_table.auto_set_column_width([i])
    
    # 设置列标题行样式
    for i, key in enumerate(df.columns):
        cell = the_table[(0, i)]
        cell.set_text_props(weight='bold', color='white')
        cell.set_facecolor(header_color)
    
    # 保存图片
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    image_path = os.path.join(image_dir, f"{filename_prefix}_{timestamp}.png")
    plt.savefig(image_path, bbox_inches='tight', dpi=210, pad_inches=0)
    plt.close()
    
    # 返回图片路径和base64编码
    with open(image_path, "rb") as img_file:
        img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
    
    print(f"已生成表格图片: {image_path}")
    return image_path, img_base64

def create_alpha_table_image(crypto_list: List[Dict[str, Any]], date: str, 
                            max_items: int = 100) -> Tuple[str, str]:
    """
    将币安Alpha项目列表转换为表格图片
    
    Args:
        crypto_list: 加密货币项目列表
        date: 数据日期
        max_items: 最大项目数量
        
    Returns:
        Tuple[str, str]: (图片路径, 图片base64编码)
    """
    # 准备数据 - 只处理最多max_items个项目
    data = [_extract_crypto_data(crypto, include_fdv=True) 
            for crypto in crypto_list[:max_items]]
    
    # 生成图片标题
    title = f'Top {max_items} 币安Alpha项目 (按市值排序) - {date}'
    
    # 调用基础函数生成图片
    return create_base_image_options(
        data=data,
        title=title,
        filename_prefix='alpha_list',
        header_color='#2a9d8f',
        highlight_top_vol_mc=False
    )


def create_top_vol_mc_ratio_image(crypto_list: List[Dict[str, Any]], date: str, max_items: int = 100) -> Tuple[str, str]:
    """
    基于交易量/市值比值排序，创建前25个项目的表格图片
    
    Args:
        crypto_list: 加密货币项目列表
        date: 数据日期
        
    Returns:
        Tuple[str, str]: (图片路径, 图片base64编码)
    """
    # 准备数据并计算 VOL/MC 比值（不包含 FDV 数据）
    data_with_ratio = []
    
    for crypto in crypto_list:
        crypto_data = _extract_crypto_data(crypto, include_fdv=False)
        # 只保留有效的 VOL/MC 比值数据
        if crypto_data["VOL/MC"] > 0:
            crypto_data["vol_mc_ratio_raw"] = crypto_data["VOL/MC"]  # 用于排序的原始值
            data_with_ratio.append(crypto_data)
    
    # 按 VOL/MC 比值递减排序，取前25个
    data_with_ratio.sort(key=lambda x: x["vol_mc_ratio_raw"], reverse=True)
    top_data = data_with_ratio[:max_items]
    
    # 移除排序用的原始值字段
    for item in top_data:
        del item["vol_mc_ratio_raw"]
    
    # 生成图片标题
    title = f'Top {max_items} 高流动性项目 (VOL/MC排序) - {date}'
    
    # 调用基础函数生成图片
    return create_base_image_options(
        data=top_data,
        title=title,
        filename_prefix='top_vol_mc_ratio',
        header_color='#e76f51',
        highlight_top_vol_mc=True
    )


def create_top_gainers_image(crypto_list: List[Dict[str, Any]], date: str, max_items: int = 50) -> Tuple[str, str]:
    """
    基于24h涨跌幅排序，创建涨幅最大的项目表格图片
    
    Args:
        crypto_list: 加密货币项目列表
        date: 数据日期
        max_items: 最大显示项目数
        
    Returns:
        Tuple[str, str]: (图片路径, 图片base64编码)
    """
    # 准备数据（不包含 FDV 数据）
    data_with_change = []
    
    for crypto in crypto_list:
        crypto_data = _extract_crypto_data(crypto, include_fdv=False)
        # 保留所有数据，包括负增长的
        crypto_data["change_raw"] = crypto_data["24h变化(%)"]  # 用于排序的原始值
        data_with_change.append(crypto_data)
    
    # 按24h变化递减排序，取前N个
    data_with_change.sort(key=lambda x: x["change_raw"], reverse=True)
    top_data = data_with_change[:max_items]
    
    # 移除排序用的原始值字段
    for item in top_data:
        del item["change_raw"]
    
    # 生成图片标题
    title = f'Top {max_items} 涨幅榜 (24h涨跌幅排序) - {date}'
    
    # 调用基础函数生成图片
    return create_base_image_options(
        data=top_data,
        title=title,
        filename_prefix='top_gainers',
        header_color='#2ecc71',  # 绿色主题
        highlight_top_vol_mc=False
    )


def create_top_losers_image(crypto_list: List[Dict[str, Any]], date: str, max_items: int = 50) -> Tuple[str, str]:
    """
    基于24h涨跌幅排序，创建跌幅最大的项目表格图片
    
    Args:
        crypto_list: 加密货币项目列表
        date: 数据日期
        max_items: 最大显示项目数
        
    Returns:
        Tuple[str, str]: (图片路径, 图片base64编码)
    """
    # 准备数据（不包含 FDV 数据）
    data_with_change = []
    
    for crypto in crypto_list:
        crypto_data = _extract_crypto_data(crypto, include_fdv=False)
        # 保留所有数据
        crypto_data["change_raw"] = crypto_data["24h变化(%)"]  # 用于排序的原始值
        data_with_change.append(crypto_data)
    
    # 按24h变化递增排序（从最负到最正），取前N个
    data_with_change.sort(key=lambda x: x["change_raw"])
    top_data = data_with_change[:max_items]
    
    # 移除排序用的原始值字段
    for item in top_data:
        del item["change_raw"]
    
    # 生成图片标题
    title = f'Top {max_items} 跌幅榜 (24h涨跌幅排序) - {date}'
    
    # 调用基础函数生成图片
    return create_base_image_options(
        data=top_data,
        title=title,
        filename_prefix='top_losers',
        header_color='#e74c3c',  # 红色主题
        highlight_top_vol_mc=False
    )


def create_gainers_losers_image(crypto_list: List[Dict[str, Any]], date: str, max_items: int = 100) -> Tuple[str, str]:
    """
    基于24h涨跌幅排序，创建涨跌幅榜图片（从高到低排序）
    
    Args:
        crypto_list: 加密货币项目列表
        date: 数据日期
        max_items: 最大显示项目数
        
    Returns:
        Tuple[str, str]: (图片路径, 图片base64编码)
    """
    # 准备数据（不包含 FDV 数据）
    data_with_change = []
    
    for crypto in crypto_list:
        crypto_data = _extract_crypto_data(crypto, include_fdv=False)
        # 保留所有数据，包括正负增长
        crypto_data["change_raw"] = crypto_data["24h变化(%)"]  # 用于排序的原始值
        data_with_change.append(crypto_data)
    
    # 按24h变化递减排序（从最高涨幅到最大跌幅），取前N个
    data_with_change.sort(key=lambda x: x["change_raw"], reverse=True)
    top_data = data_with_change[:max_items]
    
    # 移除排序用的原始值字段
    for item in top_data:
        del item["change_raw"]
    
    # 生成图片标题
    title = f'Top {max_items} 涨跌幅榜 (24h涨跌幅排序) - {date}'
    
    # 调用基础函数生成图片
    return create_base_image_options(
        data=top_data,
        title=title,
        filename_prefix='gainers_losers',
        header_color='#3498db',  # 蓝色主题（中性色）
        highlight_top_vol_mc=False
    ) 