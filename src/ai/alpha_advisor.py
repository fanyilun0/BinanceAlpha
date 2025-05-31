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
        """初始化币安Alpha项目投资顾问"""
        self.api_url = DEEPSEEK_AI.get('api_url')
        self.model = DEEPSEEK_AI.get('model')
        self.api_key = DEEPSEEK_AI.get('api_key')
        
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

请按以下顺序输出分析结果：

一、总结部分（TOP3项目）
1. 快速概览：以表格形式展示TOP3项目的基本信息和总评分
   | 代币名称 | 代码 | 24h交易量 | 市值 | FDV | MC/FDV | 总评分(1-10分) |
2. 核心优势：每个TOP3项目的1-2个最突出的优势
3. 主要风险：每个TOP3项目的1-2个主要风险点

二、详细分析（TOP3项目）
对每个TOP3项目进行以下详细分析：
1. 基本信息：以表格呈现| 代币名称 | 代码 | 24h交易量 | 市值 | FDV | MC/FDV | 交易量得分(45%) | 价格稳定性得分(35%) | 合规性得分(10%) | 代币分配得分(10%) | 总评分 |
2. 四大因素加权分析：
   - 交易量表现(45%)：详细分析24h/7d/30d交易量表现及VOL/MC比率
   - 价格稳定性(35%)：详细分析价格波动情况及稳定性趋势
   - 监管合规性(10%)：项目合规状况及团队背景评估
   - 代币分配与解锁(10%)：MC/FDV比例解读及代币分配合理性
3. 最终加权得分：按币安权重计算的总得分及具体计算过程

确保分析准确清晰，突出数据驱动的决策依据和权重分配的影响。
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
        
        # 准备API请求参数 - 优化超时设置
        base_timeout = DEEPSEEK_AI.get('timeout', 600)
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
            "max_tokens": DEEPSEEK_AI.get('max_tokens', 32000),
            "top_p": DEEPSEEK_AI.get('top_p', 1.0),
            "stream": DEEPSEEK_AI.get('stream', False)
        }
        
        # 尝试请求API
        for attempt in range(max_retries):
            last_exception = None  # 初始化异常变量
            try:
                # 动态调整超时时间：第一次使用基础超时，后续尝试逐渐增加
                current_timeout = base_timeout + (attempt * 300)  # 每次重试增加5分钟
                
                logger.info(f"正在请求AI建议，尝试 {attempt + 1}/{max_retries}，超时设置: {current_timeout}秒")
                
                # 使用计时器测量请求时间
                def make_request():
                    return requests.post(
                        self.api_url, 
                        headers=headers, 
                        json=payload, 
                        timeout=current_timeout
                    )
                
                response, request_time = self._measure_request_time(make_request)
                
                logger.info(f"API请求完成，耗时: {request_time:.2f}秒，状态码: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # 处理deepseek-reasoner模型的特殊响应格式
                    choice = result.get("choices", [{}])[0]
                    message_data = choice.get("message", {})
                    
                    # 获取主要内容
                    content = message_data.get("content", "")
                    
                    # 检查是否有reasoning_content（deepseek-reasoner模型特有）
                    reasoning_content = message_data.get("reasoning_content", "")
                    
                    # 记录响应详细信息
                    usage_info = result.get("usage", {})
                    if usage_info:
                        logger.info(f"API使用统计 - 输入tokens: {usage_info.get('prompt_tokens', 'N/A')}, "
                                  f"输出tokens: {usage_info.get('completion_tokens', 'N/A')}, "
                                  f"总tokens: {usage_info.get('total_tokens', 'N/A')}")
                    
                    # 记录推理内容信息（如果存在）
                    if reasoning_content:
                        logger.info(f"检测到推理内容，长度: {len(reasoning_content)}字符")
                        logger.debug(f"推理内容预览: {reasoning_content[:200]}...")
                    
                    # 决定使用哪个内容作为最终结果
                    final_message = content
                    
                    # 如果content为空但有reasoning_content，考虑使用reasoning_content
                    if not content.strip() and reasoning_content.strip():
                        logger.warning("主要内容为空，但存在推理内容。这可能是因为max_tokens不足导致content被截断")
                        logger.info("尝试使用推理内容作为备选方案")
                        
                        # 可以选择使用推理内容，或者提示用户增加max_tokens
                        # 这里我们记录详细信息，但不直接使用推理内容，因为它通常不是最终答案
                        final_message = f"⚠️ 检测到响应被截断\n\n推理过程长度: {len(reasoning_content)}字符\n最终内容长度: {len(content)}字符\n\n建议增加max_tokens配置以获得完整响应。\n\n推理内容摘要:\n{reasoning_content[:500]}..."
                    
                    # 如果返回内容有效，保存并返回
                    if final_message and len(final_message) > 100:
                        logger.info(f"成功获取AI建议，响应长度: {len(final_message)}字符，总耗时: {request_time:.2f}秒")
                        
                        # 如果使用了推理内容作为备选，记录警告
                        if not content.strip() and reasoning_content.strip():
                            logger.warning("返回的是基于推理内容的摘要，建议增加max_tokens获得完整响应")
                        
                        return final_message
                    else:
                        logger.warning(f"API返回内容过短或为空，content长度: {len(content)}字符，reasoning_content长度: {len(reasoning_content)}字符，耗时: {request_time:.2f}秒")
                        logger.debug(f"返回的content: {content}")
                        if reasoning_content:
                            logger.debug(f"推理内容预览: {reasoning_content[:200]}...")
                        
                        # 如果返回空内容，可能是模型处理时间过长，尝试增加超时时间
                        if attempt < max_retries - 1:
                            logger.info("检测到空响应，将在下次重试时增加超时时间")
                        # 设置一个标识，表示这是空响应而不是异常
                        last_exception = "empty_response"
                else:
                    logger.error(f"API请求失败，状态码: {response.status_code}, 耗时: {request_time:.2f}秒")
                    logger.error(f"响应内容: {response.text}")
                    # 设置一个标识，表示这是HTTP错误
                    last_exception = f"http_error_{response.status_code}"
                    
            except requests.exceptions.Timeout as e:
                logger.error(f"API请求超时 (设置: {current_timeout}秒): {str(e)}")
                if attempt < max_retries - 1:
                    logger.info(f"将在下次重试时增加超时时间到 {base_timeout + ((attempt + 1) * 300)}秒")
                last_exception = e
            except requests.exceptions.ConnectionError as e:
                logger.error(f"API连接错误: {str(e)}")
                last_exception = e
            except Exception as e:
                logger.error(f"API请求过程中出错: {str(e)}")
                last_exception = e
            
            # 如果不是最后一次尝试，等待后重试
            if attempt < max_retries - 1:
                # 根据失败原因调整重试延迟
                if last_exception and (
                    (isinstance(last_exception, Exception) and "timeout" in str(last_exception).lower()) or
                    last_exception == "empty_response"
                ):
                    delay = retry_delay * 2  # 超时错误或空响应延迟更长
                else:
                    delay = retry_delay * (1 + random.random() * 0.5)  # 添加随机抖动
                
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

    def _measure_request_time(self, func, *args, **kwargs):
        """测量请求执行时间的装饰器函数
        
        Args:
            func: 要执行的函数
            *args: 函数参数
            **kwargs: 函数关键字参数
            
        Returns:
            tuple: (执行结果, 执行时间(秒))
        """
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            end_time = time.time()
            execution_time = end_time - start_time
            return result, execution_time
        except Exception as e:
            end_time = time.time()
            execution_time = end_time - start_time
            logger.error(f"请求执行失败，耗时: {execution_time:.2f}秒, 错误: {str(e)}")
            raise e