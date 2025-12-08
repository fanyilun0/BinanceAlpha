"""
交易量变化监控模块

监控加密货币交易量变化并发送警报
支持三日趋势分析：换手率稳定性、吸筹、洗盘检测
独立模块，可直接运行
"""

import asyncio
import logging
import json
import os
import sys
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional

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


@dataclass
class TrendSignal:
    """三日趋势分析信号"""
    signal_type: str  # ACCUMULATION_STABLE, WASH_COMPLETE, BULL_FLAG, NEUTRAL
    score: float  # 0-1 置信度
    reason: str
    details: dict = None
    # 三日数据 (用于展示)
    history_3d: list = None  # [T0, T-1, T-2] 每项包含 volume, price, market_cap, turnover


class TrendAnalyzer:
    """三日趋势分析器 - 基于量价时空四维判断"""
    
    # 阈值配置
    CV_THRESHOLD = 0.15  # 交易量变异系数阈值 (越小越稳定)
    PRICE_FLAT_THRESHOLD = 3.0  # 价格横盘阈值 (±3%)
    MIN_TURNOVER = 0.02  # 最低换手率 (2%)
    VOL_SHRINK_RATIO = 0.9  # 缩量判断比例
    
    @staticmethod
    def analyze(history_3d: list[dict]) -> Optional[TrendSignal]:
        """
        分析连续3天的量价数据
        
        Args:
            history_3d: 3天数据列表 [今天, 昨天, 前天]
                       每项包含: volume, price, market_cap (可选), turnover (可选)
        
        Returns:
            TrendSignal or None
        """
        if len(history_3d) < 3:
            return None
        
        d0, d1, d2 = history_3d[0], history_3d[1], history_3d[2]
        
        # 提取数据
        volumes = [d0["volume"], d1["volume"], d2["volume"]]
        prices = [d0["price"], d1["price"], d2["price"]]
        
        # 计算价格变化率 (相对于前一天)
        p_change_d0 = ((prices[0] - prices[1]) / prices[1] * 100) if prices[1] > 0 else 0
        p_change_d1 = ((prices[1] - prices[2]) / prices[2] * 100) if prices[2] > 0 else 0
        
        # 计算换手率 (如果有market_cap)
        turnovers = []
        for d in history_3d:
            if d.get("market_cap") and d["market_cap"] > 0:
                turnovers.append(d["volume"] / d["market_cap"])
            elif d.get("turnover"):
                turnovers.append(d["turnover"])
            else:
                turnovers.append(0)
        
        # 构建带换手率的三日数据 (用于展示)
        history_3d_enriched = []
        for i, d in enumerate(history_3d):
            history_3d_enriched.append({
                "volume": d["volume"],
                "price": d["price"],
                "market_cap": d.get("market_cap", 0),
                "turnover": turnovers[i]
            })
        
        # 计算交易量变异系数 (CV = std / mean)
        vol_mean = sum(volumes) / len(volumes)
        vol_variance = sum((v - vol_mean) ** 2 for v in volumes) / len(volumes)
        vol_std = vol_variance ** 0.5
        vol_cv = vol_std / vol_mean if vol_mean > 0 else float('inf')
        
        # === 逻辑 A：稳定吸筹 ===
        # 条件：交易量极其稳定 (CV < 0.15)，价格波动极小 (|Change| < 3%)，且不是死盘 (Turnover > 0.02)
        is_stable_vol = vol_cv < TrendAnalyzer.CV_THRESHOLD
        is_flat_price = abs(p_change_d0) < TrendAnalyzer.PRICE_FLAT_THRESHOLD and abs(p_change_d1) < TrendAnalyzer.PRICE_FLAT_THRESHOLD
        is_active = all(t > TrendAnalyzer.MIN_TURNOVER for t in turnovers) if turnovers and all(t > 0 for t in turnovers) else True
        
        if is_stable_vol and is_flat_price and is_active:
            return TrendSignal(
                signal_type="ACCUMULATION_STABLE",
                score=0.9,
                reason="连续3日量能极度稳定且价格横盘，主力控盘吸筹迹象明显",
                details={"vol_cv": vol_cv, "price_changes": [p_change_d0, p_change_d1], "turnovers": turnovers},
                history_3d=history_3d_enriched
            )
        
        # === 逻辑 B：缩量洗盘结束 ===
        # 条件：连续两天缩量 (今天<昨天<前天)，且今天价格止跌 (Change > -1%)
        is_vol_shrinking = (
            volumes[0] < volumes[1] * TrendAnalyzer.VOL_SHRINK_RATIO and 
            volumes[1] < volumes[2] * TrendAnalyzer.VOL_SHRINK_RATIO
        )
        is_price_stabilizing = p_change_d0 > -1.0
        
        if is_vol_shrinking and is_price_stabilizing:
            return TrendSignal(
                signal_type="WASH_COMPLETE",
                score=0.85,
                reason="交易量连续萎缩（卖盘枯竭），价格企稳，洗盘可能结束",
                details={"vol_shrink": [volumes[0]/volumes[1], volumes[1]/volumes[2]], "price_change_d0": p_change_d0, "turnovers": turnovers},
                history_3d=history_3d_enriched
            )
        
        # === 逻辑 C：放量后的缩量确认 (空中加油/牛旗) ===
        # 条件：昨天大涨放量，今天缩量回调但价格没跌多少
        is_prev_pump = p_change_d1 > 5  # 昨天大涨
        is_now_correction = -3 < p_change_d0 < 1  # 今天微跌或微涨
        is_vol_drop_healthy = volumes[0] < volumes[1]  # 今天量缩
        
        if is_prev_pump and is_now_correction and is_vol_drop_healthy:
            return TrendSignal(
                signal_type="BULL_FLAG",
                score=0.8,
                reason="放量上涨后缩量回调，属于良性整理，上涨中继",
                details={"prev_pump": p_change_d1, "correction": p_change_d0, "turnovers": turnovers},
                history_3d=history_3d_enriched
            )
        
        return TrendSignal(
            signal_type="NEUTRAL",
            score=0.5,
            reason="无明显特征",
            details={"vol_cv": vol_cv, "price_changes": [p_change_d0, p_change_d1], "turnovers": turnovers},
            history_3d=history_3d_enriched
        )

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
    
    流程：
    1. 批量处理所有项目，更新今日数据到历史记录
    2. 基于三日历史数据进行趋势分析 (换手率/吸筹/洗盘)
    3. 发送告警
    
    Args:
        crypto_list: 加密货币项目列表 (如果为None，则从文件加载)
        threshold: 变化阈值（百分比），默认50%
        debug_only: 是否仅调试模式（不发送消息）
        
    Returns:
        dict: 包含监控结果的字典
    """
    print(f"=== 监控交易量变化 (阈值: {threshold}%) ===\n")
    
    # 初始化历史数据管理器
    history_manager = HistoryManager(os.path.join(project_root, 'data'))
    today_str = datetime.now().strftime('%Y-%m-%d')
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    day_before_str = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    
    if crypto_list is None:
        data = load_data()
        if not data:
            print("无法加载数据，监控终止")
            return {"alerts": [], "triggered_count": 0}
        crypto_list = data.get("data", {}).get("cryptoCurrencyList", [])
        print(f"已加载 {len(crypto_list)} 个项目数据")

    # 最低交易量门槛
    MIN_VOLUME_24H = 2_400_000
    MIN_MARKET_CAP = 1_000_000
    
    # ============================================
    # 阶段1: 批量更新今日数据到历史记录
    # ============================================
    print("阶段1: 批量更新今日数据...")
    processed_symbols = []
    
    for crypto in crypto_list:
        symbol = crypto.get("symbol", "Unknown")
        quotes = crypto.get("quotes", [])
        usd_quote = next((q for q in quotes if q.get("name") == "USD"), {})
        if not usd_quote and len(quotes) > 2:
            usd_quote = quotes[2]
        
        if not usd_quote:
            continue
        
        volume_24h = usd_quote.get("volume24h", 0)
        price = usd_quote.get("price", 0)
        market_cap = usd_quote.get("marketCap", 0)
        
        # 保存今日数据 (不过滤，便于后续趋势分析)
        if volume_24h > 0 and price > 0:
            history_manager.update(today_str, symbol, {
                "volume": volume_24h,
                "price": price,
                "market_cap": market_cap
            })
            processed_symbols.append(symbol)
    
    print(f"已更新 {len(processed_symbols)} 个项目的今日数据")
    
    # ============================================
    # 阶段2: 基于三日数据进行趋势分析
    # ============================================
    print("\n阶段2: 三日趋势分析...")
    
    alerts = []
    dealer_accumulation_alerts = []  # 吸筹: 量增价平/小涨
    dealer_distribution_alerts = []  # 出货/洗盘: 量增价跌
    trend_signals = []  # 三日趋势信号 (稳定吸筹/洗盘结束/牛旗)
    
    for crypto in crypto_list:
        symbol = crypto.get("symbol", "Unknown")
        name = crypto.get("name", "Unknown")
        
        quotes = crypto.get("quotes", [])
        usd_quote = next((q for q in quotes if q.get("name") == "USD"), {})
        if not usd_quote and len(quotes) > 2:
            usd_quote = quotes[2]
            
        if not usd_quote:
            continue

        vol_change_24h = usd_quote.get("volumePercentChange", 0)
        if vol_change_24h == 0:
            vol_change_24h = usd_quote.get("volumeChange24h", 0)
            
        price_change_24h = usd_quote.get("percentChange24h", 0)
        volume_24h = usd_quote.get("volume24h", 0)
        market_cap = usd_quote.get("marketCap", 0)
        fullyDilluttedMarketCap = usd_quote.get("fullyDilluttedMarketCap", 0)
        platform = crypto.get("platform", {}).get("name", "")

        changes = {
            "24h": vol_change_24h,
            "7d": usd_quote.get("volumeChange7d", 0),
            "30d": usd_quote.get("volumeChange30d", 0)
        }
        
        triggered = []
        for period, change in changes.items():
            if abs(change) >= threshold:
                arrow = "↑" if change > 0 else "↓"
                triggered.append(f"{arrow}{period}: {change:+.1f}%")
        
        # ============================================
        # 三日趋势分析 (核心逻辑)
        # ============================================
        h_today = history_manager.get_data(symbol, today_str)
        h_yest = history_manager.get_data(symbol, yesterday_str)
        h_before = history_manager.get_data(symbol, day_before_str)
        
        trend_signal = None
        is_continuous_accumulation = False
        
        if h_today and h_yest and h_before:
            # 构建3日数据序列 [今天, 昨天, 前天]
            history_3d = [h_today, h_yest, h_before]
            trend_signal = TrendAnalyzer.analyze(history_3d)
            
            if trend_signal and trend_signal.signal_type != "NEUTRAL" and trend_signal.score >= 0.8:
                # 高置信度信号
                signal_data = {
                    "symbol": symbol,
                    "name": name,
                    "signal_type": trend_signal.signal_type,
                    "score": trend_signal.score,
                    "reason": trend_signal.reason,
                    "volume": volume_24h,
                    "market_cap": market_cap,
                    "fdv": fullyDilluttedMarketCap,
                    "platform": platform,
                    "price_change": price_change_24h,
                    "vol_change": vol_change_24h,
                    # 三日数据 [T0, T-1, T-2]
                    "history_3d": trend_signal.history_3d
                }
                trend_signals.append(signal_data)
                
                # 稳定吸筹信号标记
                if trend_signal.signal_type == "ACCUMULATION_STABLE":
                    is_continuous_accumulation = True
        
        # ============================================
        # 庄家行为检测 (当日维度)
        # ============================================
        is_accumulation = False
        
        if vol_change_24h > threshold and volume_24h >= MIN_VOLUME_24H and market_cap > MIN_MARKET_CAP:
            alert_data = {
                "symbol": symbol,
                "name": name,
                "vol_change": vol_change_24h,
                "price_change": price_change_24h,
                "volume": volume_24h,
                "market_cap": market_cap,
                "fdv": fullyDilluttedMarketCap,
                "platform": platform
            }
            
            # 吸筹: 量增 + 价格不变或小涨 (-2% ~ +10%)
            if -2 <= price_change_24h <= 10:
                is_accumulation = True
                
                # 标记连续吸筹 (基于三日趋势分析结果)
                if is_continuous_accumulation:
                    alert_data["is_continuous"] = True
                # 备用逻辑：直接计算三日稳定性
                elif h_today and h_yest and h_before:
                    v_t, p_t = h_today["volume"], h_today["price"]
                    v_y, p_y = h_yest["volume"], h_yest["price"]
                    v_b, p_b = h_before["volume"], h_before["price"]
                    
                    vols = [v_t, v_y, v_b]
                    prices = [p_t, p_y, p_b]
                    v_stable = min(vols) >= max(vols) * 0.8
                    p_stable = max(prices) <= min(prices) * 1.05
                    
                    if v_stable and p_stable:
                        alert_data["is_continuous"] = True
                
                dealer_accumulation_alerts.append(alert_data)
                
            # 出货/洗盘: 量增 + 价格下跌 (< -2%)
            elif price_change_24h < -2:
                dealer_distribution_alerts.append(alert_data)

        if triggered:
            alert_info = {
                "symbol": symbol,
                "name": name,
                "change_24h": changes.get("24h", 0),
                "volume_24h": volume_24h,
                "is_accumulation": is_accumulation,
                "market_cap": market_cap,
                "fdv": fullyDilluttedMarketCap,
                "platform": platform
            }
            alerts.append(alert_info)
    
    # 保存历史数据
    history_manager.save()
    
    # 按24h变化率排序
    alerts.sort(key=lambda x: x["change_24h"], reverse=True)

    # ============================================
    # 阶段3: 发送告警
    # ============================================
    print("\n阶段3: 发送告警...")
    
    # 发送三日趋势信号告警 (新增)
    if trend_signals:
        print(f"发现 {len(trend_signals)} 个三日趋势信号")
        if not debug_only:
            await _send_trend_signals(trend_signals)

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
        "distribution_count": len(dealer_distribution_alerts),
        "trend_signals_count": len(trend_signals),
        "trend_signals": trend_signals
    }


class HistoryManager:
    """管理历史交易量数据"""
    def __init__(self, data_dir):
        self.file_path = os.path.join(data_dir, 'volume_monitor_history.json')
        self.history = self._load()

    def _load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logging.getLogger(__name__).error(f"加载历史数据失败: {e}")
                return {}
        return {}

    def save(self):
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logging.getLogger(__name__).error(f"保存历史数据失败: {e}")

    def update(self, date_str, symbol, data):
        if symbol not in self.history:
            self.history[symbol] = {}
        self.history[symbol][date_str] = data
        
        # 只保留最近7天
        dates = sorted(self.history[symbol].keys())
        if len(dates) > 7:
            for d in dates[:-7]:
                del self.history[symbol][d]

    def get_data(self, symbol, date_str):
        return self.history.get(symbol, {}).get(date_str)


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


async def _send_paginated_embed(
    title: str,
    items: list[dict],
    description_template: str,
    color: int,
    table_builder,
    batch_size: int = 20
):
    """通用分页发送 Discord Embed 消息"""
    if not items:
        return

    # 构建完整表格以检查长度
    full_table = table_builder(items)
    
    # 如果总长度未超限，直接发送
    if len(full_table) <= 4000:
        description = description_template.format(table=full_table)
        await send_discord_embed(
            title=f"{title} ({len(items)}个)",
            description=description,
            color=color,
            footer=f"监控时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        return

    # 分页发送
    total_pages = (len(items) - 1) // batch_size + 1
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        batch_table = table_builder(batch)
        page_num = i // batch_size + 1
        
        description = description_template.format(table=batch_table)
        await send_discord_embed(
            title=f"{title} ({page_num}/{total_pages})",
            description=description,
            color=color,
            footer=f"监控时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await asyncio.sleep(0.3)


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
        
        # 列宽定义 (总宽度约 72 字符)
        W_SYM = 10   # Symbol
        W_NAM = 12   # Name
        W_VOL = 8    # Vol%
        W_V24 = 8    # Vol
        W_MC = 8     # MCap
        W_FDV = 8    # FDV
        W_PLT = 10   # Platform
        
        header = f"{'Symbol':<{W_SYM}}{'Name':<{W_NAM}}{'Vol%':>{W_VOL}}{'Vol':>{W_V24}}{'MCap':>{W_MC}}{'FDV':>{W_FDV}}{'Plat':>{W_PLT}}"
        sep = "-" * (W_SYM + W_NAM + W_VOL + W_V24 + W_MC + W_FDV + W_PLT)
        
        lines = [f"```\n{header}\n{sep}"]
        
        for item in items:
            symbol = item["symbol"][:W_SYM]
            name = item["name"][:W_NAM]
            change = f"{item['change_24h']:+.0f}%"
            volume = _format_number(item.get("volume_24h", 0))
            mcap = _format_number(item.get("market_cap", 0))
            fdv = _format_number(item.get("fdv", 0))
            platform = (item.get("platform") or "")[:W_PLT]
            
            row = f"{symbol:<{W_SYM}}{name:<{W_NAM}}{change:>{W_VOL}}{volume:>{W_V24}}{mcap:>{W_MC}}{fdv:>{W_FDV}}{platform:>{W_PLT}}"
            lines.append(row)
        
        lines.append("```")
        return "\n".join(lines)
    
    # 发送涨幅榜
    if gainers:
        await _send_paginated_embed(
            title="📈 交易量激增",
            items=gainers,
            description_template=f"**阈值:** Vol > +{threshold}% & Vol24h > $2.4M\n{{table}}",
            color=DiscordColors.GREEN,
            table_builder=build_table
        )
    
    # 发送跌幅榜
    if losers:
        await _send_paginated_embed(
            title="📉 交易量骤降",
            items=losers,
            description_template=f"**阈值:** Vol < -{threshold}% & Vol24h > $2.4M\n{{table}}",
            color=DiscordColors.RED,
            table_builder=build_table
        )


def _build_dealer_table(items: list[dict]) -> str:
    """构建庄家行为表格
    
    使用固定宽度，适配 Discord embed 显示
    总宽度约 72 字符 (Discord embed 代码块最佳宽度)
    """
    # 列宽定义
    W_SYM = 10   # Symbol
    W_VOL = 8    # Vol%
    W_PRC = 7    # Prc%
    W_V24 = 8    # Vol
    W_MC = 8     # MCap
    W_FDV = 8    # FDV
    W_PLT = 10   # Platform
    
    header = f"{'Symbol':<{W_SYM}}{'Vol%':>{W_VOL}}{'Prc%':>{W_PRC}}{'Vol':>{W_V24}}{'MCap':>{W_MC}}{'FDV':>{W_FDV}}{'Plat':>{W_PLT}}"
    sep = "-" * (W_SYM + W_VOL + W_PRC + W_V24 + W_MC + W_FDV + W_PLT)
    
    lines = [f"```\n{header}\n{sep}"]
    
    for item in items:
        # 标记连续吸筹
        is_cont = item.get("is_continuous", False)
        raw_sym = item["symbol"]
        if is_cont:
            symbol = ("★" + raw_sym)[:W_SYM]
        else:
            symbol = raw_sym[:W_SYM]
            
        vol_change = f"+{item['vol_change']:.0f}%"
        price_change = f"{item['price_change']:+.1f}%"
        volume = _format_number(item["volume"])
        mcap = _format_number(item["market_cap"])
        fdv = _format_number(item["fdv"])
        platform = (item.get("platform") or "")[:W_PLT]
        
        row = f"{symbol:<{W_SYM}}{vol_change:>{W_VOL}}{price_change:>{W_PRC}}{volume:>{W_V24}}{mcap:>{W_MC}}{fdv:>{W_FDV}}{platform:>{W_PLT}}"
        lines.append(row)
    
    lines.append("```")
    return "\n".join(lines)


async def _send_accumulation_alerts(items: list[dict]):
    """发送庄家吸筹警报到 Discord - 量增价平/小涨"""
    # 按市值降序排列
    items_sorted = sorted(items, key=lambda x: x["market_cap"], reverse=True)
    
    await _send_paginated_embed(
        title="🐋 疑似吸筹",
        items=items_sorted,
        description_template="**特征:** 量增价平/小涨 (Vol↑ Price -2%~+10%)\n**★:** 3日量价稳定(持续吸筹)\n{table}",
        color=DiscordColors.PURPLE,
        table_builder=_build_dealer_table
    )


async def _send_distribution_alerts(items: list[dict]):
    """发送出货/洗盘警报到 Discord - 量增价跌"""
    # 按跌幅排序 (跌得最多的在前)
    items_sorted = sorted(items, key=lambda x: x["price_change"])
    
    await _send_paginated_embed(
        title="⚠️ 疑似出货/洗盘",
        items=items_sorted,
        description_template="**特征:** 量增价跌 (Vol↑ Price < -2%)\n{table}",
        color=DiscordColors.RED,
        table_builder=_build_dealer_table
    )


def _format_turnover(turnover: float) -> str:
    """格式化换手率 (百分比形式)"""
    if turnover <= 0:
        return "-"
    return f"{turnover * 100:.1f}%"


def _build_trend_signal_detail_table(items: list[dict]) -> str:
    """构建三日趋势信号详细表格 (展示 T-2, T-1, T0 的交易量和换手率)
    
    表格格式:
    Symbol   | T-2 Vol | T-2 TR | T-1 Vol | T-1 TR | T0 Vol  | T0 TR  | MCap
    """
    # 列宽定义 (总宽度约 72 字符)
    W_SYM = 10   # Symbol
    W_VOL = 7    # Volume (T-2, T-1, T0)
    W_TR = 6     # Turnover (T-2, T-1, T0)
    W_MC = 8     # MCap
    
    header = f"{'Symbol':<{W_SYM}}{'T-2Vol':>{W_VOL}}{'T-2TR':>{W_TR}}{'T-1Vol':>{W_VOL}}{'T-1TR':>{W_TR}}{'T0Vol':>{W_VOL}}{'T0TR':>{W_TR}}{'MCap':>{W_MC}}"
    sep = "-" * (W_SYM + W_VOL * 3 + W_TR * 3 + W_MC)
    
    lines = [f"```\n{header}\n{sep}"]
    
    for item in items:
        symbol = item["symbol"][:W_SYM]
        mcap = _format_number(item["market_cap"])
        
        # 获取三日数据 [T0, T-1, T-2]
        history_3d = item.get("history_3d", [])
        
        if history_3d and len(history_3d) >= 3:
            # T0 (今天)
            t0 = history_3d[0]
            t0_vol = _format_number(t0.get("volume", 0))
            t0_tr = _format_turnover(t0.get("turnover", 0))
            
            # T-1 (昨天)
            t1 = history_3d[1]
            t1_vol = _format_number(t1.get("volume", 0))
            t1_tr = _format_turnover(t1.get("turnover", 0))
            
            # T-2 (前天)
            t2 = history_3d[2]
            t2_vol = _format_number(t2.get("volume", 0))
            t2_tr = _format_turnover(t2.get("turnover", 0))
        else:
            # 无三日数据时显示占位符
            t0_vol = t0_tr = t1_vol = t1_tr = t2_vol = t2_tr = "-"
        
        row = f"{symbol:<{W_SYM}}{t2_vol:>{W_VOL}}{t2_tr:>{W_TR}}{t1_vol:>{W_VOL}}{t1_tr:>{W_TR}}{t0_vol:>{W_VOL}}{t0_tr:>{W_TR}}{mcap:>{W_MC}}"
        lines.append(row)
    
    lines.append("```")
    return "\n".join(lines)


def _build_trend_signal_summary_table(items: list[dict]) -> str:
    """构建三日趋势信号摘要表格 (简洁版，用于概览)"""
    # 列宽定义
    W_SYM = 10   # Symbol
    W_SIG = 10   # Signal
    W_SCR = 6    # Score
    W_VOL = 8    # Vol%
    W_PRC = 7    # Prc%
    W_TR = 7     # TR(T0)
    W_MC = 8     # MCap
    
    header = f"{'Symbol':<{W_SYM}}{'Signal':<{W_SIG}}{'Score':>{W_SCR}}{'Vol%':>{W_VOL}}{'Prc%':>{W_PRC}}{'TR(T0)':>{W_TR}}{'MCap':>{W_MC}}"
    sep = "-" * (W_SYM + W_SIG + W_SCR + W_VOL + W_PRC + W_TR + W_MC)
    
    lines = [f"```\n{header}\n{sep}"]
    
    signal_map = {
        "ACCUMULATION_STABLE": "稳定吸筹",
        "WASH_COMPLETE": "洗盘结束",
        "BULL_FLAG": "牛旗整理"
    }
    
    for item in items:
        symbol = item["symbol"][:W_SYM]
        signal = signal_map.get(item["signal_type"], item["signal_type"])[:W_SIG]
        score = f"{item['score']:.2f}"
        vol_change = f"{item.get('vol_change', 0):+.0f}%"
        price_change = f"{item.get('price_change', 0):+.1f}%"
        mcap = _format_number(item["market_cap"])
        
        # 获取 T0 换手率
        history_3d = item.get("history_3d", [])
        if history_3d and len(history_3d) > 0:
            t0_tr = _format_turnover(history_3d[0].get("turnover", 0))
        else:
            t0_tr = "-"
        
        row = f"{symbol:<{W_SYM}}{signal:<{W_SIG}}{score:>{W_SCR}}{vol_change:>{W_VOL}}{price_change:>{W_PRC}}{t0_tr:>{W_TR}}{mcap:>{W_MC}}"
        lines.append(row)
    
    lines.append("```")
    return "\n".join(lines)


async def _send_trend_signals(items: list[dict]):
    """发送三日趋势信号告警到 Discord
    
    发送两类消息：
    1. 摘要表 (概览)
    2. 详细表 (T-2, T-1, T0 的 Vol 和 Turnover)
    """
    # 按信号类型分组
    accumulation = [i for i in items if i["signal_type"] == "ACCUMULATION_STABLE"]
    wash_complete = [i for i in items if i["signal_type"] == "WASH_COMPLETE"]
    bull_flag = [i for i in items if i["signal_type"] == "BULL_FLAG"]
    
    # 发送稳定吸筹信号
    if accumulation:
        accumulation_sorted = sorted(accumulation, key=lambda x: x["market_cap"], reverse=True)
        
        # 发送详细表 (三日 Vol + Turnover)
        await _send_paginated_embed(
            title="📊 稳定吸筹 (三日量价)",
            items=accumulation_sorted,
            description_template="**特征:** 连续3日量能稳定 + 价格横盘\n**含义:** 主力控盘吸筹迹象明显\n**TR:** 换手率 = Vol/MCap\n{table}",
            color=DiscordColors.PURPLE,
            table_builder=_build_trend_signal_detail_table
        )
    
    # 发送洗盘结束信号
    if wash_complete:
        wash_sorted = sorted(wash_complete, key=lambda x: x["market_cap"], reverse=True)
        
        await _send_paginated_embed(
            title="📊 洗盘结束 (三日量价)",
            items=wash_sorted,
            description_template="**特征:** 连续缩量 + 价格企稳\n**含义:** 卖盘枯竭，可能触底\n**TR:** 换手率 = Vol/MCap\n{table}",
            color=DiscordColors.YELLOW,
            table_builder=_build_trend_signal_detail_table
        )
    
    # 发送牛旗信号
    if bull_flag:
        flag_sorted = sorted(bull_flag, key=lambda x: x["market_cap"], reverse=True)
        
        await _send_paginated_embed(
            title="📊 牛旗整理 (三日量价)",
            items=flag_sorted,
            description_template="**特征:** 昨日放量大涨 + 今日缩量回调\n**含义:** 良性整理，上涨中继\n**TR:** 换手率 = Vol/MCap\n{table}",
            color=DiscordColors.GREEN,
            table_builder=_build_trend_signal_detail_table
        )

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



