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

def _find_latest_file_for_date(data_dir: str, target_date: str) -> Optional[str]:
    """查找指定日期的最新数据文件
    
    Args:
        data_dir: 数据目录
        target_date: 目标日期 (YYYYMMDD 格式)
        
    Returns:
        最新文件路径或None
    """
    import glob
    pattern = os.path.join(data_dir, f'filtered_crypto_list_{target_date}*.json')
    files = glob.glob(pattern)
    
    if not files:
        return None
    
    # 按文件名排序，取最新的（时间戳最大的）
    files.sort(reverse=True)
    return files[0]


def load_multi_day_data(days: int = 3) -> dict[str, list]:
    """加载最近N天的 filtered_crypto_list 数据
    
    Args:
        days: 需要加载的天数（默认3天）
        
    Returns:
        dict: {
            "T0": [crypto_list],  # 今天
            "T-1": [crypto_list], # 昨天
            "T-2": [crypto_list], # 前天
            ...
        }
    """
    data_dir = os.path.join(project_root, 'data')
    result = {}
    
    for i in range(days):
        date_obj = datetime.now() - timedelta(days=i)
        date_str = date_obj.strftime('%Y%m%d')
        key = f"T{-i}" if i > 0 else "T0"
        
        file_path = _find_latest_file_for_date(data_dir, date_str)
        
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    result[key] = data
                    logger.info(f"已加载 {key} ({date_str}) 数据: {os.path.basename(file_path)}, 共 {len(data)} 项")
            except Exception as e:
                logger.error(f"加载 {key} ({date_str}) 数据失败: {str(e)}")
                result[key] = []
        else:
            logger.warning(f"未找到 {key} ({date_str}) 的数据文件")
            result[key] = []
    
    return result


def _build_crypto_index(crypto_list: list) -> dict[str, dict]:
    """构建 symbol -> crypto_data 的索引
    
    Args:
        crypto_list: 加密货币列表
        
    Returns:
        dict: {symbol: crypto_data}
    """
    index = {}
    for crypto in crypto_list:
        symbol = crypto.get("symbol", "")
        if symbol:
            index[symbol] = crypto
    return index


def load_data():
    """加载最新的Binance Alpha数据 (兼容原有接口)
    
    Returns:
        今天的数据（列表格式）或 None
    """
    multi_day = load_multi_day_data(days=1)
    today_data = multi_day.get("T0", [])
    
    if not today_data:
        logger.error("加载今日数据失败")
        return None
    
    # 兼容原有格式
    return {
        "data": {
            "cryptoCurrencyList": today_data
        }
    }


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
    
    # 加载三日数据文件 (filtered_crypto_list_*.json)
    multi_day_data = load_multi_day_data(days=3)
    t0_list = multi_day_data.get("T0", [])
    t1_list = multi_day_data.get("T-1", [])
    t2_list = multi_day_data.get("T-2", [])
    
    # 构建 symbol 索引以便快速查找
    t1_index = _build_crypto_index(t1_list)
    t2_index = _build_crypto_index(t2_list)
    
    if crypto_list is None:
        if not t0_list:
            print("无法加载数据，监控终止")
            return {"alerts": [], "triggered_count": 0}
        crypto_list = t0_list
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
        # 优先从 filtered_crypto_list 文件加载三日数据
        h_today = {"volume": volume_24h, "price": price, "market_cap": market_cap}
        
        # 从 T-1 文件获取昨日数据
        h_yest = None
        t1_crypto = t1_index.get(symbol)
        if t1_crypto:
            t1_quotes = t1_crypto.get("quotes", [])
            t1_usd = next((q for q in t1_quotes if q.get("name") == "USD"), {})
            if not t1_usd and len(t1_quotes) > 2:
                t1_usd = t1_quotes[2]
            if t1_usd:
                h_yest = {
                    "volume": t1_usd.get("volume24h", 0),
                    "price": t1_usd.get("price", 0),
                    "market_cap": t1_usd.get("marketCap", 0)
                }
        
        # 从 T-2 文件获取前日数据
        h_before = None
        t2_crypto = t2_index.get(symbol)
        if t2_crypto:
            t2_quotes = t2_crypto.get("quotes", [])
            t2_usd = next((q for q in t2_quotes if q.get("name") == "USD"), {})
            if not t2_usd and len(t2_quotes) > 2:
                t2_usd = t2_quotes[2]
            if t2_usd:
                h_before = {
                    "volume": t2_usd.get("volume24h", 0),
                    "price": t2_usd.get("price", 0),
                    "market_cap": t2_usd.get("marketCap", 0)
                }
        
        # 回退到 HistoryManager 中的数据
        if not h_yest:
            h_yest = history_manager.get_data(symbol, yesterday_str)
        if not h_before:
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
        # 构建三日历史数据 (用于展示)
        # ============================================
        history_3d_enriched = None
        if h_today and h_yest and h_before:
            # 计算换手率
            turnovers = []
            for d in [h_today, h_yest, h_before]:
                mc = d.get("market_cap", 0)
                vol = d.get("volume", 0)
                if mc > 0:
                    turnovers.append(vol / mc)
                else:
                    turnovers.append(0)
            
            history_3d_enriched = [
                {"volume": h_today["volume"], "price": h_today["price"], "market_cap": h_today.get("market_cap", 0), "turnover": turnovers[0]},
                {"volume": h_yest["volume"], "price": h_yest["price"], "market_cap": h_yest.get("market_cap", 0), "turnover": turnovers[1]},
                {"volume": h_before["volume"], "price": h_before["price"], "market_cap": h_before.get("market_cap", 0), "turnover": turnovers[2]},
            ]
        
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
                "platform": platform,
                "history_3d": history_3d_enriched  # 添加三日数据
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
                "price_change": price_change_24h,
                "volume_24h": volume_24h,
                "is_accumulation": is_accumulation,
                "market_cap": market_cap,
                "fdv": fullyDilluttedMarketCap,
                "platform": platform,
                "history_3d": history_3d_enriched  # 添加三日数据
            }
            alerts.append(alert_info)
    
    # 保存历史数据
    history_manager.save()
    
    # 按24h变化率排序
    alerts.sort(key=lambda x: x["change_24h"], reverse=True)
    
    # 保存吸筹/洗盘数据到本地 JSON (供 docs-viewer 使用)
    await _save_trend_data(
        trend_signals=trend_signals,
        accumulation_alerts=dealer_accumulation_alerts,
        distribution_alerts=dealer_distribution_alerts
    )

    # 阶段3: 发送告警 (顺序: 三日趋势 → 吸筹 → 洗盘 → 交易量)
    print("\n阶段3: 发送告警...")
    
    # 1. 发送三日趋势信号告警 (高优先级)
    if trend_signals:
        print(f"发现 {len(trend_signals)} 个三日趋势信号")
        if not debug_only:
            await _send_trend_signals(trend_signals)
    
    # 2. 发送庄家吸筹警报 (量增价平/小涨)
    if dealer_accumulation_alerts:
        print(f"发现 {len(dealer_accumulation_alerts)} 个疑似庄家吸筹项目")
        if not debug_only:
            await _send_accumulation_alerts(dealer_accumulation_alerts)
    
    # 3. 发送出货/洗盘警报 (量增价跌)
    if dealer_distribution_alerts:
        print(f"发现 {len(dealer_distribution_alerts)} 个疑似出货/洗盘项目")
        if not debug_only:
            await _send_distribution_alerts(dealer_distribution_alerts)

    # 4. 发送常规交易量异动警报 (最后)
    if alerts:
        print(f"发现 {len(alerts)} 个交易量异动项目")
        if not debug_only:
            await _send_volume_alerts(alerts, threshold)
    else:
        print("未发现超过阈值的交易量变化")
    
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
    """发送交易量警报消息到 Discord - 紧凑列表格式
    
    使用与吸筹告警相同的展示方式，支持三日数据展示
    """
    # 过滤最低交易量门槛
    MIN_VOLUME_24H = 2_400_000
    filtered_alerts = [a for a in alerts if a.get("volume_24h", 0) >= MIN_VOLUME_24H]
    
    if not filtered_alerts:
        print(f"过滤后无符合条件的交易量异动 (门槛: ${MIN_VOLUME_24H:,})")
        return
    
    # 分离涨跌
    gainers = [a for a in filtered_alerts if a["change_24h"] > 0]
    losers = [a for a in filtered_alerts if a["change_24h"] < 0]
    
    # 发送涨幅榜 (交易量激增)
    if gainers:
        # 按变化率排序
        gainers_sorted = sorted(gainers, key=lambda x: x["change_24h"], reverse=True)
        await _send_summary_embed(
            title="📈 交易量激增",
            items=gainers_sorted,
            color=DiscordColors.GREEN,
            description_prefix=f"**阈值:** Vol > +{threshold}% & Vol24h > $2.4M",
            max_items=15
        )
    
    # 发送跌幅榜 (交易量骤降)
    if losers:
        # 按变化率排序 (跌幅最大的在前)
        losers_sorted = sorted(losers, key=lambda x: x["change_24h"])
        await _send_summary_embed(
            title="📉 交易量骤降",
            items=losers_sorted,
            color=DiscordColors.RED,
            description_prefix=f"**阈值:** Vol < -{threshold}% & Vol24h > $2.4M",
            max_items=15
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
    """发送庄家吸筹警报到 Discord - 量增价平/小涨
    
    使用紧凑列表格式，突出显示连续吸筹标记
    """
    # 按市值降序排列
    items_sorted = sorted(items, key=lambda x: x["market_cap"], reverse=True)
    
    # 分离连续吸筹和单日吸筹
    continuous = [i for i in items_sorted if i.get("is_continuous", False)]
    single_day = [i for i in items_sorted if not i.get("is_continuous", False)]
    
    # 发送连续吸筹（高优先级）
    if continuous:
        await _send_summary_embed(
            title="🐋⭐ 持续吸筹 (连续3日)",
            items=continuous,
            color=DiscordColors.PURPLE,
            description_prefix="**特征:** 量增价平/小涨 + 连续3日量价稳定\n**含义:** 主力持续吸筹，高度关注",
            max_items=15
        )
    
    # 发送单日吸筹
    if single_day:
        await _send_summary_embed(
            title="🐋 疑似吸筹 (单日)",
            items=single_day,
            color=DiscordColors.PURPLE,
            description_prefix="**特征:** 量增价平/小涨 (Vol↑ Price -2%~+10%)",
            max_items=15
        )


async def _send_distribution_alerts(items: list[dict]):
    """发送出货/洗盘警报到 Discord - 量增价跌
    
    使用紧凑列表格式
    """
    # 按跌幅排序 (跌得最多的在前)
    items_sorted = sorted(items, key=lambda x: x["price_change"])
    
    await _send_summary_embed(
        title="⚠️ 疑似出货/洗盘",
        items=items_sorted,
        color=DiscordColors.RED,
        description_prefix="**特征:** 量增价跌 (Vol↑ Price < -2%)\n**风险提示:** 注意规避下跌风险",
        max_items=15
    )


def _format_turnover(turnover: float) -> str:
    """格式化换手率 (百分比形式)"""
    if turnover <= 0:
        return "-"
    return f"{turnover * 100:.1f}%"


def _get_trend_emoji(values: list[float]) -> str:
    """根据数值趋势返回 Emoji
    
    Args:
        values: 数值列表 [最新, ..., 最旧]
        
    Returns:
        趋势 Emoji
    """
    if len(values) < 2:
        return "➡️"
    
    latest, prev = values[0], values[1]
    if prev == 0:
        return "➡️"
    
    change = (latest - prev) / prev * 100
    
    if change > 10:
        return "🚀"
    elif change > 3:
        return "📈"
    elif change > -3:
        return "➡️"
    elif change > -10:
        return "📉"
    else:
        return "💥"


def _get_signal_color(signal_type: str) -> int:
    """获取信号类型对应的颜色
    
    Args:
        signal_type: 信号类型
        
    Returns:
        颜色值 (十六进制)
    """
    color_map = {
        "ACCUMULATION_STABLE": 0x9B59B6,  # 紫色 - 吸筹
        "WASH_COMPLETE": 0xF1C40F,         # 黄色 - 洗盘结束
        "BULL_FLAG": 0x2ECC71,             # 绿色 - 牛旗
        "DISTRIBUTION": 0xE74C3C,          # 红色 - 出货
    }
    return color_map.get(signal_type, 0x5865F2)


def _get_signal_emoji(signal_type: str) -> str:
    """获取信号类型对应的 Emoji"""
    emoji_map = {
        "ACCUMULATION_STABLE": "🟪",
        "WASH_COMPLETE": "🟨",
        "BULL_FLAG": "🟩",
        "DISTRIBUTION": "🟥",
    }
    return emoji_map.get(signal_type, "⬜")


def _get_signal_name(signal_type: str) -> str:
    """获取信号类型的中文名称"""
    name_map = {
        "ACCUMULATION_STABLE": "稳定吸筹",
        "WASH_COMPLETE": "洗盘结束",
        "BULL_FLAG": "牛旗整理",
        "DISTRIBUTION": "出货/洗盘",
    }
    return name_map.get(signal_type, signal_type)


async def _send_signal_card(signal_data: dict):
    """发送单个信号的详情卡片（一级告警）
    
    使用 Embed Fields 垂直布局，展示三日量价数据
    适用于高置信度信号 (Score > 0.8)
    
    Args:
        signal_data: 包含信号详情的字典
    """
    symbol = signal_data["symbol"]
    name = signal_data["name"]
    signal_type = signal_data["signal_type"]
    score = signal_data["score"]
    reason = signal_data["reason"]
    history_3d = signal_data.get("history_3d", [])
    market_cap = signal_data.get("market_cap", 0)
    price_change = signal_data.get("price_change", 0)
    platform = signal_data.get("platform", "")
    
    # 构建标题
    signal_emoji = _get_signal_emoji(signal_type)
    signal_name = _get_signal_name(signal_type)
    title = f"{signal_emoji} {symbol} 发现{signal_name}信号 (置信度: {score:.2f})"
    
    # 构建描述（基本信息）
    price_emoji = "📈" if price_change > 0 else "📉" if price_change < 0 else "➡️"
    description = f"**{name}** | {platform}\n"
    description += f"市值: **${_format_number(market_cap)}** | 24h价格: **{price_change:+.2f}%** {price_emoji}"
    
    # 构建三日量价趋势 (垂直布局)
    fields = []
    
    if history_3d and len(history_3d) >= 3:
        # T-2 (前天)
        t2 = history_3d[2]
        t2_vol = _format_number(t2.get("volume", 0))
        t2_tr = _format_turnover(t2.get("turnover", 0))
        t2_price = t2.get("price", 0)
        
        # T-1 (昨天)
        t1 = history_3d[1]
        t1_vol = _format_number(t1.get("volume", 0))
        t1_tr = _format_turnover(t1.get("turnover", 0))
        t1_price = t1.get("price", 0)
        
        # T0 (今天)
        t0 = history_3d[0]
        t0_vol = _format_number(t0.get("volume", 0))
        t0_tr = _format_turnover(t0.get("turnover", 0))
        t0_price = t0.get("price", 0)
        
        # 计算趋势
        volumes = [t0.get("volume", 0), t1.get("volume", 0), t2.get("volume", 0)]
        prices = [t0_price, t1_price, t2_price]
        vol_trend = _get_trend_emoji(volumes)
        price_trend = _get_trend_emoji(prices)
        
        # 三日数据字段 (垂直堆叠)
        trend_text = (
            f"📅 **T-2 (前天):** Vol {t2_vol} | TR {t2_tr} | Price ${t2_price:.4g}\n"
            f"📅 **T-1 (昨天):** Vol {t1_vol} | TR {t1_tr} | Price ${t1_price:.4g}\n"
            f"📅 **T-0 (今天):** Vol {t0_vol} | TR {t0_tr} | Price ${t0_price:.4g}\n"
            f"📊 **趋势:** 量能{vol_trend} | 价格{price_trend}"
        )
        
        fields.append({
            "name": "📈 三日量价趋势",
            "value": trend_text,
            "inline": False
        })
        
        # 换手率分析
        avg_turnover = sum(d.get("turnover", 0) for d in history_3d) / 3
        tr_analysis = ""
        if avg_turnover > 0.3:
            tr_analysis = f"**{_format_turnover(avg_turnover)}** (极高换手，短线博弈激烈)"
        elif avg_turnover > 0.15:
            tr_analysis = f"**{_format_turnover(avg_turnover)}** (高换手，资金活跃)"
        elif avg_turnover > 0.05:
            tr_analysis = f"**{_format_turnover(avg_turnover)}** (正常换手)"
        else:
            tr_analysis = f"**{_format_turnover(avg_turnover)}** (低换手，主力控盘)"
        
        fields.append({
            "name": "💹 平均换手率",
            "value": tr_analysis,
            "inline": True
        })
    
    # 信号解读
    fields.append({
        "name": "🔍 信号解读",
        "value": reason,
        "inline": False
    })
    
    # 构建 Embed
    embed = {
        "title": title,
        "description": description,
        "color": _get_signal_color(signal_type),
        "fields": fields,
        "footer": {
            "text": f"判定逻辑: CV<0.15 & Price±3% | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        }
    }
    
    # 发送
    await _send_embed_raw(embed)


async def _send_embed_raw(embed: dict, username: str = "Binance Alpha Monitor"):
    """发送原始 Embed 对象
    
    Args:
        embed: Discord Embed 对象
        username: 机器人名称
    """
    import aiohttp
    from config import DISCORD_WEBHOOK_URL, PROXY_URL, USE_PROXY
    
    if not DISCORD_WEBHOOK_URL:
        print("错误: DISCORD_WEBHOOK_URL 未配置")
        return False
    
    payload = {"embeds": [embed]}
    if username:
        payload["username"] = username
    
    proxy = PROXY_URL if USE_PROXY else None
    headers = {"Content-Type": "application/json"}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                DISCORD_WEBHOOK_URL,
                json=payload,
                headers=headers,
                proxy=proxy
            ) as response:
                if response.status in (200, 204):
                    print("Discord Embed 消息发送成功!")
                    return True
                else:
                    text = await response.text()
                    print(f"Discord Embed 消息发送失败: {response.status}, {text}")
                    return False
    except Exception as e:
        print(f"Discord Embed 消息发送出错: {str(e)}")
        return False


async def _send_summary_embed(
    title: str,
    items: list[dict],
    color: int,
    description_prefix: str = "",
    max_items: int = 10
):
    """发送紧凑概览列表（二级告警）
    
    使用多行文本块展示，每个 Token 独立一块
    适用于批量展示普通异动，支持三日数据展示
    
    Args:
        title: Embed 标题
        items: 项目列表 (需包含 history_3d 字段以展示三日数据)
        color: 颜色
        description_prefix: 描述前缀
        max_items: 最大展示数量
    """
    if not items:
        return
    
    # 限制数量
    display_items = items[:max_items]
    
    # 构建描述内容 (紧凑列表格式)
    lines = []
    if description_prefix:
        lines.append(description_prefix)
        lines.append("")
    
    for i, item in enumerate(display_items, 1):
        symbol = item.get("symbol", "?")
        name = item.get("name", "")[:15]
        vol_change = item.get("vol_change", item.get("change_24h", 0))
        price_change = item.get("price_change", 0)
        volume = _format_number(item.get("volume", item.get("volume_24h", 0)))
        market_cap = _format_number(item.get("market_cap", 0))
        
        # 状态标记
        vol_emoji = "🚀" if vol_change > 50 else "↗️" if vol_change > 0 else "↘️"
        price_emoji = "📈" if price_change > 5 else "📉" if price_change < -5 else "➡️"
        
        # 判断信号类型
        status = ""
        if -2 <= price_change <= 10 and vol_change > 50:
            status = "🐋 量增价平 (疑似吸筹)"
        elif price_change < -2 and vol_change > 50:
            status = "⚠️ 放量下跌 (疑似出货)"
        elif price_change > 10 and vol_change > 50:
            status = "🔥 放量上涨"
        else:
            status = f"Vol {vol_change:+.0f}% | Price {price_change:+.1f}%"
        
        # 构建三日数据展示
        history_3d = item.get("history_3d", [])
        history_lines = ""
        
        if history_3d and len(history_3d) >= 3:
            # T-2 (前天)
            t2 = history_3d[2]
            t2_vol = _format_number(t2.get("volume", 0))
            t2_tr = _format_turnover(t2.get("turnover", 0))
            t2_price = t2.get("price", 0)
            
            # T-1 (昨天)
            t1 = history_3d[1]
            t1_vol = _format_number(t1.get("volume", 0))
            t1_tr = _format_turnover(t1.get("turnover", 0))
            t1_price = t1.get("price", 0)
            
            # 计算价格变化
            t2_pct = ""
            t1_pct = ""
            if t2_price > 0 and t1_price > 0:
                t1_change = ((t1_price - t2_price) / t2_price) * 100
                t1_pct = f" ({t1_change:+.1f}%)"
            if t1_price > 0 and history_3d[0].get("price", 0) > 0:
                t0_price = history_3d[0].get("price", 0)
                t0_change = ((t0_price - t1_price) / t1_price) * 100
                # t0_pct 在当前价格变化中已经体现
            
            history_lines = (
                f"├─ T-2: Vol {t2_vol} | TR {t2_tr} | ${t2_price:.4g}\n"
                f"├─ T-1: Vol {t1_vol} | TR {t1_tr} | ${t1_price:.4g}{t1_pct}\n"
            )
        
        block = (
            f"**{i}. {symbol}** ({name})\n"
            f"├─ T0 Vol: ${volume} ({vol_change:+.0f}% {vol_emoji})\n"
            f"{history_lines}"
            f"├─ MCap: ${market_cap} | Price: {price_change:+.1f}% {price_emoji}\n"
            f"└─ {status}"
        )
        lines.append(block)
        lines.append("")
    
    # 如果有更多项目
    if len(items) > max_items:
        lines.append(f"_...还有 {len(items) - max_items} 个项目未显示_")
    
    description = "\n".join(lines)
    
    # 限制描述长度
    if len(description) > 4000:
        description = description[:3950] + "\n\n_...内容已截断_"
    
    embed = {
        "title": f"{title} ({len(items)}个)",
        "description": description,
        "color": color,
        "footer": {
            "text": f"监控时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        }
    }
    
    await _send_embed_raw(embed)


async def _save_trend_data(
    trend_signals: list[dict],
    accumulation_alerts: list[dict],
    distribution_alerts: list[dict]
):
    """保存吸筹/洗盘数据到本地 JSON 文件 (供 docs-viewer 使用)
    
    输出路径: data/trend_signals_YYYYMMDD.json
    (通过 generate-list.js 脚本复制到 docs-viewer/public/tables/)
    
    Args:
        trend_signals: 三日趋势信号列表
        accumulation_alerts: 吸筹告警列表
        distribution_alerts: 出货/洗盘告警列表
    """
    # 目标目录 (保存到 data 目录，与 filtered_crypto_list 同级)
    data_dir = os.path.join(project_root, 'data')
    if not os.path.exists(data_dir):
        logger.warning(f"data 目录不存在，跳过保存: {data_dir}")
        return
    
    today_str = datetime.now().strftime('%Y%m%d')
    output_file = os.path.join(data_dir, f'trend_signals_{today_str}.json')
    
    # 构建输出数据结构
    output_data = {
        "title": "吸筹/洗盘信号分析",
        "date": datetime.now().strftime('%Y-%m-%d'),
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "trend_signals_count": len(trend_signals),
            "accumulation_count": len(accumulation_alerts),
            "distribution_count": len(distribution_alerts)
        },
        "columns": [
            "代号", "名称", "信号类型", "置信度", "交易量变化(%)", "价格变化(%)",
            "24h交易量", "市值", "FDV", "平台", "信号解读",
            "T0交易量", "T0换手率", "T-1交易量", "T-1换手率", "T-2交易量", "T-2换手率"
        ],
        "data": []
    }
    
    # 合并所有信号数据
    all_items = []
    
    # 添加三日趋势信号
    for item in trend_signals:
        signal_type = item.get("signal_type", "UNKNOWN")
        signal_name = _get_signal_name(signal_type)
        history_3d = item.get("history_3d", [])
        
        row = {
            "代号": item.get("symbol", "-"),
            "名称": item.get("name", "-"),
            "信号类型": signal_name,
            "置信度": f"{item.get('score', 0):.2f}",
            "交易量变化(%)": f"{item.get('vol_change', 0):+.1f}%",
            "价格变化(%)": f"{item.get('price_change', 0):+.1f}%",
            "24h交易量": f"${_format_number(item.get('volume', 0))}",
            "市值": f"${_format_number(item.get('market_cap', 0))}",
            "FDV": f"${_format_number(item.get('fdv', 0))}",
            "平台": item.get("platform", "-"),
            "信号解读": item.get("reason", "-"),
            "signal_type_raw": signal_type,
            "score_raw": item.get("score", 0),
            "vol_change_raw": item.get("vol_change", 0),
            "price_change_raw": item.get("price_change", 0),
            "volume_raw": item.get("volume", 0),
            "market_cap_raw": item.get("market_cap", 0),
        }
        
        # 三日数据
        if history_3d and len(history_3d) >= 3:
            for i, label in enumerate(["T0", "T-1", "T-2"]):
                d = history_3d[i]
                row[f"{label}交易量"] = f"${_format_number(d.get('volume', 0))}"
                row[f"{label}换手率"] = _format_turnover(d.get("turnover", 0))
                row[f"{label}_volume_raw"] = d.get("volume", 0)
                row[f"{label}_turnover_raw"] = d.get("turnover", 0)
        else:
            for label in ["T0", "T-1", "T-2"]:
                row[f"{label}交易量"] = "-"
                row[f"{label}换手率"] = "-"
        
        all_items.append(row)
    
    # 添加吸筹告警 (如果不在 trend_signals 中)
    existing_symbols = {item["代号"] for item in all_items}
    for item in accumulation_alerts:
        symbol = item.get("symbol", "-")
        if symbol in existing_symbols:
            continue
        
        history_3d = item.get("history_3d", [])
        row = {
            "代号": symbol,
            "名称": item.get("name", "-"),
            "信号类型": "疑似吸筹" if not item.get("is_continuous") else "持续吸筹",
            "置信度": "0.70" if not item.get("is_continuous") else "0.85",
            "交易量变化(%)": f"{item.get('vol_change', 0):+.1f}%",
            "价格变化(%)": f"{item.get('price_change', 0):+.1f}%",
            "24h交易量": f"${_format_number(item.get('volume', 0))}",
            "市值": f"${_format_number(item.get('market_cap', 0))}",
            "FDV": f"${_format_number(item.get('fdv', 0))}",
            "平台": item.get("platform", "-"),
            "信号解读": "量增价平/小涨" + (" + 连续3日稳定" if item.get("is_continuous") else ""),
            "signal_type_raw": "ACCUMULATION_SINGLE" if not item.get("is_continuous") else "ACCUMULATION_CONTINUOUS",
            "score_raw": 0.70 if not item.get("is_continuous") else 0.85,
            "vol_change_raw": item.get("vol_change", 0),
            "price_change_raw": item.get("price_change", 0),
            "volume_raw": item.get("volume", 0),
            "market_cap_raw": item.get("market_cap", 0),
        }
        
        if history_3d and len(history_3d) >= 3:
            for i, label in enumerate(["T0", "T-1", "T-2"]):
                d = history_3d[i]
                row[f"{label}交易量"] = f"${_format_number(d.get('volume', 0))}"
                row[f"{label}换手率"] = _format_turnover(d.get("turnover", 0))
                row[f"{label}_volume_raw"] = d.get("volume", 0)
                row[f"{label}_turnover_raw"] = d.get("turnover", 0)
        else:
            for label in ["T0", "T-1", "T-2"]:
                row[f"{label}交易量"] = "-"
                row[f"{label}换手率"] = "-"
        
        all_items.append(row)
        existing_symbols.add(symbol)
    
    # 添加出货/洗盘告警
    for item in distribution_alerts:
        symbol = item.get("symbol", "-")
        if symbol in existing_symbols:
            continue
        
        history_3d = item.get("history_3d", [])
        row = {
            "代号": symbol,
            "名称": item.get("name", "-"),
            "信号类型": "疑似出货/洗盘",
            "置信度": "0.65",
            "交易量变化(%)": f"{item.get('vol_change', 0):+.1f}%",
            "价格变化(%)": f"{item.get('price_change', 0):+.1f}%",
            "24h交易量": f"${_format_number(item.get('volume', 0))}",
            "市值": f"${_format_number(item.get('market_cap', 0))}",
            "FDV": f"${_format_number(item.get('fdv', 0))}",
            "平台": item.get("platform", "-"),
            "信号解读": "量增价跌，注意风险",
            "signal_type_raw": "DISTRIBUTION",
            "score_raw": 0.65,
            "vol_change_raw": item.get("vol_change", 0),
            "price_change_raw": item.get("price_change", 0),
            "volume_raw": item.get("volume", 0),
            "market_cap_raw": item.get("market_cap", 0),
        }
        
        if history_3d and len(history_3d) >= 3:
            for i, label in enumerate(["T0", "T-1", "T-2"]):
                d = history_3d[i]
                row[f"{label}交易量"] = f"${_format_number(d.get('volume', 0))}"
                row[f"{label}换手率"] = _format_turnover(d.get("turnover", 0))
                row[f"{label}_volume_raw"] = d.get("volume", 0)
                row[f"{label}_turnover_raw"] = d.get("turnover", 0)
        else:
            for label in ["T0", "T-1", "T-2"]:
                row[f"{label}交易量"] = "-"
                row[f"{label}换手率"] = "-"
        
        all_items.append(row)
    
    # 按置信度和市值排序
    all_items.sort(key=lambda x: (x.get("score_raw", 0), x.get("market_cap_raw", 0)), reverse=True)
    output_data["data"] = all_items
    output_data["total_count"] = len(all_items)
    
    # 写入文件
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        logger.info(f"已保存吸筹/洗盘数据到: {output_file}, 共 {len(all_items)} 条")
    except Exception as e:
        logger.error(f"保存吸筹/洗盘数据失败: {e}")


async def _send_trend_signals(items: list[dict]):
    """发送三日趋势信号告警到 Discord
    
    分层展示策略：
    - 一级告警 (高置信度 Score >= 0.85): 单币单卡片
    - 二级告警 (普通信号): 紧凑列表
    """
    if not items:
        return
    
    # 按信号类型分组
    accumulation = [i for i in items if i["signal_type"] == "ACCUMULATION_STABLE"]
    wash_complete = [i for i in items if i["signal_type"] == "WASH_COMPLETE"]
    bull_flag = [i for i in items if i["signal_type"] == "BULL_FLAG"]
    
    # 发送稳定吸筹信号
    if accumulation:
        accumulation_sorted = sorted(accumulation, key=lambda x: (x["score"], x["market_cap"]), reverse=True)
        
        # 一级告警：Top 3 高置信度信号发送单独卡片
        high_confidence = [i for i in accumulation_sorted if i["score"] >= 0.85][:3]
        for item in high_confidence:
            await _send_signal_card(item)
            await asyncio.sleep(0.3)
        
        # 二级告警：其余信号发送紧凑列表
        remaining = [i for i in accumulation_sorted if i not in high_confidence]
        if remaining:
            await _send_summary_embed(
                title="🟪 稳定吸筹概览",
                items=remaining,
                color=DiscordColors.PURPLE,
                description_prefix="**特征:** 连续3日量能稳定 + 价格横盘\n**含义:** 主力控盘吸筹迹象明显"
            )
    
    # 发送洗盘结束信号
    if wash_complete:
        wash_sorted = sorted(wash_complete, key=lambda x: (x["score"], x["market_cap"]), reverse=True)
        
        high_confidence = [i for i in wash_sorted if i["score"] >= 0.85][:3]
        for item in high_confidence:
            await _send_signal_card(item)
            await asyncio.sleep(0.3)
        
        remaining = [i for i in wash_sorted if i not in high_confidence]
        if remaining:
            await _send_summary_embed(
                title="🟨 洗盘结束概览",
                items=remaining,
                color=DiscordColors.YELLOW,
                description_prefix="**特征:** 连续缩量 + 价格企稳\n**含义:** 卖盘枯竭，可能触底"
            )
    
    # 发送牛旗信号
    if bull_flag:
        flag_sorted = sorted(bull_flag, key=lambda x: (x["score"], x["market_cap"]), reverse=True)
        
        high_confidence = [i for i in flag_sorted if i["score"] >= 0.8][:3]
        for item in high_confidence:
            await _send_signal_card(item)
            await asyncio.sleep(0.3)
        
        remaining = [i for i in flag_sorted if i not in high_confidence]
        if remaining:
            await _send_summary_embed(
                title="🟩 牛旗整理概览",
                items=remaining,
                color=DiscordColors.GREEN,
                description_prefix="**特征:** 昨日放量大涨 + 今日缩量回调\n**含义:** 良性整理，上涨中继"
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



