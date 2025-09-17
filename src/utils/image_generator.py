"""
图片生成工具
用于将数据转换为图片格式
"""

import os
import io
import base64
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端
import pandas as pd
import numpy as np
from config import DATA_DIRS
from src.utils.binance_symbols import is_token_listed

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
    # 确保目录存在
    image_dir = os.path.join(DATA_DIRS.get('data', 'data'), 'images')
    os.makedirs(image_dir, exist_ok=True)
    
    # 准备数据
    data = []
    
    # 只处理最多max_items个项目
    for crypto in crypto_list[:max_items]:
        # 提取基本数据
        name = crypto.get("name", "未知")
        symbol = crypto.get("symbol", "未知")
        rank = crypto.get("cmcRank", "未知")
        chain = crypto.get("platform", {}).get("name", "未知")

        # 使用简化的函数直接检查symbol是否上线
        is_listed = is_token_listed(symbol)
        
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
            
        # 计算完全稀释估值(FDV)
        fdv = usd_quote.get("fullyDilluttedMarketCap", 0)
        
        # 计算MC/FDV比率
        mc_fdv_ratio = market_cap / fdv if fdv > 0 else 0

        # 计算VOL/MC比率
        vol_mc_ratio = volume_24h / market_cap if market_cap > 0 else 0
        
        # 数据格式化
        data.append({
            "排名": rank,
            "名称": name,
            "代码": symbol,
            "chain": chain,
            "是否上线": "是" if is_listed else "否",
            "价格($)": round(price, 4),
            "24h变化(%)": round(percent_change_24h, 2),
            "交易量(M$)": round(volume_24h / 1000000, 2),
            "市值(M$)": round(market_cap / 1000000, 2),
            "VOL/MC": round(vol_mc_ratio, 2),
            "FDV(M$)": round(fdv / 1000000, 2),
            "MC/FDV": round(mc_fdv_ratio, 2),
        })
    
    # 创建DataFrame
    df = pd.DataFrame(data)
    
    # 设置样式
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei']  # 设置中文字体
    plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
    
    # 根据数据量和列数调整图片尺寸
    rows = min(len(data), max_items)
    cols = len(df.columns)
    # 增加宽度以适应更多列
    fig_width = 18  # 调整宽度
    fig_height = 0.5 * rows + 3  # 基础高度加上每行高度
    
    # 创建图表
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    
    # 隐藏轴
    ax.axis('tight')
    ax.axis('off')
    
    # 添加标题
    plt.title(f'📈 Top 100 币安Alpha项目 (按市值排序) - {date}', 
              fontsize=16, fontweight='bold', pad=20)
    
    # 为变化列添加颜色映射
    cell_colors = []
    for i in range(len(df)):
        row_colors = ['white'] * len(df.columns)
        
        # 设置24h变化的颜色
        change_index = df.columns.get_loc("24h变化(%)")
        change_value = df.iloc[i, change_index]
        
        if change_value > 0:
            row_colors[change_index] = '#d8f3dc'  # 浅绿色
        elif change_value < 0:
            row_colors[change_index] = '#ffccd5'  # 浅红色
        
        # 设置"是否上线"列的颜色
        listing_index = df.columns.get_loc("是否上线")
        is_listed_value = df.iloc[i, listing_index]
        
        if is_listed_value == "是":
            row_colors[listing_index] = '#d8f3dc'  # 浅绿色
            
        cell_colors.append(row_colors)
    
    # 创建表格，调整列宽
    the_table = ax.table(
        cellText=df.values,
        colLabels=df.columns,
        cellLoc='center',
        loc='center',  # 可以尝试修改为'upper center'减少与标题的间距
        cellColours=cell_colors
    )
    
    # 设置表格样式
    the_table.auto_set_font_size(False)
    the_table.set_fontsize(11)  # 字体略小以适应更多列
    the_table.scale(1, 1.5)  # 调整表格比例
    
    # 调整列宽，使其适应列数增加的情况
    for i in range(len(df.columns)):
        the_table.auto_set_column_width([i])
    
    # 设置列标题行样式
    for i, key in enumerate(df.columns):
        cell = the_table[(0, i)]
        cell.set_text_props(weight='bold', color='white')
        cell.set_facecolor('#2a9d8f')
    
    # 保存图片，增加分辨率
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    image_path = os.path.join(image_dir, f"alpha_list_{timestamp}.png")
    # 减少图片边距，使得标题和表格间距更小
    plt.savefig(image_path, bbox_inches='tight', dpi=210, pad_inches=0)  # 减小pad_inches参数
    plt.close()
    
    # 返回图片路径和base64编码
    with open(image_path, "rb") as img_file:
        img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
    
    print(f"已生成Alpha项目表格图片: {image_path}")
    return image_path, img_base64


def create_top_vol_mc_ratio_image(crypto_list: List[Dict[str, Any]], date: str) -> Tuple[str, str]:
    """
    基于交易量/市值比值排序，创建前10个项目的表格图片
    
    Args:
        crypto_list: 加密货币项目列表
        date: 数据日期
        
    Returns:
        Tuple[str, str]: (图片路径, 图片base64编码)
    """
    # 确保目录存在
    image_dir = os.path.join(DATA_DIRS.get('data', 'data'), 'images')
    os.makedirs(image_dir, exist_ok=True)
    
    # 准备数据并计算 VOL/MC 比值
    data_with_ratio = []
    
    for crypto in crypto_list:
        # 提取基本数据
        name = crypto.get("name", "未知")
        symbol = crypto.get("symbol", "未知")
        rank = crypto.get("cmcRank", "未知")
        chain = crypto.get("platform", {}).get("name", "未知")

        # 使用简化的函数直接检查symbol是否上线
        is_listed = is_token_listed(symbol)
        
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
        
        # 只保留有效的 VOL/MC 比值数据
        if vol_mc_ratio > 0:
            data_with_ratio.append({
                "排名": rank,
                "名称": name,
                "代码": symbol,
                "chain": chain,
                "是否上线": "是" if is_listed else "否",
                "价格($)": round(price, 4),
                "24h变化(%)": round(percent_change_24h, 2),
                "交易量(M$)": round(volume_24h / 1000000, 2),
                "市值(M$)": round(market_cap / 1000000, 2),
                "VOL/MC": round(vol_mc_ratio, 2),
                "vol_mc_ratio_raw": vol_mc_ratio  # 用于排序的原始值
            })
    
    # 按 VOL/MC 比值递减排序，取前25个
    data_with_ratio.sort(key=lambda x: x["vol_mc_ratio_raw"], reverse=True)
    top_10_data = data_with_ratio[:25]
    
    # 移除排序用的原始值字段
    for item in top_10_data:
        del item["vol_mc_ratio_raw"]
    
    # 创建DataFrame
    df = pd.DataFrame(top_10_data)
    
    # 设置样式
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei']  # 设置中文字体
    plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
    
    # 根据数据量调整图片尺寸
    rows = len(top_10_data)
    fig_width = 18
    fig_height = 0.5 * rows + 3
    
    # 创建图表
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    
    # 隐藏轴
    ax.axis('tight')
    ax.axis('off')
    
    # 添加标题
    plt.title(f'📈 Top 25 高流动性项目 (VOL/MC排序) - {date}', 
              fontsize=16, fontweight='bold', pad=20)
    
    # 为变化列添加颜色映射
    cell_colors = []
    for i in range(len(df)):
        row_colors = ['white'] * len(df.columns)
        
        # 设置24h变化的颜色
        change_index = df.columns.get_loc("24h变化(%)")
        change_value = df.iloc[i, change_index]
        
        if change_value > 0:
            row_colors[change_index] = '#d8f3dc'  # 浅绿色
        elif change_value < 0:
            row_colors[change_index] = '#ffccd5'  # 浅红色
        
        # 设置"是否上线"列的颜色
        listing_index = df.columns.get_loc("是否上线")
        is_listed_value = df.iloc[i, listing_index]
        
        if is_listed_value == "是":
            row_colors[listing_index] = '#d8f3dc'  # 浅绿色
            
        # 设置VOL/MC比值的颜色渐变（前3名高亮）
        if i < 3:  # 前3名
            vol_mc_index = df.columns.get_loc("VOL/MC")
            row_colors[vol_mc_index] = '#fff3cd'  # 浅黄色高亮
            
        cell_colors.append(row_colors)
    
    # 创建表格
    the_table = ax.table(
        cellText=df.values,
        colLabels=df.columns,
        cellLoc='center',
        loc='center',
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
        cell.set_facecolor('#e76f51')  # 使用不同颜色区分
    
    # 保存图片
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    image_path = os.path.join(image_dir, f"top_vol_mc_ratio_{timestamp}.png")
    plt.savefig(image_path, bbox_inches='tight', dpi=210, pad_inches=0.1)
    plt.close()
    
    # 返回图片路径和base64编码
    with open(image_path, "rb") as img_file:
        img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
    
    print(f"已生成VOL/MC比值Top10项目表格图片: {image_path}")
    return image_path, img_base64 