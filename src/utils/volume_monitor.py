"""
交易量变化监控模块

监控加密货币交易量变化并发送警报
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


async def monitor_volume_changes(crypto_list, threshold=50.0, debug_only=False):
    """监控交易量变化并发送警报
    
    Args:
        crypto_list: 加密货币项目列表
        threshold: 变化阈值（百分比），默认50%
        debug_only: 是否仅调试模式（不发送消息）
        
    Returns:
        dict: 包含监控结果的字典
            - alerts: 警报列表
            - triggered_count: 触发警报的项目数量
    """
    print(f"=== 监控交易量变化 (阈值: {threshold}%) ===\n")
    
    alerts = []
    
    for crypto in crypto_list:
        symbol = crypto.get("symbol", "Unknown")
        name = crypto.get("name", "Unknown")
        
        # 获取USD报价
        quotes = crypto.get("quotes", [])
        usd_quote = next((q for q in quotes if q.get("name") == "USD"), {})
        if not usd_quote and len(quotes) > 2:
            usd_quote = quotes[2]
            
        # 检查各个时间段的变化
        # API主要返回 volumePercentChange (24h)
        vol_change_24h = usd_quote.get("volumePercentChange", 0)
        if vol_change_24h == 0:
            vol_change_24h = usd_quote.get("volumeChange24h", 0)
            
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
        
        if triggered:
            # 使用更简洁的格式，一行显示
            alert_line = f"【{symbol}】{name}: " + " | ".join(triggered)
            alerts.append(alert_line)
            
    if alerts:
        print(f"发现 {len(alerts)} 个交易量异动项目，准备发送警报...")
        
        await _send_volume_alerts(alerts, threshold)
    else:
        print("未发现超过阈值的交易量变化")
    
    return {
        "alerts": alerts,
        "triggered_count": len(alerts)
    }


async def _send_volume_alerts(alerts, threshold):
    """发送交易量警报消息
    
    Args:
        alerts: 警报列表
        threshold: 阈值百分比
    """
    from webhook import send_message_async
    
    # 构建消息 - 使用更清晰的文本格式
    header = f"📊 交易量异动监控\n阈值: >{threshold}% | 数量: {len(alerts)}个\n"
    separator = "─" * 25
    
    # 将alerts分组，每组最多15个，避免单条消息过长
    group_size = 15
    alert_groups = [alerts[i:i+group_size] for i in range(0, len(alerts), group_size)]
    
    for idx, group in enumerate(alert_groups):
        if len(alert_groups) > 1:
            group_header = f"{header}{separator}\n[{idx+1}/{len(alert_groups)}]\n\n"
        else:
            group_header = f"{header}{separator}\n\n"
        
        message = group_header + "\n".join(group)
        await send_message_async(message, msg_type="text")
        
        # 如果有多组，稍微延迟避免频率限制
        if idx < len(alert_groups) - 1:
            await asyncio.sleep(0.5)


async def get_volume_statistics(crypto_list):
    """获取交易量统计信息
    
    Args:
        crypto_list: 加密货币项目列表
        
    Returns:
        dict: 交易量统计信息
    """
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

