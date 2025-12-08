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
from src.utils.discord_webhook import send_discord_message, send_discord_embed, DiscordColors

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
    dealer_accumulation_alerts = []  # 吸筹: 量增价平/小涨
    dealer_distribution_alerts = []  # 出货/洗盘: 量增价跌
    
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
        
        # 庄家行为检测逻辑
        # 最低交易量门槛: 24H > 2.4M
        MIN_VOLUME_24H = 2_400_000
        MIN_MARKET_CAP = 1_000_000
        
        is_accumulation = False
        
        if vol_change_24h > threshold and volume_24h >= MIN_VOLUME_24H and market_cap > MIN_MARKET_CAP:
            alert_data = {
                "symbol": symbol,
                "name": name,
                "vol_change": vol_change_24h,
                "price_change": price_change_24h,
                "volume": volume_24h,
                "market_cap": market_cap,
                "fdv": fullyDilluttedMarketCap
            }
            
            # 吸筹: 量增 + 价格不变或小涨 (-2% ~ +10%)
            if -2 <= price_change_24h <= 10:
                is_accumulation = True
                dealer_accumulation_alerts.append(alert_data)
            # 出货/洗盘: 量增 + 价格下跌 (< -2%)
            elif price_change_24h < -2:
                dealer_distribution_alerts.append(alert_data)

        if triggered:
            # 保存完整数据用于表格展示
            alert_info = {
                "symbol": symbol,
                "name": name,
                "change_24h": changes.get("24h", 0),
                "volume_24h": volume_24h,
                "is_accumulation": is_accumulation
            }
            alerts.append(alert_info)
    
    # 按24h变化率排序
    alerts.sort(key=lambda x: x["change_24h"], reverse=True)


    # 发送常规交易量异动警报
    if alerts:
        print(f"发现 {len(alerts)} 个交易量异动项目")
        if not debug_only:
            await _send_volume_alerts(alerts, threshold)
    else:
        print("未发现超过阈值的交易量变化")

    # 发送庄家吸筹警报 (量增价平/小涨)
    if dealer_accumulation_alerts:
        print(f"发现 {len(dealer_accumulation_alerts)} 个疑似庄家吸筹项目")
        if not debug_only:
            await _send_accumulation_alerts(dealer_accumulation_alerts)
    
    # 发送出货/洗盘警报 (量增价跌)
    if dealer_distribution_alerts:
        print(f"发现 {len(dealer_distribution_alerts)} 个疑似出货/洗盘项目")
        if not debug_only:
            await _send_distribution_alerts(dealer_distribution_alerts)
    
    return {
        "alerts": alerts,
        "triggered_count": len(alerts),
        "accumulation_count": len(dealer_accumulation_alerts),
        "distribution_count": len(dealer_distribution_alerts)
    }


def _format_number(num: float) -> str:
    """格式化数字，大数字用 K/M/B 表示"""
    if abs(num) >= 1_000_000_000:
        return f"{num / 1_000_000_000:.1f}B"
    elif abs(num) >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    elif abs(num) >= 1_000:
        return f"{num / 1_000:.1f}K"
    else:
        return f"{num:.0f}"


async def _send_volume_alerts(alerts: list[dict], threshold: float):
    """发送交易量警报消息到 Discord - 表格形式"""
    # 过滤最低交易量门槛
    MIN_VOLUME_24H = 2_400_000
    filtered_alerts = [a for a in alerts if a.get("volume_24h", 0) >= MIN_VOLUME_24H]
    
    if not filtered_alerts:
        print(f"过滤后无符合条件的交易量异动 (门槛: ${MIN_VOLUME_24H:,})")
        return
    
    # 分离涨跌
    gainers = [a for a in filtered_alerts if a["change_24h"] > 0]
    losers = [a for a in filtered_alerts if a["change_24h"] < 0]
    
    # 构建表格 - 使用代码块实现等宽对齐
    def build_table(items: list[dict]) -> str:
        if not items:
            return ""
        
        lines = []
        lines.append("```")
        lines.append(f"{'Symbol':<8} {'Name':<16} {'Vol%':>9} {'Volume':>9}")
        lines.append(f"{'-'*8} {'-'*16} {'-'*9} {'-'*9}")
        
        for item in items:
            symbol = item["symbol"][:8]
            name = item["name"][:16]
            change = f"{item['change_24h']:+.0f}%"
            volume = _format_number(item.get("volume_24h", 0))
            lines.append(f"{symbol:<8} {name:<16} {change:>9} {volume:>9}")
        
        lines.append("```")
        return "\n".join(lines)
    
    # 发送涨幅榜
    if gainers:
        table = build_table(gainers)
        await send_discord_embed(
            title=f"📈 交易量激增 ({len(gainers)}个)",
            description=f"**阈值:** Vol > +{threshold}% & Vol24h > $2.4M\n{table}",
            color=DiscordColors.GREEN,
            footer=f"监控时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await asyncio.sleep(0.3)
    
    # 发送跌幅榜
    if losers:
        table = build_table(losers)
        await send_discord_embed(
            title=f"📉 交易量骤降 ({len(losers)}个)",
            description=f"**阈值:** Vol < -{threshold}% & Vol24h > $2.4M\n{table}",
            color=DiscordColors.RED,
            footer=f"监控时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )


def _build_dealer_table(items: list[dict]) -> str:
    """构建庄家行为表格"""
    lines = ["```"]
    lines.append(f"{'Symbol':<8} {'Vol%':>7} {'Price%':>7} {'MCap':>8} {'Volume':>8}")
    lines.append(f"{'-'*8} {'-'*7} {'-'*7} {'-'*8} {'-'*8}")
    
    for item in items:
        symbol = item["symbol"][:8]
        vol_change = f"+{item['vol_change']:.0f}%"
        price_change = f"{item['price_change']:+.1f}%"
        mcap = _format_number(item["market_cap"])
        volume = _format_number(item["volume"])
        lines.append(f"{symbol:<8} {vol_change:>7} {price_change:>7} {mcap:>8} {volume:>8}")
    
    lines.append("```")
    return "\n".join(lines)


async def _send_accumulation_alerts(items: list[dict]):
    """发送庄家吸筹警报到 Discord - 量增价平/小涨"""
    # 按市值降序排列
    items_sorted = sorted(items, key=lambda x: x["market_cap"], reverse=True)
    
    table = _build_dealer_table(items_sorted)
    
    # Discord Embed description 限制 4096 字符
    if len(table) > 4000:
        batch_size = 20
        for i in range(0, len(items_sorted), batch_size):
            batch = items_sorted[i:i + batch_size]
            batch_table = _build_dealer_table(batch)
            batch_num = f" ({i // batch_size + 1}/{(len(items_sorted) - 1) // batch_size + 1})"
            
            await send_discord_embed(
                title=f"🐋 疑似吸筹{batch_num}",
                description=f"**特征:** 量增价平/小涨 (Vol↑ Price -2%~+10%)\n{batch_table}",
                color=DiscordColors.PURPLE,
                footer=f"监控时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await asyncio.sleep(0.3)
    else:
        await send_discord_embed(
            title=f"🐋 疑似吸筹 ({len(items)}个)",
            description=f"**特征:** 量增价平/小涨 (Vol↑ Price -2%~+10%)\n{table}",
            color=DiscordColors.PURPLE,
            footer=f"监控时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )


async def _send_distribution_alerts(items: list[dict]):
    """发送出货/洗盘警报到 Discord - 量增价跌"""
    # 按跌幅排序 (跌得最多的在前)
    items_sorted = sorted(items, key=lambda x: x["price_change"])
    
    table = _build_dealer_table(items_sorted)
    
    if len(table) > 4000:
        batch_size = 20
        for i in range(0, len(items_sorted), batch_size):
            batch = items_sorted[i:i + batch_size]
            batch_table = _build_dealer_table(batch)
            batch_num = f" ({i // batch_size + 1}/{(len(items_sorted) - 1) // batch_size + 1})"
            
            await send_discord_embed(
                title=f"⚠️ 疑似出货/洗盘{batch_num}",
                description=f"**特征:** 量增价跌 (Vol↑ Price < -2%)\n{batch_table}",
                color=DiscordColors.RED,
                footer=f"监控时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await asyncio.sleep(0.3)
    else:
        await send_discord_embed(
            title=f"⚠️ 疑似出货/洗盘 ({len(items)}个)",
            description=f"**特征:** 量增价跌 (Vol↑ Price < -2%)\n{table}",
            color=DiscordColors.RED,
            footer=f"监控时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )


async def _send_accumulation_alerts(items: list[dict]):
    """发送庄家吸筹警报到 Discord"""
    # 构建 Embed fields
    fields = []
    for item in items:
        field_value = (
            f"量变: **+{item['vol_change']:.1f}%** | 价变: **{item['price_change']:+.2f}%**\n"
            f"交易量: ${item['volume']:,.0f}\n"
            f"市值: ${item['market_cap']:,.0f} | FDV: ${item['fdv']:,.0f}"
        )
        fields.append({
            "name": f"🔹 {item['symbol']} - {item['name']}",
            "value": field_value,
            "inline": False
        })
    
    # Discord Embed 最多 25 个 fields，需要分批
    MAX_FIELDS = 25
    for i in range(0, len(fields), MAX_FIELDS):
        batch_fields = fields[i:i + MAX_FIELDS]
        batch_num = f" ({i // MAX_FIELDS + 1}/{(len(fields) - 1) // MAX_FIELDS + 1})" if len(fields) > MAX_FIELDS else ""
        
        await send_discord_embed(
            title=f"🐋 疑似庄家吸筹监控{batch_num}",
            description="**特征:** 交易量大增，价格波动小 (量增价平)",
            color=DiscordColors.PURPLE,
            fields=batch_fields,
            footer=f"监控时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        # 避免频率限制
        if i + MAX_FIELDS < len(fields):
            await asyncio.sleep(0.5)

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



