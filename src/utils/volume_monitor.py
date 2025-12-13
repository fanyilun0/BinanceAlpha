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

    # ==========================================
    # 优化: 提高硬性过滤门槛，剔除噪音
    # ==========================================
    MIN_VOLUME_24H = 3_000_000             # 3M: 最低24h交易量门槛 (原2.4M)
    MIN_TURNOVER = 0.02                    # 2%: 最低换手率，剔除死盘
    
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


# ==============================================================================
# SignalArbiter: 信号仲裁器 - 实现"赢家通吃"去重逻辑
# ==============================================================================

class SignalCategory:
    """信号分类枚举"""
    ALPHA_TREND = "alpha_trend"           # 🎯 Alpha: 完美三日趋势
    ALPHA_WHALE = "alpha_whale"           # 🎯 Alpha: 巨鲸吸筹
    RISK_DISTRIBUTION = "risk_distribution"  # ⚠️ 风险: 主力出货
    ANOMALY_EXTREME = "anomaly_extreme"   # ⚠️ 异动: 极端爆量


@dataclass
class ClassifiedSignal:
    """分类后的信号"""
    symbol: str
    name: str
    category: str           # SignalCategory
    sub_type: str           # 细分类型: ACCUMULATION_STABLE, WASH_COMPLETE, BULL_FLAG, etc.
    score: float            # 置信度 0-1
    mcap_tag: str           # 市值标签
    data: dict              # 原始数据
    reason: str             # 信号原因


class SignalArbiter:
    """信号仲裁器
    
    核心职责：
    1. 按优先级顺序判定每个代币的最终分类
    2. 实现"赢家通吃"：一个代币只能归入一个类别
    3. 输出两条数据流：🎯 Alpha + ⚠️ 异动
    
    优先级顺序：
    1. Trend (完美三日趋势) → Alpha
    2. Accumulation (强力吸筹, score > 0.8) → Alpha  
    3. Distribution (出货) → 异动/风险
    4. Extreme Vol (极端波动) → 异动
    """
    
    # 阈值配置
    ALPHA_WHALE_MIN_SCORE = 0.80          # 巨鲸吸筹最低分
    EXTREME_VOL_MIN_CHANGE = 100          # 极端爆量最低变化率 (%)
    EXTREME_VOL_MIN_TURNOVER = 0.05       # 极端爆量最低换手率 (5%)
    
    def __init__(self):
        self.alpha_signals: list[ClassifiedSignal] = []
        self.anomaly_signals: list[ClassifiedSignal] = []
        self._processed_symbols: set[str] = set()
    
    def classify(
        self,
        trend_signals: list[dict],
        accumulation_alerts: list[dict],
        distribution_alerts: list[dict],
        volume_alerts: list[dict]
    ) -> tuple[list[ClassifiedSignal], list[ClassifiedSignal]]:
        """执行分类仲裁
        
        Args:
            trend_signals: 三日趋势信号
            accumulation_alerts: 吸筹告警
            distribution_alerts: 出货告警
            volume_alerts: 常规交易量异动
            
        Returns:
            (alpha_signals, anomaly_signals)
        """
        self.alpha_signals.clear()
        self.anomaly_signals.clear()
        self._processed_symbols.clear()
        
        # ========================================
        # Priority 1: 完美三日趋势 → Alpha
        # ========================================
        for item in trend_signals:
            symbol = item.get("symbol", "")
            if not symbol or symbol in self._processed_symbols:
                continue
            
            signal = ClassifiedSignal(
                symbol=symbol,
                name=item.get("name", ""),
                category=SignalCategory.ALPHA_TREND,
                sub_type=item.get("signal_type", "TREND"),
                score=item.get("score", 0),
                mcap_tag=item.get("details", {}).get("mcap_tag", "") if item.get("details") else "",
                data=item,
                reason=item.get("reason", "三日趋势信号")
            )
            self.alpha_signals.append(signal)
            self._processed_symbols.add(symbol)
        
        # ========================================
        # Priority 2: 强力吸筹 (高分) → Alpha
        # ========================================
        for item in accumulation_alerts:
            symbol = item.get("symbol", "")
            if not symbol or symbol in self._processed_symbols:
                continue
            
            score = item.get("score", 0)
            # 只有高分吸筹才进入 Alpha
            if score >= self.ALPHA_WHALE_MIN_SCORE or item.get("is_continuous"):
                reason = "巨鲸吸筹 (量增价平)"
                if item.get("is_continuous"):
                    reason += " + 连续3日稳定"
                signal = ClassifiedSignal(
                    symbol=symbol,
                    name=item.get("name", ""),
                    category=SignalCategory.ALPHA_WHALE,
                    sub_type="ACCUMULATION_WHALE",
                    score=score,
                    mcap_tag=item.get("mcap_tag", ""),
                    data=item,
                    reason=reason
                )
                self.alpha_signals.append(signal)
                self._processed_symbols.add(symbol)
        
        # ========================================
        # Priority 3: 主力出货 → 异动/风险
        # ========================================
        for item in distribution_alerts:
            symbol = item.get("symbol", "")
            if not symbol or symbol in self._processed_symbols:
                continue
            
            signal = ClassifiedSignal(
                symbol=symbol,
                name=item.get("name", ""),
                category=SignalCategory.RISK_DISTRIBUTION,
                sub_type="DISTRIBUTION",
                score=item.get("score", 0.65),
                mcap_tag=item.get("mcap_tag", ""),
                data=item,
                reason=f"放量下跌 {item.get('price_change', 0):+.1f}%"
            )
            self.anomaly_signals.append(signal)
            self._processed_symbols.add(symbol)
        
        # ========================================
        # Priority 4: 低分吸筹 → 异动
        # ========================================
        for item in accumulation_alerts:
            symbol = item.get("symbol", "")
            if not symbol or symbol in self._processed_symbols:
                continue
            
            score = item.get("score", 0)
            # 低分吸筹进入异动
            signal = ClassifiedSignal(
                symbol=symbol,
                name=item.get("name", ""),
                category=SignalCategory.ANOMALY_EXTREME,
                sub_type="ACCUMULATION_SINGLE",
                score=score,
                mcap_tag=item.get("mcap_tag", ""),
                data=item,
                reason=f"单日吸筹 (Vol+{item.get('vol_change', 0):.0f}%)"
            )
            self.anomaly_signals.append(signal)
            self._processed_symbols.add(symbol)
        
        # ========================================
        # Priority 5: 极端交易量异动 → 异动
        # ========================================
        for item in volume_alerts:
            symbol = item.get("symbol", "")
            if not symbol or symbol in self._processed_symbols:
                continue
            
            change = abs(item.get("change_24h", 0))
            turnover = item.get("volume_24h", 0) / item.get("market_cap", 1) if item.get("market_cap", 0) > 0 else 0
            
            # 只保留极端异动
            if change >= self.EXTREME_VOL_MIN_CHANGE and turnover >= self.EXTREME_VOL_MIN_TURNOVER:
                price_change = item.get("price_change", 0)
                if price_change > 10:
                    reason = "🔥 放量上涨"
                elif price_change < -5:
                    reason = "⚠️ 放量下跌"
                else:
                    reason = "📊 极端爆量"
                
                signal = ClassifiedSignal(
                    symbol=symbol,
                    name=item.get("name", ""),
                    category=SignalCategory.ANOMALY_EXTREME,
                    sub_type="EXTREME_VOLUME",
                    score=0.5,  # 极端爆量基础分较低
                    mcap_tag="",
                    data=item,
                    reason=reason
                )
                self.anomaly_signals.append(signal)
                self._processed_symbols.add(symbol)
        
        # 排序：按 score desc, market_cap desc
        self.alpha_signals.sort(key=lambda x: (x.score, x.data.get("market_cap", 0)), reverse=True)
        self.anomaly_signals.sort(key=lambda x: (x.score, x.data.get("market_cap", 0)), reverse=True)
        
        return self.alpha_signals, self.anomaly_signals
    
    def get_stats(self) -> dict:
        """获取分类统计"""
        alpha_by_type = {}
        for s in self.alpha_signals:
            alpha_by_type[s.sub_type] = alpha_by_type.get(s.sub_type, 0) + 1
        
        anomaly_by_type = {}
        for s in self.anomaly_signals:
            anomaly_by_type[s.sub_type] = anomaly_by_type.get(s.sub_type, 0) + 1
        
        return {
            "alpha_total": len(self.alpha_signals),
            "alpha_by_type": alpha_by_type,
            "anomaly_total": len(self.anomaly_signals),
            "anomaly_by_type": anomaly_by_type,
            "processed_symbols": len(self._processed_symbols)
        }


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
                    reason=f"[{config.name}] 量稳({score_vol_stability:.2f}) 价平({score_price_flat:.2f})",
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
                    reason=f"[{config.name}] 连续缩量({shrink_magnitude*100:.1f}%)且价格企稳",
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
                    reason=f"[{config.name}] 昨日放量涨{p_changes[1]:.1f}%，今日缩量整理",
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
    1. 硬性市值过滤
    2. 批量处理所有项目，更新今日数据
    3. 基于三日历史数据进行趋势分析
    4. 置信度加权
    5. 智能排序并发送告警
    """
    print(f"=== 监控交易量变化 (阈值: {threshold}%) ===\n")
    
    # 初始化历史数据管理器
    history_manager = HistoryManager(os.path.join(project_root, 'data'))
    today_str = datetime.now().strftime('%Y-%m-%d')
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    day_before_str = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    three_days_ago_str = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
    
    # 加载4天数据文件 (T0, T-1, T-2, T-3)
    # T-3 用于计算 T-2 的价格涨跌幅
    multi_day_data = load_multi_day_data(days=4)
    t0_list = multi_day_data.get("T0", [])
    t1_list = multi_day_data.get("T-1", [])
    t2_list = multi_day_data.get("T-2", [])
    t3_list = multi_day_data.get("T-3", [])
    
    # 构建索引
    t1_index = _build_crypto_index(t1_list)
    t2_index = _build_crypto_index(t2_list)
    t3_index = _build_crypto_index(t3_list)
    
    if crypto_list is None:
        if not t0_list:
            print("无法加载数据，监控终止")
            return {"alerts": [], "triggered_count": 0}
        crypto_list = t0_list
        print(f"已加载 {len(crypto_list)} 个项目数据")

    # 使用统一配置的交易量门槛
    MIN_VOLUME_24H = ScoringConfig.MIN_VOLUME_24H
    
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
        
        # ---> 硬性过滤 (优化: 增加交易量和换手率门槛) <---
        # 1. 市值过滤
        if market_cap < ScoringConfig.MIN_MCAP_THRESHOLD:
            filtered_count += 1
            continue  # 直接跳过 < 1M 的代币
        
        # 2. 交易量过滤 (新增)
        if volume_24h < ScoringConfig.MIN_VOLUME_24H:
            filtered_count += 1
            continue  # 跳过低交易量代币
        
        # 3. 换手率过滤 (新增: 剔除死盘)
        turnover = volume_24h / market_cap if market_cap > 0 else 0
        if turnover < ScoringConfig.MIN_TURNOVER:
            filtered_count += 1
            continue  # 跳过换手率过低的代币
        
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
        h_today = {"volume": volume_24h, "price": price, "market_cap": market_cap}
        
        # 辅助函数: 获取历史数据
        def _get_history(idx_map, fallback_date):
            d_crypto = idx_map.get(symbol)
            if d_crypto:
                t_quotes = d_crypto.get("quotes", [])
                t_usd = next((q for q in t_quotes if q.get("name") == "USD"), {})
                if not t_usd and len(t_quotes) > 2:
                    t_usd = t_quotes[2]
                if t_usd:
                    return {
                        "volume": t_usd.get("volume24h", 0),
                        "price": t_usd.get("price", 0),
                        "market_cap": t_usd.get("marketCap", 0)
                    }
            return history_manager.get_data(symbol, fallback_date)

        h_yest = _get_history(t1_index, yesterday_str)
        h_before = _get_history(t2_index, day_before_str)
        h_t3 = _get_history(t3_index, three_days_ago_str)
        
        trend_signal = None
        is_continuous_accumulation = False
        
        # 趋势分析只看 T0-T2 (保持策略逻辑不变)
        if h_today and h_yest and h_before:
            history_analyze = [h_today, h_yest, h_before]
            trend_signal = DynamicTrendAnalyzer.analyze(history_analyze)
            
            # 如果有 T-3 数据，追加到 history_3d 列表供展示使用
            # 这是一个关键 Hack: analyze 返回的 history_3d 只有3个，我们这里扩充为4个
            if trend_signal and h_t3:
                 t3_turnover = h_t3.get("volume", 0) / h_t3.get("market_cap", 1) if h_t3.get("market_cap") else 0
                 trend_signal.history_3d.append({
                     "volume": h_t3.get("volume", 0),
                     "price": h_t3.get("price", 0),
                     "market_cap": h_t3.get("market_cap", 0),
                     "turnover": t3_turnover
                 })

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
                        "price": price,
                        "price_change": price_change_24h,
                        "vol_change": vol_change_24h,
                        "history_3d": trend_signal.history_3d
                    }
                    trend_signals.append(signal_data)
                    
                    if trend_signal.signal_type == "ACCUMULATION_STABLE" and trend_signal.score > 0.8:
                        is_continuous_accumulation = True
        
        # ============================================
        # 构建三日历史数据 (用于展示) - 扩充为 4 天
        # ============================================
        history_3d_enriched = None
        if h_today and h_yest and h_before:
            # 计算换手率
            raw_history = [h_today, h_yest, h_before]
            if h_t3:
                raw_history.append(h_t3)
                
            history_3d_enriched = []
            for d in raw_history:
                mc = d.get("market_cap", 0)
                vol = d.get("volume", 0)
                tr = vol / mc if mc > 0 else 0
                history_3d_enriched.append({
                    "volume": vol,
                    "price": d.get("price", 0),
                    "market_cap": mc,
                    "turnover": tr
                })
        
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
                "history_3d": history_3d_enriched,  # 添加数据(可能包含4天)
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
                "history_3d": history_3d_enriched  # 添加数据(可能包含4天)
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
    
    # ============================================
    # 优化: 使用 SignalArbiter 实现"赢家通吃"去重
    # ============================================
    arbiter = SignalArbiter()
    alpha_signals, anomaly_signals = arbiter.classify(
        trend_signals=trend_signals,
        accumulation_alerts=dealer_accumulation_alerts,
        distribution_alerts=dealer_distribution_alerts,
        volume_alerts=alerts
    )
    
    stats = arbiter.get_stats()
    print(f"\n📊 SignalArbiter 分类完成:")
    print(f"   🎯 Alpha 信号: {stats['alpha_total']} 个 {stats['alpha_by_type']}")
    print(f"   ⚠️ 异动警告: {stats['anomaly_total']} 个 {stats['anomaly_by_type']}")
    print(f"   📋 已处理代币: {stats['processed_symbols']} 个")
    
    # 保存吸筹/洗盘数据到本地 JSON (供 docs-viewer 使用)
    # 从 ClassifiedSignal 提取原始数据
    trend_for_save = [s.data for s in alpha_signals if s.category == SignalCategory.ALPHA_TREND]
    accum_for_save = [s.data for s in alpha_signals if s.category == SignalCategory.ALPHA_WHALE]
    dist_for_save = [s.data for s in anomaly_signals if s.category == SignalCategory.RISK_DISTRIBUTION]
    
    await _save_trend_data(
        trend_signals=trend_for_save,
        accumulation_alerts=accum_for_save,
        distribution_alerts=dist_for_save
    )

    # ============================================
    # 阶段3: 发送告警 (双流输出)
    # ============================================
    print("\n阶段3: 发送告警 (双流输出)...")
    
    # 🎯 Alpha 信号流 (High Confidence Long Setup)
    if alpha_signals:
        print(f"🎯 发送 Alpha 信号: {len(alpha_signals)} 个")
        if not debug_only:
            await _send_unified_alpha(alpha_signals)
    
    # ⚠️ 异动与风控流 (Anomalies & Risks)
    if anomaly_signals:
        print(f"⚠️ 发送异动警告: {len(anomaly_signals)} 个")
        if not debug_only:
            # 在 Alpha 与 风险/异动 流之间插入分隔符（仅两者都存在时）
            if alpha_signals:
                await send_discord_message("──────────────")
                await asyncio.sleep(0.3)
            await _send_unified_anomaly(anomaly_signals)
    
    if not alpha_signals and not anomaly_signals:
        print("未发现符合条件的信号")
    
    return {
        "alpha_signals": [s.__dict__ for s in alpha_signals],
        "anomaly_signals": [s.__dict__ for s in anomaly_signals],
        "alpha_count": len(alpha_signals),
        "anomaly_count": len(anomaly_signals),
        "stats": stats
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


# ==============================================================================
# 统一推送函数 (Unified Notification System)
# 只有两条数据流：🎯 Alpha + ⚠️ 异动
# ==============================================================================

async def _send_unified_alpha(signals: list[ClassifiedSignal], max_per_embed: int = 5):
    """发送 🎯 Alpha 信号流
    
    统一使用 Embed 格式，按子类型分组，紧凑展示。
    
    Args:
        signals: ClassifiedSignal 列表
        max_per_embed: 每个 Embed 最多展示多少个
    """
    if not signals:
        return
    
    # 按子类型分组
    by_subtype: dict[str, list[ClassifiedSignal]] = {}
    for s in signals:
        if s.sub_type not in by_subtype:
            by_subtype[s.sub_type] = []
        by_subtype[s.sub_type].append(s)
    
    # 定义子类型的展示顺序和配置
    subtype_config = {
        "ACCUMULATION_STABLE": {"title": "🎯 Alpha: 稳定吸筹", "color": 0x9B59B6, "desc": "连续3日量能稳定 + 价格横盘"},
        "WASH_COMPLETE": {"title": "🎯 Alpha: 洗盘结束", "color": 0xF1C40F, "desc": "连续缩量 + 价格企稳，卖盘枯竭"},
        "BULL_FLAG": {"title": "🎯 Alpha: 牛旗整理", "color": 0x2ECC71, "desc": "昨日放量大涨 + 今日缩量回调"},
        "ACCUMULATION_WHALE": {"title": "🎯 Alpha: 巨鲸吸筹", "color": 0x3498DB, "desc": "高置信度资金流入 (量增价平)"},
    }
    
    # 按顺序发送
    for subtype in ["WASH_COMPLETE", "ACCUMULATION_STABLE", "BULL_FLAG", "ACCUMULATION_WHALE"]:
        group = by_subtype.get(subtype, [])
        if not group:
            continue
        
        config = subtype_config.get(subtype, {"title": f"🎯 Alpha: {subtype}", "color": 0x5865F2, "desc": ""})
        await _send_compact_embed(
            title=config["title"],
            signals=group[:max_per_embed],
            total_count=len(group),
            color=config["color"],
            description=config["desc"]
        )
        await asyncio.sleep(0.3)


async def _send_unified_anomaly(signals: list[ClassifiedSignal], max_per_embed: int = 5):
    """发送 ⚠️ 异动与风控流
    
    统一使用 Embed 格式，分为出货风险和极端异动两部分。
    
    Args:
        signals: ClassifiedSignal 列表
        max_per_embed: 每个 Embed 最多展示多少个
    """
    if not signals:
        return
    
    # 分组
    distribution = [s for s in signals if s.category == SignalCategory.RISK_DISTRIBUTION]
    extreme = [s for s in signals if s.category == SignalCategory.ANOMALY_EXTREME]
    
    # 出货风险
    if distribution:
        await _send_compact_embed(
            title="⚠️ 风险: 主力出货",
            signals=distribution[:max_per_embed],
            total_count=len(distribution),
            color=0xE74C3C,  # 红色
            description="量增价跌，注意规避下跌风险"
        )
        await asyncio.sleep(0.3)
    
    # 极端异动 (包括低分吸筹和极端爆量)
    if extreme:
        await _send_compact_embed(
            title="⚠️ 异动: 极端波动",
            signals=extreme[:max_per_embed],
            total_count=len(extreme),
            color=0xE67E22,  # 橙色
            description="极端交易量变化，高风险高收益"
        )


async def _send_compact_embed(
    title: str,
    signals: list[ClassifiedSignal],
    total_count: int,
    color: int,
    description: str = ""
):
    """发送紧凑格式的 Embed (支持分页与详细3日数据)
    
    格式:
    Symbol (Name)
    💵 $Price | 💰 MC $... | FDV $...
    Vol +X% 🚀 | Price +Y% 📈 | Score 0.XX
    T-0: vol/price-change/TR
    T-1: ...
    T-2: ...
    
    Args:
        title: Embed 标题
        signals: 信号列表
        total_count: 总数量 (忽略，实际使用 signals 长度)
        color: 颜色
        description: 描述文本
    """
    if not signals:
        return
    
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    real_count = len(signals)
    
    # 构造头部信息 (Total Count & Time)
    header_title = f"{title} ({real_count}个)"
    header_description = f"⏱️ {current_time}"
    if description:
        header_description += f"\n{description}"
        
    # 分页配置
    MAX_FIELDS_PER_EMBED = 10  # 每个 Embed 最多显示多少个代币 (防止消息过长)
    chunks = [signals[i:i + MAX_FIELDS_PER_EMBED] for i in range(0, len(signals), MAX_FIELDS_PER_EMBED)]
    
    total_chunks = len(chunks)
    
    for chunk_idx, chunk in enumerate(chunks):
        fields = []
        
        for i, sig in enumerate(chunk, 1):
            # 全局序号
            global_idx = chunk_idx * MAX_FIELDS_PER_EMBED + i
            
            data = sig.data
            symbol = sig.symbol
            name = sig.name[:12]
            
            # 提取关键数据
            price = data.get("price", 0)
            market_cap = data.get("market_cap", 0)
            fdv = data.get("fdv", 0)
            vol_change = data.get("vol_change", data.get("change_24h", 0))
            price_change = data.get("price_change", 0)
            history_3d = data.get("history_3d", [])

            # 价格回填
            if (not price or price <= 0) and history_3d and isinstance(history_3d, list):
                try:
                    t0_price = history_3d[0].get("price", 0) if len(history_3d) >= 1 else 0
                    if t0_price and t0_price > 0:
                        price = t0_price
                except Exception:
                    pass
            
            # 格式化基础数值
            price_str = f"${price:.6g}" if price > 0 else "-"
            mc_str = _format_number(market_cap)
            fdv_str = _format_number(fdv)
            
            # Emoji
            vol_emoji = "🚀" if vol_change > 50 else "📈" if vol_change > 0 else "📉"
            price_emoji = "📈" if price_change > 3 else "📉" if price_change < -3 else "➡️"
            score_emoji = ConfidenceEngine.get_score_emoji(sig.score)

            # 构建 3日数据详情 (T-0, T-1, T-2)
            metrics_lines = []
            if history_3d and isinstance(history_3d, list):
                # 辅助函数: 安全获取数据
                def _get_h_data(idx):
                    if idx < len(history_3d):
                        return history_3d[idx] or {}
                    return {}
                
                t0, t1, t2 = _get_h_data(0), _get_h_data(1), _get_h_data(2)
                
                # 定义行生成逻辑
                days = [("T-0", t0), ("T-1", t1), ("T-2", t2)]
                
                # 计算价格变化需要的上日价格
                # T-0 PChg = (P0 - P1)/P1
                # T-1 PChg = (P1 - P2)/P2
                # T-2 PChg = (P2 - P3)/P3 (如果不存在P3则无法计算)
                
                # 获取价格序列用于计算涨跌幅
                p0 = t0.get("price", 0) or 0
                p1 = t1.get("price", 0) or 0
                p2 = t2.get("price", 0) or 0
                # 尝试获取 t3 用于计算 t2 的涨跌幅 (如果存在)
                t3 = _get_h_data(3)
                p3 = t3.get("price", 0) or 0
                
                prices_seq = [p0, p1, p2, p3]
                
                for d_idx, (label, day_data) in enumerate(days):
                    if not day_data:
                        continue
                        
                    vol = day_data.get("volume", 0) or 0
                    
                    # 换手率
                    tr = day_data.get("turnover", 0)
                    if not tr and market_cap > 0:
                         # 估算: 使用当天的 MC 估算 (不太准，但可用)
                         tr = vol / market_cap
                    
                    # 价格变化
                    # 注意: prices_seq 长度为 4 (p0, p1, p2, p3), d_idx 最大为 2 (T-2)
                    # 当 d_idx=2 (T-2) 时, prev_p 是 p3
                    curr_p = prices_seq[d_idx]
                    prev_p = prices_seq[d_idx + 1] if d_idx + 1 < len(prices_seq) else 0
                    
                    pchg_str = "-"
                    if prev_p > 0:
                        pchg = (curr_p - prev_p) / prev_p * 100
                        pchg_str = f"{pchg:+.1f}%"
                    
                    # 格式化单行
                    # T-X: vol / price-change / TR
                    line = f"{label}: ${_format_number(vol)} / {pchg_str} / TR {_format_turnover(tr)}"
                    metrics_lines.append(line)
            
            # 构建 field
            field_name = f"{global_idx}. {symbol} ({name})"
            reason_line = (sig.reason or "").strip() or "-"
            
            content_lines = [
                f"💵 **{price_str}** | 💰 MC ${mc_str} | FDV ${fdv_str}",
                f"Vol {vol_change:+.0f}% {vol_emoji} | Price {price_change:+.1f}% {price_emoji} | {sig.score:.2f} {score_emoji}",
            ]
            if metrics_lines:
                content_lines.extend(metrics_lines)
            content_lines.append(f"💡 {reason_line}")

            fields.append({
                "name": field_name,
                "value": "\n".join(content_lines),
                "inline": False
            })
        
        # 发送当前 chunk
        chunk_title = header_title
        if total_chunks > 1:
            chunk_title = f"{header_title} ({chunk_idx + 1}/{total_chunks})"
        
        # 底部不再重复显示时间和总数
        footer_text = "Binance Alpha Monitor"
        
        embed = {
            "title": chunk_title,
            "description": header_description if chunk_idx == 0 else "", # 描述只显示在第一页
            "color": color,
            "fields": fields,
            "footer": {"text": footer_text}
        }
        
        await _send_embed_raw(embed)
        # 避免速率限制
        if total_chunks > 1:
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



