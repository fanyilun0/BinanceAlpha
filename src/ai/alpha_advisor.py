import os
import json
import logging
import time
import random
from typing import Dict, Any, List, Optional, Tuple
import requests
from datetime import datetime

from config import DEEPSEEK_AI, DATA_DIRS, BLOCKCHAIN_PLATFORMS, BLOCK_TOKEN_LIST
from src.utils.crypto_formatter import format_project_detailed, extract_basic_info, save_crypto_data

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AlphaAdvisor:
    """币安Alpha项目投资顾问，基于当天数据生成建议"""
    
    def __init__(self):
        """初始化币安Alpha项目投资顾问"""
        self.api_url = DEEPSEEK_AI.get('api_url')
        self.model = DEEPSEEK_AI.get('model')
        self.api_key = os.getenv('DEEPSEEK_API_KEY', '')
        
        if not self.api_key:
            logger.warning("未设置DEEPSEEK_API_KEY环境变量")
    
    def _format_project_data(self, crypto: Dict[str, Any]) -> str:
        """格式化单个项目数据为文本
        
        Args:
            crypto: 项目数据字典
            
        Returns:
            str: 格式化后的项目数据文本
        """
        # 使用新的crypto_formatter模块
        project_text = format_project_detailed(crypto)
            
        return project_text

    def _filter_blocked_tokens(self, crypto_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """过滤掉被屏蔽的代币
        
        Args:
            crypto_list: 加密货币数据列表
            
        Returns:
            List[Dict[str, Any]]: 过滤后的加密货币数据列表
        """
        if not BLOCK_TOKEN_LIST or len(BLOCK_TOKEN_LIST) == 0:
            return crypto_list
        
        filtered_list = []
        blocked_count = 0
        
        for crypto in crypto_list:
            # 获取代币的标识信息
            symbol = crypto.get("symbol", "").upper()
            name = crypto.get("name", "").upper()
            id_str = str(crypto.get("id", "")).upper()
            
            # 检查是否在屏蔽列表中
            if any(block_item.upper() in [symbol, name, id_str] for block_item in BLOCK_TOKEN_LIST):
                blocked_count += 1
                continue
            
            filtered_list.append(crypto)
        
        if blocked_count > 0:
            logger.info(f"已过滤 {blocked_count} 个屏蔽代币")
        
        return filtered_list

    def _prepare_prompt(self, alpha_data: Dict[str, Any]) -> Tuple[str, str]:
        """准备提示词
        
        Args:
            alpha_data: 币安Alpha数据
            
        Returns:
            Tuple[str, str]: 平台名称和生成的提示词
        """
        crypto_list = alpha_data.get("data", {}).get("cryptoCurrencyList", [])
        date = alpha_data.get("date", "")
        platform = alpha_data.get("platform", "") # 从传入的数据中获取平台信息
        prefix = f"alpha_crypto_list_{platform}"
        
        # 过滤屏蔽代币
        crypto_list = self._filter_blocked_tokens(crypto_list)
        
        # 保存币安Alpha项目列表数据到本地文件以便调试
        self.save_list_data_for_debug(crypto_list, prefix)
        
        # 如果未直接指定平台，尝试识别平台
        if not platform and crypto_list and len(crypto_list) > 0:
            # 从配置中获取区块链平台关键词
            platform_keywords = BLOCKCHAIN_PLATFORMS
            
            # 尝试从第一个项目信息中识别平台
            first_crypto = crypto_list[0]
            platform_info = first_crypto.get("platform", {})
            platform_name = platform_info.get("name", "") if platform_info else ""
            tags = first_crypto.get("tags", [])
            platform_tags = [tag for tag in tags if isinstance(tag, str)]
            
            # 尝试从平台信息和标签中识别平台
            for p_name, keywords in platform_keywords.items():
                if (any(keyword.lower() in platform_name.lower() for keyword in keywords) or 
                    any(any(keyword.lower() in tag.lower() for tag in platform_tags) for keyword in keywords)):
                    platform = p_name
                    break
        
        # 构建全部提示词
        prompt = self._create_complete_prompt(platform, date, crypto_list)
        
        return platform, prompt
    
    def _create_complete_prompt(self, platform: str, date: str, crypto_list: List[Dict[str, Any]]) -> str:
        """创建简化的提示词，聚焦于币安官方上币要求
        
        Args:
            platform: 区块链平台名称
            date: 数据日期
            crypto_list: 加密货币数据列表
            
        Returns:
            str: 简化的提示词
        """
        # 1. 简化任务介绍
        task_intro = f"""
作为加密货币分析师，请评估以下{f"{platform}平台上的" if platform else ""}币安Alpha已流通项目中哪些最可能获得币安现货上币资格。
"""

        # 2. 简化背景和关键考量要素
        background = """
币安官方明确指出，已上线Alpha平台的流通项目上现货将主要考量四大关键因素：

1. 交易量表现：Alpha平台上保持高且持续的交易量
2. 价格稳定性：交易期间价格稳定，无重大暴跌或人为哄抬
3. 监管合规性：满足所有监管合规要求
4. 代币分配与解锁：遵守合理的代币分配和解锁计划
"""

        # 3. 简化评估标准，保留核心内容
        evaluation_criteria = """
各因素具体评估要点及权重：

1. 交易量表现（核心指标，权重45%）：
   - 24h交易量：应保持高位且稳定，与市值形成合理比例
   - 7d和30d交易量趋势：应呈现稳定或上升趋势，无大幅波动
   - 交易活跃度：包括买卖订单分布和交易地址多样性
   - VOL/MC比率：健康的24h交易量与市值的比例，反映流动性状况
   币安特别强调Alpha项目必须保持"高且持续的交易量"，是上现货的首要考量因素。

2. 价格稳定性（重要指标，权重35%）：
   - 24h、7d和30d价格变化：交易期间价格表现稳定，无重大崩盘或哄抬价格行为为。

3. 监管合规性（基础门槛，权重10%）：
   - 项目合规性：无违反相关法规风险
   - 团队背景：核心团队无不良记录，无监管风险
   - 运营透明度：信息披露充分，无隐瞒重要事项
   作为基本要求，不达标则无法获得上币机会。

4. 代币分配与解锁（基础门槛，权重10%）：
   - MC/FDV比例：反映代币解锁压力，比例越高越好
   - 代币集中度：大户持币占比，团队持币比例与锁定期
   - 近期解锁计划：近期是否有大量代币解锁
   - 代币经济模型健康度：通缩/通胀机制，代币效用
   币安要求项目"持续遵守合理的代币分配和解锁计划"，避免引起持币者恐慌。
"""

        # 4. 简化输出要求，聚焦核心输出
        output_requirements = f"""
请基于币安官方公告的四大关键考量因素，对所有{f"{platform}平台上的" if platform else ""}币安Alpha项目进行全面权重评估。

对每个代币进行以下分析并输出TOP3得分的项目：
   1. 基本信息：以表格呈现| 代币名称 | 代码 | 24h交易量 | 市值 | FDV | MC/FDV | 交易量得分(45%) | 价格稳定性得分(35%) | 合规性得分(10%) | 代币分配得分(10%) | 总评分 |(1-10分)
   2. 四大因素加权分析：
      - 交易量表现(45%)：详细分析24h/7d/30d交易量表现及VOL/MC比率
      - 价格稳定性(35%)：详细分析价格波动情况及稳定性趋势
      - 监管合规性(10%)：项目合规状况及团队背景评估
      - 代币分配与解锁(10%)：MC/FDV比例解读及代币分配合理性
   3. 总体评估：项目核心优势、主要风险点
   4. 最终加权得分：按币安权重计算的总得分

请使用markdown格式输出，确保分析准确清晰，突出数据驱动的决策依据和权重分配的影响。
"""

        # 5. 数据部分
        data_section = f"以下是当前{f"{platform}平台上的" if platform else ""}币安Alpha已流通项目数据（{date}，按市值排序）：\n"
        
        # 按市值排序项目列表
        sorted_crypto_list = sorted(
            crypto_list,
            key=lambda x: float(next((q.get("marketCap", 0) for q in x.get("quotes", []) if q.get("name") == "USD"), 0)),
            reverse=True
        )
        
        # 格式化项目数据 -- 只取前15个
        for i, crypto in enumerate(sorted_crypto_list[:15], 1):
            # 使用新的crypto_formatter模块
            project_text = self._format_project_data(crypto)
            data_section += f"{i}. {project_text}\n"
        
        # 合并所有部分为完整提示词
        complete_prompt = task_intro + background + evaluation_criteria + output_requirements + data_section
        
        return complete_prompt
    
    def get_investment_advice(self, alpha_data: Dict[str, Any], max_retries=3, retry_delay=2.0, debug=True, dry_run=False) -> Optional[str]:
        """获取投资建议
        
        Args:
            alpha_data: 币安Alpha项目数据
            max_retries: 最大重试次数
            retry_delay: 重试间隔时间（秒）
            debug: 是否启用调试模式，保存数据到文件
            dry_run: 是否仅生成提示词但不发送API请求（调试模式）
            
        Returns:
            生成的投资建议文本，如果生成失败则返回None
        """
        if not self.api_key and not dry_run:
            logger.error("未设置DEEPSEEK_API_KEY，无法获取AI建议")
            return None
        
        # 准备提示词
        platform, prompt = self._prepare_prompt(alpha_data)
        
        # 格式化平台名称用于文件命名
        platform_str = platform.lower().replace(' ', '_') if platform else "general"
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        
        # 保存提示词供调试
        os.makedirs(DATA_DIRS['prompts'], exist_ok=True)
        prompt_file = os.path.join(DATA_DIRS['prompts'], f"prompt_{timestamp}_{platform_str}.txt")
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt)
        logger.info(f"已保存{platform or '通用'}平台提示词到: {prompt_file}")
        
        # 如果是dry_run模式，到此为止直接返回
        if dry_run:
            logger.info("调试模式：已生成提示词，跳过API请求")
            return f"## 调试模式 - {platform or '通用'}平台提示词生成\n\n提示词已保存到: {prompt_file}\n\n此为调试模式，未发送API请求。"
        
        # 准备API请求参数
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": DEEPSEEK_AI.get('temperature', 0),
            "max_tokens": DEEPSEEK_AI.get('max_tokens', 2048),
            "top_p": DEEPSEEK_AI.get('top_p', 1.0),
            "stream": DEEPSEEK_AI.get('stream', False)
        }
        
        # 尝试请求API
        for attempt in range(max_retries):
            try:
                logger.info(f"正在请求AI建议，尝试 {attempt + 1}/{max_retries}")
                response = requests.post(self.api_url, headers=headers, json=payload, timeout=DEEPSEEK_AI.get('timeout', 180))
                
                if response.status_code == 200:
                    result = response.json()
                    message = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    
                    # 如果返回内容有效，保存并返回
                    if message and len(message) > 100:
                        logger.info("成功获取AI建议")
                        
                        # 保存建议到文件
                        os.makedirs(DATA_DIRS['advices'], exist_ok=True)
                        advice_file = os.path.join(DATA_DIRS['advices'], f"advice_{timestamp}_{platform_str}.md")
                        with open(advice_file, 'w', encoding='utf-8') as f:
                            f.write(message)
                        logger.info(f"已保存{platform or '通用'}平台投资建议到: {advice_file}")
                        
                        return message
                    else:
                        logger.warning(f"API返回内容过短或为空: {message}")
                else:
                    logger.error(f"API请求失败，状态码: {response.status_code}, 响应: {response.text}")
                    
            except requests.exceptions.Timeout as e:
                logger.error(f"API请求超时: {str(e)}")
            except requests.exceptions.ConnectionError as e:
                logger.error(f"API连接错误: {str(e)}")
            except Exception as e:
                logger.error(f"API请求过程中出错: {str(e)}")
            
            # 如果不是最后一次尝试，等待后重试
            if attempt < max_retries - 1:
                delay = retry_delay * (1 + random.random() * 0.5)  # 添加随机抖动，最多额外50%
                logger.info(f"等待 {delay:.2f} 秒后重试...")
                time.sleep(delay)
        
        logger.error(f"在 {max_retries} 次尝试后放弃获取AI建议")
        return None 
        

    def save_list_data_for_debug(self, crypto_list: List[Dict[str, Any]], prefix: str = ""):
        """保存币安Alpha项目列表数据到本地文件以便调试
        
        Args:
            crypto_list: 加密货币数据列表
            prefix: 文件名前缀，用于区分不同平台的数据
            
        Returns:
            str: 保存的文件路径，如果保存失败则返回None
        """
        try:
            # 创建调试数据目录
            os.makedirs(DATA_DIRS['debug'], exist_ok=True)
            
            # 获取当前时间戳
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
            
            # 保存到文件
            filename = f"{prefix}_{timestamp}.json" if prefix else f"crypto_list_{timestamp}.json"
            
            # 使用crypto_formatter模块保存数据
            file_path = save_crypto_data(crypto_list, filename, prefix)
            
            logger.info(f"已保存币安Alpha项目列表数据到: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"保存币安Alpha项目列表数据时出错: {str(e)}")
            return None