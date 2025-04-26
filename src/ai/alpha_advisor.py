import os
import json
import logging
import time
import random
from typing import Dict, Any, List, Optional, Tuple
import requests
from datetime import datetime

from config import DEEPSEEK_AI, DATA_DIRS, BLOCKCHAIN_PLATFORMS

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
        name = crypto.get("name", "未知")
        symbol = crypto.get("symbol", "未知")
        rank = crypto.get("cmcRank", "未知")
        
        # 提取价格和价格变化数据（USD）
        quotes = crypto.get("quotes", [])
        usd_quote = next((q for q in quotes if q.get("name") == "USD"), {})
        
        price = usd_quote.get("price", 0)
        percent_change_24h = usd_quote.get("percentChange24h", 0)
        percent_change_7d = usd_quote.get("percentChange7d", 0)
        percent_change_30d = usd_quote.get("percentChange30d", 0)
        market_cap = usd_quote.get("marketCap", 0)

        if market_cap == 0:
            if crypto.get("circulatingSupply", 0) > 0:
                market_cap = crypto.get("circulatingSupply", 0) * price
            else:
                market_cap = crypto.get("selfReportedCirculatingSupply", 0) * price

        fdv = price * crypto.get("totalSupply", 0)
        volume_24h = usd_quote.get("volume24h", 0)
        
        # 获取项目平台信息
        platform_info = crypto.get("platform", {})
        platform_name = platform_info.get("name", "") if platform_info else ""
        
        # 构建项目信息文本
        project_text = f"{name} ({symbol}):\n"
        project_text += f"   - 排名: {rank}\n"
        if platform_name:
            project_text += f"   - 平台: {platform_name}\n"
        project_text += f"   - 价格: ${price:.6f}\n"
        project_text += f"   - 价格变化: 24h {percent_change_24h:.2f}% | 7d {percent_change_7d:.2f}% | 30d {percent_change_30d:.2f}%\n"
        project_text += f"   - 市值: ${market_cap:.2f}\n"
        project_text += f"   - 完全稀释估值: ${fdv:.2f}\n"
        project_text += f"   - 24小时交易量: ${volume_24h:.2f}\n"
        
        # 添加项目标签信息
        tags = crypto.get("tags", [])
        if tags and isinstance(tags, list) and all(isinstance(tag, str) for tag in tags):
            project_text += f"   - 标签: {', '.join(tags[:5])}{' ...' if len(tags) > 5 else ''}\n"
            
        # 添加项目简介（如果有）
        description = crypto.get("description", "")
        if description and len(description) > 10:
            # 截取合适长度的描述
            short_desc = description[:200] + "..." if len(description) > 200 else description
            project_text += f"   - 简介: {short_desc}\n"
            
        return project_text
    
    def _create_prompt_template(self, platform: str, date: str, crypto_count: int) -> str:
        """创建提示词模板
        
        Args:
            platform: 区块链平台名称
            date: 数据日期
            crypto_count: 加密货币数量
            
        Returns:
            str: 提示词模板
        """
        # 开头部分
        intro = f"""
作为加密货币分析师，请针对以下{f"{platform}平台上的" if platform else ""}币安Alpha项目数据（{date}），分析并仅推荐3个最具投资潜力的代币。

背景说明：
币安Alpha是币安生态系统中的预上币池，专注于发掘Web3生态系统中有潜力的早期加密项目。作为币安交易所的上币渠道之一，它提高了上币审议过程的透明度。币安钱包和币安交易平台用户均可无缝访问Alpha平台，无需Web3钱包或外部转账即可直接在链上交易这些早期代币。

币安上币流程与评估标准：
1. 币安Alpha(预上币池) → 2. 币安合约 → 3. 币安现货

币安Alpha项目评估重点：
- 项目基本面：用户增长率、实际采用情况、可行商业模式、行业相关性
- 代币经济学：代币分布、持币集中度、行权计划与解锁时间表
- 技术与安全：代码质量、创新性、中心化风险、安全审计历史
- 团队背景：核心团队资质、行业经验、合规状况
- 二级市场表现：交易量、流动性深度、价格稳定性、市值与完全稀释估值比例

从Alpha进入合约/现货平台的关键指标：
- 在Alpha平台保持高且持续的交易量，表明社区和用户认可
- 价格表现稳定，无重大崩盘或人为哄抬行为
- 持续遵守合理的代币分配和解锁计划
- 项目基本面持续改善，无重大负面变化

分析要点:
1. {"关注"+platform+"生态系统的独特优势和竞争格局" if platform else "项目在整体加密生态中的定位与竞争力"}
2. {"代币在该生态中的具体作用和采用情况" if platform else "Token经济模型可持续性"}
3. 当前链上数据分析（交易量、钱包地址增长、开发者活跃度）
4. 进入币安合约和现货平台的潜力评估
5. 近期价格走势与交易量的相关性分析
6. 项目团队背景、投资方实力与执行力评估
7. 代币未来价值催化剂（路线图关键节点、解锁事件、生态系统扩张）

以下是当前{f"{platform}平台上的" if platform else ""}币安Alpha列表中的项目（按市值排序）：
"""

        # 结尾部分
        conclusion = f"""
请基于以上{f"{platform}平台上的" if platform else ""}币安Alpha项目数据，提供以下内容：

1. 仅推荐3个最具投资潜力的{""+platform+"平台" if platform else ""}代币，每个包括：
   - 代币名称和代码
   - 详细推荐理由{f"（专注于{platform}生态系统中的作用）" if platform else ""}
   - 币安上币路径评估（从Alpha到合约再到现货的可能性及时间框架）
   - 技术亮点和实际应用场景
   - 链上数据分析（交易活跃度、钱包地址增长、开发者贡献）
   - 与同类项目的对比优势

2. 每个代币的投资分析：
   - 投资风险评估（低/中/高）及具体风险点
   - 代币解锁计划及其对价格的潜在影响
   - 建议的投资时间范围（短期/中期/长期）
   - 适合的投资者类型
   - 进入币安合约/现货的主要障碍（如有）
   - 进入币安生态其他产品的可能性（如Launchpool、Megadrop、HODLer空投）

3. 投资组合建议：
   - 在所推荐的3个代币中如何分配投资比例
   - 风险分散策略：如何平衡高潜力但高风险与相对稳健的选择
   - 投资时间策略：分批建仓还是一次性投入
   - 如何跟踪这些项目的关键发展指标

请使用markdown格式输出，分析应该简明扼要但内容深入，重点关注每个项目从Alpha进入合约和现货平台的可能路径和时间表。
"""
        
        return intro, conclusion
    
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
        
        # 获取提示词模板
        intro_template, conclusion_template = self._create_prompt_template(platform, date, len(crypto_list))
        
        # 构建项目数据部分
        projects_text = ""
        for i, crypto in enumerate(crypto_list, 1):
            project_text = self._format_project_data(crypto)
            projects_text += f"{i}. {project_text}\n"
        
        # 组合最终提示词
        prompt = intro_template + projects_text + conclusion_template
        
        return platform, prompt
    
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
        

    def save_list_data_for_debug(self, data_list: List[Dict], filename_prefix: str = "list_data") -> str:
        """保存列表数据到文件用于调试
        
        Args:
            data_list: 要保存的数据列表
            filename_prefix: 文件名前缀
            
        Returns:
            保存的文件路径
        """
        try:
            # 确保调试目录存在
            data_dir = DATA_DIRS.get('data', 'data')
            os.makedirs(data_dir, exist_ok=True)
            
            # 创建文件名
            timestamp = datetime.now().strftime('%Y%m%d')
            filename = f"{filename_prefix}_{timestamp}.json"
            file_path = os.path.join(data_dir, filename)
            
            # 保存到文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data_list, f, ensure_ascii=False, indent=2)
            
            logger.info(f"已保存列表数据到: {file_path}")
            return file_path
        except Exception as e:
            logger.error(f"保存列表数据时出错: {str(e)}")
            return "" 