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
    signal_type: str  # ACCUMULATION_STABLE, WASH_COMPLETE, NEUTRAL
    score: float  # 0-1 置信度
    reason: str
    details: dict = None
    # 三日数据 (用于展示)
    history_3d: list = None  # [T0, T-1, T-2] 每项包含 volume, price, market_cap, turnover


@dataclass
class MarketTierConfig:
    """不同市值层级的动态阈值配置"""
    name: str
    min_mcap: float
    max_cv: float          # 允许的最大交易量变异系数 (越小越严)
    max_price_dev: float   # 允许的最大价格偏差 (%, ±值)
    min_turnover: float    # 最低换手率要求
    vol_weight: float      # 交易量权重
    price_weight: float    # 价格权重


# 定义分层配置
MARKET_TIERS: list[MarketTierConfig] = [
    MarketTierConfig("LARGE", 100_000_000, max_cv=0.10, max_price_dev=2.0, min_turnover=0.01, vol_weight=0.5, price_weight=0.5),
    MarketTierConfig("MID",   10_000_000, max_cv=0.18, max_price_dev=4.0, min_turnover=0.02, vol_weight=0.4, price_weight=0.6),
    MarketTierConfig("SMALL",  5_000_000, max_cv=0.30, max_price_dev=8.0, min_turnover=0.03, vol_weight=0.3, price_weight=0.7),
]


class ScoringConfig:
    """评分与风控配置"""
    # 市值门槛 (单位: USD)
    MIN_MCAP_THRESHOLD = 1_000_000         # 1M: 低于此值直接忽略
    TARGET_MCAP_MIN = 10_000_000           # 10M: 重点关注下限
    TARGET_MCAP_MAX = 100_000_000          # 100M: 重点关注上限

    # 换手率健康区间
    TURNOVER_HEALTHY_MIN = 0.03            # 3%: 低于此值流动性差
    TURNOVER_HEALTHY_MAX = 0.30            # 30%: 高于此值可能过热/P&D风险

    # 权重配置
    WEIGHT_PATTERN = 0.6                   # 形态权重 (技术面)
    WEIGHT_MCAP = 0.3                      # 市值权重 (策略面)
    WEIGHT_LIQUIDITY = 0.1                 # 流动性权重 (资金面)


class ConfidenceEngine:
    """置信度计算引擎
    
    基于市值分层和换手率健康度，对基础形态分数进行加权调整。
    重点关注 10M-100M 黄金区间，过滤 <1M 垃圾盘。
    """

    @staticmethod
    def calculate_score(base_score: float, market_cap: float, turnover: float) -> tuple[float, str]:
        """计算最终置信度
        
        Args:
            base_score: 基础形态分数 (0-1)
            market_cap: 市值 (USD)
            turnover: 换手率 (0-1)
            
        Returns:
            (final_score, mcap_tag): 最终分数和市值标签
        """
        # 1. 市值系数 (Market Cap Multiplier)
        mcap_score = 1.0
        mcap_tag = ""

        if ScoringConfig.TARGET_MCAP_MIN <= market_cap <= ScoringConfig.TARGET_MCAP_MAX:
            # 黄金区间 (10M-100M): 给予加成
            mcap_score = 1.2
            mcap_tag = "[黄金市值]"
        elif market_cap > ScoringConfig.TARGET_MCAP_MAX:
            # 大市值: 保持标准
            mcap_score = 1.0
            mcap_tag = "[大市值稳健]"
        elif market_cap >= 5_000_000:
            # 小市值 (5M-10M): 降权
            mcap_score = 0.85
            mcap_tag = "[小市值高风]"
        else:
            # 微型市值 (1M-5M): 重度降权
            mcap_score = 0.7
            mcap_tag = "[微型市值]"

        # 2. 换手率修正 (Turnover Correction)
        # 使用正态分布逻辑，中间优，两头差
        turnover_score = 1.0
        if turnover < ScoringConfig.TURNOVER_HEALTHY_MIN:
            turnover_score = 0.7  # 流动性不足
        elif turnover > ScoringConfig.TURNOVER_HEALTHY_MAX:
            turnover_score = 0.8  # 过热风险
        else:
            turnover_score = 1.1  # 健康换手

        # 3. 综合计算
        # 基础分 * 市值系数 * 换手修正 (限制最大值为 0.99)
        raw_final = base_score * mcap_score * turnover_score
        final_score = min(0.99, raw_final)

        return final_score, mcap_tag

    @staticmethod
    def get_score_emoji(score: float) -> str:
        """根据置信度返回 Emoji"""
        if score >= 0.9:
            return "🔥"  # 极高置信度 (通常是黄金市值+完美形态)
        if score >= 0.8:
            return "⭐"  # 高置信度
        if score >= 0.7:
            return "🔹"  # 中等置信度
        return "⚪"  # 低置信度


class DynamicTrendAnalyzer:
    """基于市值分层的动态趋势分析器
    
    核心改进:
    1. 动态阈值：根据市值分层调整 CV/价格偏差容忍度
    2. 加权评分：集成 ConfidenceEngine 进行市值分层加权
    3. 多策略检测：吸筹、洗盘结束、牛旗整理
    """

    @staticmethod
    def _get_tier(market_cap: float) -> MarketTierConfig:
        """根据市值获取对应层级的配置"""
        for tier in MARKET_TIERS:
            if market_cap >= tier.min_mcap:
                return tier
        return MARKET_TIERS[-1]

    @staticmethod
    def _normalize_score(value: float, threshold: float, inverse: bool = True) -> float:
        """归一化打分函数 (0-1)
        inverse=True: 值越小分越高 (如CV)
        inverse=False: 值越大分越高 (如换手率)
        """
        if inverse:
            if value >= threshold:
                return 0.0
            return 1.0 - (value / threshold)
        if value >= threshold:
            return 1.0
        return min(value / threshold, 1.0)

    @staticmethod
    def analyze(history_3d: list[dict]) -> Optional[TrendSignal]:
        """分析三日趋势并返回信号
        
        Args:
            history_3d: 三日数据列表 [T0, T-1, T-2]，每项包含 volume, price, market_cap
            
        Returns:
            TrendSignal 或 None
        """
        if len(history_3d) < 3:
            return None

        d0, d1, d2 = history_3d[0], history_3d[1], history_3d[2]
        volumes = [d['volume'] for d in history_3d]
        prices = [d['price'] for d in history_3d]
        market_cap = d0.get("market_cap", 0)

        # 获取该币种的动态阈值配置
        config = DynamicTrendAnalyzer._get_tier(market_cap)

        # 计算统计指标
        vol_mean = sum(volumes) / 3
        vol_std = (sum((v - vol_mean) ** 2 for v in volumes) / 3) ** 0.5
        vol_cv = vol_std / vol_mean if vol_mean > 0 else float('inf')

        # 价格变化序列
        p_changes = [
            ((prices[0] - prices[1]) / prices[1] * 100) if prices[1] else 0,
            ((prices[1] - prices[2]) / prices[2] * 100) if prices[2] else 0
        ]
        max_p_change = max(abs(c) for c in p_changes)

        # 换手率
        avg_turnover = sum(d.get("volume", 0) / d.get("market_cap", 1) for d in history_3d) / 3
        current_turnover = d0.get("volume", 0) / market_cap if market_cap > 0 else 0

        # 构建返回用的历史数据
        history_enriched = []
        for d in history_3d:
            history_enriched.append({
                "volume": d["volume"],
                "price": d["price"],
                "market_cap": d.get("market_cap", 0),
                "turnover": d.get("volume", 0) / d.get("market_cap", 1) if d.get("market_cap") else 0
            })

        # ==========================================
        # 策略 A: 智能吸筹检测 (Accumulation)
        # ==========================================
        # 逻辑：价格要在动态阈值内横盘，且量能稳定

        # A1. 量能稳定性得分 (CV越低分越高)
        score_vol_stability = DynamicTrendAnalyzer._normalize_score(vol_cv, config.max_cv, inverse=True)

        # A2. 价格横盘得分 (变化幅度越小分越高)
        score_price_flat = DynamicTrendAnalyzer._normalize_score(max_p_change, config.max_price_dev, inverse=True)

        # A3. 活跃度惩罚 (如果是死盘，直接扣分)
        active_ratio = min(avg_turnover / config.min_turnover, 1.0) if config.min_turnover > 0 else 0

        # 基础形态分数 (加权)
        base_accumulation_score = (
            score_vol_stability * config.vol_weight +
            score_price_flat * config.price_weight
        ) * active_ratio

        if base_accumulation_score > 0.60:  # 基础门槛降低，让 ConfidenceEngine 决定最终分数
            # 使用 ConfidenceEngine 计算最终置信度
            final_score, mcap_tag = ConfidenceEngine.calculate_score(
                base_accumulation_score, market_cap, current_turnover
            )

            # 最终分数过滤
            if final_score >= 0.60:
                return TrendSignal(
                    signal_type="ACCUMULATION_STABLE",
                    score=round(final_score, 2),
                    reason=f"{mcap_tag} [{config.name}级] 量稳({score_vol_stability:.2f}) 价平({score_price_flat:.2f})",
                    details={
                        "tier": config.name,
                        "mcap_tag": mcap_tag,
                        "vol_cv": round(vol_cv, 4),
                        "max_p_change": round(max_p_change, 2),
                        "avg_turnover": round(avg_turnover, 4),
                        "base_score": round(base_accumulation_score, 2)
                    },
                    history_3d=history_enriched
                )

        # ==========================================
        # 策略 B: 洗盘结束 (Wash Complete)
        # ==========================================
        # 逻辑：连续缩量 + 价格企稳

        # B1. 缩量得分 (今天<昨天<前天)
        is_shrinking = volumes[0] < volumes[1] < volumes[2]
        shrink_magnitude = (volumes[2] - volumes[0]) / volumes[2] if volumes[2] > 0 else 0
        score_shrink = 0.8 if is_shrinking else 0.0
        if is_shrinking and 0.3 <= shrink_magnitude <= 0.7:
            # 如果缩量幅度在 30%-70% 之间，加分 (缩太少没意义，缩太多可能是归零)
            score_shrink += 0.2

        # B2. 企稳得分 (今天价格没跌 或 微跌)
        # 容忍微跌 -1.5% 到 +inf
        score_stabilize = 1.0 if p_changes[0] > -1.5 else 0.0

        base_wash_score = (score_shrink * 0.6 + score_stabilize * 0.4)

        if base_wash_score > 0.70:
            # 使用 ConfidenceEngine 计算最终置信度
            final_score, mcap_tag = ConfidenceEngine.calculate_score(
                base_wash_score, market_cap, current_turnover
            )

            if final_score >= 0.60:
                return TrendSignal(
                    signal_type="WASH_COMPLETE",
                    score=round(final_score, 2),
                    reason=f"{mcap_tag} 连续缩量({shrink_magnitude*100:.1f}%)且价格企稳",
                    details={
                        "tier": config.name,
                        "mcap_tag": mcap_tag,
                        "shrink_mag": round(shrink_magnitude, 4),
                        "base_score": round(base_wash_score, 2)
                    },
                    history_3d=history_enriched
                )

        # ==========================================
        # 策略 C: 牛旗整理 (Bull Flag)
        # ==========================================
        # 逻辑：前日放量大涨 + 昨日/今日缩量回调

        # C1. 前日是否放量大涨
        is_prev_pump = (
            p_changes[1] > 10 and  # T-2 到 T-1 涨幅 > 10%
            volumes[1] > volumes[2] * 1.5  # T-1 量能 > T-2 * 1.5
        )

        # C2. 今日是否缩量整理
        is_now_correction = (
            -5 < p_changes[0] < 5 and  # T-1 到 T0 波动 < ±5%
            volumes[0] < volumes[1] * 0.7  # T0 量能 < T-1 * 0.7
        )

        if is_prev_pump and is_now_correction:
            base_flag_score = 0.75
            final_score, mcap_tag = ConfidenceEngine.calculate_score(
                base_flag_score, market_cap, current_turnover
            )

            if final_score >= 0.60:
                return TrendSignal(
                    signal_type="BULL_FLAG",
                    score=round(final_score, 2),
                    reason=f"{mcap_tag} 昨日放量涨{p_changes[1]:.1f}%，今日缩量整理",
                    details={
                        "tier": config.name,
                        "mcap_tag": mcap_tag,
                        "prev_pump_pct": round(p_changes[1], 2),
                        "vol_shrink_ratio": round(volumes[0] / volumes[1], 2) if volumes[1] > 0 else 0,
                        "base_score": round(base_flag_score, 2)
                    },
                    history_3d=history_enriched
                )

        return TrendSignal(
            signal_type="NEUTRAL",
            score=0.1,
            reason="无明显特征",
            details={"tier": config.name, "vol_cv": round(vol_cv, 4)},
            history_3d=history_enriched
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
    1. 硬性市值过滤 (< MIN_MCAP_THRESHOLD 直接忽略)
    2. 批量处理所有项目，更新今日数据到历史记录
    3. 基于三日历史数据进行趋势分析 (换手率/吸筹/洗盘)
    4. 使用 ConfidenceEngine 进行置信度加权
    5. 智能排序并发送告警
    
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
    
    # ============================================
    # 阶段1: 硬性过滤 + 批量更新今日数据
    # ============================================
    print("阶段1: 硬性过滤及批量更新今日数据...")
    processed_symbols = []
    valid_crypto_list = []  # 用于后续分析的清洗后列表
    filtered_count = 0
    
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
        
        # ---> 硬性市值过滤 <---
        if market_cap < ScoringConfig.MIN_MCAP_THRESHOLD:
            filtered_count += 1
            continue  # 直接跳过 < 1M 的代币
        
        valid_crypto_list.append(crypto)
        
        # 保存今日数据 (不过滤，便于后续趋势分析)
        if volume_24h > 0 and price > 0:
            history_manager.update(today_str, symbol, {
                "volume": volume_24h,
                "price": price,
                "market_cap": market_cap
            })
            processed_symbols.append(symbol)
    
    print(f"过滤后剩余关注项目: {len(valid_crypto_list)} (原: {len(crypto_list)}, 过滤: {filtered_count})")
    print(f"已更新 {len(processed_symbols)} 个项目的今日数据")
    
    # ============================================
    # 阶段2: 基于三日数据进行趋势分析
    # ============================================
    print("\n阶段2: 三日趋势分析...")
    
    alerts = []
    dealer_accumulation_alerts = []  # 吸筹: 量增价平/小涨
    dealer_distribution_alerts = []  # 出货/洗盘: 量增价跌
    trend_signals = []  # 三日趋势信号 (稳定吸筹/洗盘结束)
    
    for crypto in valid_crypto_list:  # 使用过滤后的列表
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
        price = usd_quote.get("price", 0)
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
            history_3d = [h_today, h_yest, h_before]
            trend_signal = DynamicTrendAnalyzer.analyze(history_3d)
            
            if trend_signal and trend_signal.signal_type != "NEUTRAL":
                should_alert = False
                if trend_signal.score >= 0.85:
                    should_alert = True
                elif trend_signal.score >= 0.75 and market_cap > 5_000_000:
                    should_alert = True
                
                if should_alert:
                    signal_data = {
                        "symbol": symbol,
                        "name": name,
                        "signal_type": trend_signal.signal_type,
                        "score": trend_signal.score,
                        "reason": trend_signal.reason,
                        "details": trend_signal.details,
                        "volume": volume_24h,
                        "market_cap": market_cap,
                        "fdv": fullyDilluttedMarketCap,
                        "platform": platform,
                        "price_change": price_change_24h,
                        "vol_change": vol_change_24h,
                        "history_3d": trend_signal.history_3d
                    }
                    trend_signals.append(signal_data)
                    
                    if trend_signal.signal_type == "ACCUMULATION_STABLE" and trend_signal.score > 0.8:
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
        # 庄家行为检测 (当日维度 + 置信度加权)
        # ============================================
        is_accumulation = False
        current_turnover = volume_24h / market_cap if market_cap > 0 else 0
        
        if vol_change_24h > threshold and volume_24h >= MIN_VOLUME_24H:
            # 计算动态置信度 (即使不是三日趋势，单日异动也可以有置信度)
            base_alert_score = 0.65  # 单日异动基础分
            alert_score, mcap_tag = ConfidenceEngine.calculate_score(
                base_alert_score, market_cap, current_turnover
            )
            score_emoji = ConfidenceEngine.get_score_emoji(alert_score)
            
            alert_data = {
                "symbol": symbol,
                "name": name,
                "vol_change": vol_change_24h,
                "price_change": price_change_24h,
                "volume": volume_24h,
                "market_cap": market_cap,
                "fdv": fullyDilluttedMarketCap,
                "platform": platform,
                "price": price,
                "history_3d": history_3d_enriched,  # 添加三日数据
                "score": alert_score,  # 新增分数
                "mcap_tag": mcap_tag,  # 新增标签
                "score_emoji": score_emoji  # 新增 emoji
            }
            
            # 只有分数达标才加入警报
            if alert_score >= 0.55:
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
    
    # ============================================
    # 智能排序 (Sorting Optimization)
    # ============================================
    # 不再单纯按市值排序，而是按 [置信度 desc, 市值 desc] 排序
    # 这样 10M-100M 的高分项目会排在 500M 的普通项目前面
    
    def smart_sort_key(item):
        """智能排序键: (置信度, 市值)"""
        return (item.get("score", 0), item.get("market_cap", 0))
    
    # 趋势信号按置信度和市值排序
    trend_signals.sort(key=smart_sort_key, reverse=True)
    
    # 吸筹告警按置信度和市值排序
    dealer_accumulation_alerts.sort(key=smart_sort_key, reverse=True)
    
    # 出货/洗盘告警按置信度和市值排序
    dealer_distribution_alerts.sort(key=smart_sort_key, reverse=True)
    
    # 常规异动按24h变化率排序
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
    fdv = signal_data.get("fdv", 0)
    price_change = signal_data.get("price_change", 0)
    price = signal_data.get("price", 0)
    platform = signal_data.get("platform", "")
    details = signal_data.get("details", {}) or {}
    tier_name = details.get("tier", "UNKNOWN")
    mcap_tag = details.get("mcap_tag", "")
    
    # 获取置信度 Emoji
    score_emoji = ConfidenceEngine.get_score_emoji(score)
    
    # 构建标题 (时间放最前面)
    signal_emoji = _get_signal_emoji(signal_type)
    signal_name = _get_signal_name(signal_type)
    title = f"{signal_emoji} {symbol} 发现{signal_name}信号 {score_emoji}"
    
    # 构建描述（时间放最上方，市值和FDV突出显示）
    price_emoji = "📈" if price_change > 0 else "📉" if price_change < 0 else "➡️"
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    description = f"⏰ **{current_time}**\n\n"
    description += f"**{name}** | {platform}\n"
    description += f"💰 **MC: ${_format_number(market_cap)}** | **FDV: ${_format_number(fdv)}**\n"
    if price > 0:
        description += f"💵 当前价格: **${price:.6g}**\n"
    description += f"📊 24h价格: **{price_change:+.2f}%** {price_emoji}"
    
    # 构建三日量价趋势 (垂直布局)
    fields = []

    # 置信度与分层信息
    fields.append({
        "name": "🎚️ 置信度分析",
        "value": f"**得分: {score:.2f}/1.0** {score_emoji} (等级: {tier_name}) {mcap_tag}\n说明: {reason}",
        "inline": False
    })
    
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
            "text": f"基于市值分层的动态阈值 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
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
    
    # 构建描述内容 (时间放最上方)
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lines = [f"⏰ **{current_time}**\n"]
    
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
        fdv = _format_number(item.get("fdv", 0))
        price = item.get("price", 0)
        score = item.get("score", 0)
        mcap_tag = item.get("mcap_tag", "")
        
        # 获取置信度 Emoji
        score_emoji = ConfidenceEngine.get_score_emoji(score) if score > 0 else ""
        
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
        
        # 添加置信度信息
        score_info = f" | 置信度: {score:.2f} {score_emoji}" if score > 0 else ""
        mcap_info = f" {mcap_tag}" if mcap_tag else ""
        
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
        
        # 价格信息
        price_info = f" | Price: ${price:.6g}" if price > 0 else ""
        
        block = (
            f"**{i}. {symbol}** ({name}){mcap_info}\n"
            f"├─ 💰 **MC: ${market_cap}** | **FDV: ${fdv}**{price_info}\n"
            f"├─ T0 Vol: ${volume} ({vol_change:+.0f}% {vol_emoji})\n"
            f"{history_lines}"
            f"├─ Price: {price_change:+.1f}% {price_emoji}{score_info}\n"
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
            "text": f"基于市值分层的动态阈值 | {current_time}"
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
            "代号", "名称", "信号类型", "置信度", "市值分层", "市值标签", "交易量变化(%)", "价格变化(%)",
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
        
        details = item.get("details", {}) or {}
        tier_name = details.get("tier", "-")
        mcap_tag = details.get("mcap_tag", "-")
        row = {
            "代号": item.get("symbol", "-"),
            "名称": item.get("name", "-"),
            "信号类型": signal_name,
            "置信度": f"{item.get('score', 0):.2f}",
            "市值分层": tier_name,
            "市值标签": mcap_tag,
            "交易量变化(%)": f"{item.get('vol_change', 0):+.1f}%",
            "价格变化(%)": f"{item.get('price_change', 0):+.1f}%",
            "24h交易量": f"${_format_number(item.get('volume', 0))}",
            "市值": f"${_format_number(item.get('market_cap', 0))}",
            "FDV": f"${_format_number(item.get('fdv', 0))}",
            "平台": item.get("platform", "-"),
            "信号解读": item.get("reason", "-"),
            "signal_type_raw": signal_type,
            "score_raw": item.get("score", 0),
            "tier_raw": tier_name,
            "mcap_tag_raw": mcap_tag,
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
        score = item.get("score", 0.70 if not item.get("is_continuous") else 0.85)
        mcap_tag = item.get("mcap_tag", "-")
        
        # 计算市值分层
        market_cap = item.get("market_cap", 0)
        if market_cap >= 100_000_000:
            tier_name = "LARGE"
        elif market_cap >= 10_000_000:
            tier_name = "MID"
        elif market_cap >= 5_000_000:
            tier_name = "SMALL"
        else:
            tier_name = "MICRO"
        
        row = {
            "代号": symbol,
            "名称": item.get("name", "-"),
            "信号类型": "疑似吸筹" if not item.get("is_continuous") else "持续吸筹",
            "置信度": f"{score:.2f}",
            "市值分层": tier_name,
            "市值标签": mcap_tag,
            "交易量变化(%)": f"{item.get('vol_change', 0):+.1f}%",
            "价格变化(%)": f"{item.get('price_change', 0):+.1f}%",
            "24h交易量": f"${_format_number(item.get('volume', 0))}",
            "市值": f"${_format_number(item.get('market_cap', 0))}",
            "FDV": f"${_format_number(item.get('fdv', 0))}",
            "平台": item.get("platform", "-"),
            "信号解读": "量增价平/小涨" + (" + 连续3日稳定" if item.get("is_continuous") else "") + f" {mcap_tag}",
            "signal_type_raw": "ACCUMULATION_SINGLE" if not item.get("is_continuous") else "ACCUMULATION_CONTINUOUS",
            "score_raw": score,
            "tier_raw": tier_name,
            "mcap_tag_raw": mcap_tag,
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
        score = item.get("score", 0.65)
        mcap_tag = item.get("mcap_tag", "-")
        
        # 计算市值分层
        market_cap = item.get("market_cap", 0)
        if market_cap >= 100_000_000:
            tier_name = "LARGE"
        elif market_cap >= 10_000_000:
            tier_name = "MID"
        elif market_cap >= 5_000_000:
            tier_name = "SMALL"
        else:
            tier_name = "MICRO"
        
        row = {
            "代号": symbol,
            "名称": item.get("name", "-"),
            "信号类型": "疑似出货/洗盘",
            "置信度": f"{score:.2f}",
            "市值分层": tier_name,
            "市值标签": mcap_tag,
            "交易量变化(%)": f"{item.get('vol_change', 0):+.1f}%",
            "价格变化(%)": f"{item.get('price_change', 0):+.1f}%",
            "24h交易量": f"${_format_number(item.get('volume', 0))}",
            "市值": f"${_format_number(item.get('market_cap', 0))}",
            "FDV": f"${_format_number(item.get('fdv', 0))}",
            "平台": item.get("platform", "-"),
            "信号解读": f"量增价跌，注意风险 {mcap_tag}",
            "signal_type_raw": "DISTRIBUTION",
            "score_raw": score,
            "tier_raw": tier_name,
            "mcap_tag_raw": mcap_tag,
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



