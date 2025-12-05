"""
交易量变化监控模块

监控加密货币交易量变化并发送警报
独立模块，可直接运行
"""

import asyncio
import logging
import json
import os
import sys
from datetime import datetime

# 添加项目根目录 to sys.path so we can import config and webhook
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.append(project_root)

from config import DATA_DIRS
from webhook import send_message_async

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('volume_monitor.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

def load_data():
    """加载最新的Binance Alpha数据"""
    data_file = os.path.join(project_root, 'data', 'binance_alpha_data.json')
    if not os.path.exists(data_file):
        logger.error(f"数据文件不存在: {data_file}")
        return None
    
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except Exception as e:
        logger.error(f"加载数据失败: {str(e)}")
        return None

async def monitor_volume_changes(crypto_list=None, threshold=50.0, debug_only=False):
    """监控交易量变化并发送警报
    
    Args:
        crypto_list: 加密货币项目列表 (如果为None，则从文件加载)
        threshold: 变化阈值（百分比），默认50%
        debug_only: 是否仅调试模式（不发送消息）
        
    Returns:
        dict: 包含监控结果的字典
    """
    print(f"=== 监控交易量变化 (阈值: {threshold}%) ===\n")
    
    if crypto_list is None:
        data = load_data()
        if not data:
            print("无法加载数据，监控终止")
            return {"alerts": [], "triggered_count": 0}
        crypto_list = data.get("data", {}).get("cryptoCurrencyList", [])
        print(f"已加载 {len(crypto_list)} 个项目数据")

    alerts = []
    dealer_accumulation_alerts = []
    
    for crypto in crypto_list:
        symbol = crypto.get("symbol", "Unknown")
        name = crypto.get("name", "Unknown")
        
        # 获取USD报价
        quotes = crypto.get("quotes", [])
        usd_quote = next((q for q in quotes if q.get("name") == "USD"), {})
        if not usd_quote and len(quotes) > 2:
            usd_quote = quotes[2]
            
        if not usd_quote:
            continue

        # 检查各个时间段的变化
        # API主要返回 volumePercentChange (24h)
        vol_change_24h = usd_quote.get("volumePercentChange", 0)
        if vol_change_24h == 0:
            vol_change_24h = usd_quote.get("volumeChange24h", 0)
            
        price_change_24h = usd_quote.get("percentChange24h", 0)
        volume_24h = usd_quote.get("volume24h", 0)
        market_cap = usd_quote.get("marketCap", 0)
        fullyDilluttedMarketCap = usd_quote.get("fullyDilluttedMarketCap", 0)

        changes = {
            "24h": vol_change_24h,
            "7d": usd_quote.get("volumeChange7d", 0),
            "30d": usd_quote.get("volumeChange30d", 0)
        }
        
        triggered = []
        for period, change in changes.items():
            if abs(change) >= threshold:
                # 添加涨跌箭头
                arrow = "↑" if change > 0 else "↓"
                triggered.append(f"{arrow}{period}: {change:+.1f}%")
        
        # 庄家吸筹逻辑: 交易量大增，但价格变化不大 (底部吸筹)
        # 条件: 
        # 1. 24h交易量激增 (> 50%)
        # 2. 价格波动较小 (|24h涨跌幅| < 10%)
        # 3. 市值不能太小 (可选，例如 > 100k)
        is_accumulation = False
        MAX_PRICE_CHANGE = 10
        MIN_MARKET_CAP = 1_000_000
        if vol_change_24h > threshold and abs(price_change_24h) < MAX_PRICE_CHANGE and usd_quote.get('marketCap',0) > MIN_MARKET_CAP:
             is_accumulation = True
             dealer_accumulation_alerts.append({
                 "symbol": symbol,
                 "name": name,
                 "vol_change": vol_change_24h,
                 "price_change": price_change_24h,
                 "volume": volume_24h,
                 "market_cap": market_cap,
                 "fdv": fullyDilluttedMarketCap
             })

        if triggered:
            # 使用更简洁的格式，一行显示
            # 获取24h变化率用于排序
            alert_info = {
                "line": f"【{symbol}】{name}: " + " | ".join(triggered),
                "change_24h": changes.get("24h", 0),
                "is_accumulation": is_accumulation
            }
            alerts.append(alert_info)
    
    # 按24h变化率排序
    alerts.sort(key=lambda x: x["change_24h"], reverse=True)


    # 发送常规交易量异动警报
    if alerts:
        alert_lines = [a["line"] for a in alerts]
        
        print(f"发现 {len(alerts)} 个交易量异动项目")
        if not debug_only:
            await _send_volume_alerts(alert_lines, threshold)
    else:
        print("未发现超过阈值的交易量变化")

    # 发送庄家吸筹警报 (单独推送)
    if dealer_accumulation_alerts:
        print(f"发现 {len(dealer_accumulation_alerts)} 个疑似庄家吸筹项目")
        if not debug_only:
            await _send_accumulation_alerts(dealer_accumulation_alerts)
    
    return {
        "alerts": alerts,
        "triggered_count": len(alerts),
        "accumulation_count": len(dealer_accumulation_alerts)
    }


async def _send_volume_alerts(alerts, threshold):
    """发送交易量警报消息"""
    # 构建消息 - 使用更清晰的文本格式
    header = f"📊 交易量异动监控\n阈值: >{threshold}% | 数量: {len(alerts)}个\n"
    message = header + "\n".join(alerts)
    await send_message_async(message, msg_type="text")

async def _send_accumulation_alerts(items):
    """发送庄家吸筹警报"""
    header = "🐋 疑似庄家吸筹监控 (量增价平)\n"
    
    lines = []
    for item in items:
        line = (f"【{item['symbol']}】{item['name']}\n"
                f"  量变: +{item['vol_change']:.1f}%\n"
                f"  价变: {item['price_change']:+.2f}%\n"
                f"  交易量: ${item['volume']:,.0f}\n"
                f"  市值: ${item['market_cap']:,.0f}\n"
                f"  FDV: ${item['fdv']:,.0f}\n")
        lines.append(line)
    message = header + "\n".join(lines) 
    await send_message_async(message, msg_type="text")

async def get_volume_statistics(crypto_list):
    """获取交易量统计信息 (保留原有功能)"""
    total_volume_24h = 0
    volume_changes = []
    
    for crypto in crypto_list:
        quotes = crypto.get("quotes", [])
        usd_quote = next((q for q in quotes if q.get("name") == "USD"), {})
        if not usd_quote and len(quotes) > 2:
            usd_quote = quotes[2]
        
        volume_24h = usd_quote.get("volume24h", 0)
        vol_change = usd_quote.get("volumePercentChange", 0)
        
        total_volume_24h += volume_24h
        if vol_change != 0:
            volume_changes.append({
                "symbol": crypto.get("symbol", "Unknown"),
                "name": crypto.get("name", "Unknown"),
                "volume_24h": volume_24h,
                "change_24h": vol_change
            })
    
    # 按涨幅排序
    volume_changes.sort(key=lambda x: x["change_24h"], reverse=True)
    
    return {
        "total_volume_24h": total_volume_24h,
        "top_gainers": volume_changes[:10] if volume_changes else [],
        "top_losers": volume_changes[-10:][::-1] if volume_changes else [],
        "average_change": sum(v["change_24h"] for v in volume_changes) / len(volume_changes) if volume_changes else 0
    }

async def main():
    """独立运行入口"""
    import argparse
    parser = argparse.ArgumentParser(description="交易量监控工具")
    parser.add_argument("--threshold", type=float, default=50.0, help="交易量变化阈值 (%)")
    parser.add_argument("--debug", action="store_true", help="调试模式，不发送消息")
    args = parser.parse_args()
    
    await monitor_volume_changes(threshold=args.threshold, debug_only=args.debug)

if __name__ == "__main__":
    asyncio.run(main())



