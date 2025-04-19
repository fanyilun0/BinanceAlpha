"""
AI顾问模块 - 提供基于大模型的投资建议

此模块负责:
1. 整合历史数据供AI分析
2. 调用DeepSeek API生成投资建议
3. 格式化和保存AI建议
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union

# 导入DeepseekAPI
from ai.deepseek import DeepseekAPI

# 导入调试保存功能
from ai.prompt import save_list_data_for_debug

# 导入配置
from config import DATA_DIRS

# 设置日志
logger = logging.getLogger(__name__)

class DeepseekAdvisor:
    """DeepSeek顾问类，提供基于DeepSeek大模型的投资建议"""
    
    def __init__(self, api_key: str = None, api_url: str = None):
        """初始化DeepSeek顾问
        
        Args:
            api_key: DeepSeek API密钥，如果未提供则使用环境变量
            api_url: DeepSeek API URL，如果未提供则使用默认URL
        """
        # 初始化DeepSeek API客户端
        self.api = DeepseekAPI(api_key=api_key, api_url=api_url)
        
        # 确保保存建议的目录存在
        self.advice_dir = os.path.join(DATA_DIRS['advices'])
        os.makedirs(self.advice_dir, exist_ok=True)
        
        logger.info("DeepSeek顾问初始化完成")
    
    def get_investment_advice(self, data_file: str, months: int = 3, last_record_id: str = None, 
                            debug: bool = False, max_retries: int = 3, retry_delay: float = 2.0, **kwargs) -> Optional[str]:
        """获取投资建议
        
        Args:
            data_file: 整合后的历史数据文件路径
            months: 分析最近几个月的数据
            last_record_id: 上次建议的记录ID，用于连续性建议
            debug: 是否开启调试模式
            max_retries: 最大重试次数
            retry_delay: 重试间隔时间（秒）
            **kwargs: 其他参数传递给API
            
        Returns:
            生成的投资建议文本，如果生成失败则返回None
        """
        # 整理和筛选数据
        filtered_data = self._prepare_data_for_ai(data_file, months)
        if not filtered_data:
            logger.error("准备AI分析数据失败")
            return None
            
        # 将筛选后的数据转为JSON字符串
        data_json = json.dumps(filtered_data, ensure_ascii=False)
        
        # 调用API生成投资建议
        logger.info(f"开始生成投资建议，使用最近{months}个月的数据...")
        
        try:
            # 生成并保存投资建议
            result = self.api.generate_and_save_investment_advice(
                data_json=data_json,
                last_record_id=last_record_id,
                debug=debug,
                max_retries=max_retries,
                retry_delay=retry_delay,
                **kwargs
            )
            
            if result.get("success"):
                # 获取建议内容和记录ID
                advice = result.get("advice")
                
                # 额外保存一份到AI建议目录
                self._save_advice_to_file(advice)
                
                logger.info(f"成功生成投资建议")
                return advice
            else:
                error = result.get("error", "未知错误")
                logger.error(f"生成投资建议失败: {error}")
                return None
                
        except Exception as e:
            logger.error(f"调用AI API生成投资建议时出错: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def _prepare_data_for_ai(self, data_file: str, months: int) -> List[Dict]:
        """准备用于AI分析的数据
        
        Args:
            data_file: 整合后的历史数据文件路径
            months: 分析最近几个月的数据
            
        Returns:
            筛选后的历史数据列表
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(data_file):
                logger.error(f"数据文件不存在: {data_file}")
                return []
                
            # 读取整合后的数据
            with open(data_file, 'r', encoding='utf-8') as f:
                file_content = f.read()
                
            # 尝试解析JSON数据
            try:
                all_data = json.loads(file_content)
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析错误: {e}")
                logger.debug(f"文件内容预览: {file_content[:200]}...")
                return []
            
            # 保存原始数据供调试
            raw_data = []
            if isinstance(all_data, list):
                raw_data = all_data
            elif isinstance(all_data, dict) and 'responses' in all_data:
                raw_data = all_data['responses']
            else:
                raw_data = [all_data]
            save_list_data_for_debug(raw_data, "ai_advisor_raw_data")
                
            # 验证数据类型    
            if not isinstance(all_data, list):
                logger.error(f"数据格式错误: 期望列表类型，获取到 {type(all_data).__name__}")
                # 如果是字典类型，尝试获取数据数组
                if isinstance(all_data, dict) and 'data' in all_data and isinstance(all_data['data'], list):
                    all_data = all_data['data']
                    logger.info("从字典中提取数据数组")
                # 如果是字典类型，查找responses字段
                elif isinstance(all_data, dict) and 'responses' in all_data and isinstance(all_data['responses'], list):
                    all_data = all_data['responses']
                    logger.info("从responses中提取数据数组")
                else:
                    # 尝试将JSON字符串再次解析
                    try:
                        if isinstance(all_data, str):
                            all_data = json.loads(all_data)
                            if isinstance(all_data, list):
                                logger.info("成功将字符串解析为数据列表")
                            else:
                                logger.error("解析后仍不是列表类型")
                                return []
                        else:
                            return []
                    except:
                        return []
            
            # 验证每个数据项是否为字典
            if all_data and not all(isinstance(item, dict) for item in all_data):
                logger.error("数据格式错误: 列表中的项不全是字典类型")
                return []
            
            # 计算月份起始日期
            today = datetime.today()
            start_date = (today - timedelta(days=30 * months)).strftime('%Y-%m-%d')
            
            # 筛选指定月份的数据
            filtered_data = []
            for item in all_data:
                if not isinstance(item, dict):
                    continue
                    
                date_str = item.get('date')
                if not date_str or not isinstance(date_str, str):
                    continue
                    
                if date_str >= start_date:
                    filtered_data.append(item)
            
            # 检查是否成功筛选到数据
            if not filtered_data:
                logger.warning(f"没有找到从 {start_date} 开始的数据")
                # 如果没有筛选到数据，返回所有数据（但限制数量）
                filtered_data = all_data[:min(100, len(all_data))]
                logger.info(f"返回所有可用数据（最多100条）")
            
            # 按日期降序排序（最新的在前）
            filtered_data.sort(key=lambda x: x.get('date', ''), reverse=True)
            
            # 保存筛选后的数据
            save_list_data_for_debug(filtered_data, "ai_advisor_filtered_data")
            
            logger.info(f"已准备{len(filtered_data)}条数据供AI分析，时间范围: {filtered_data[-1]['date'] if filtered_data else 'N/A'} 至 {filtered_data[0]['date'] if filtered_data else 'N/A'}")
            return filtered_data
            
        except Exception as e:
            logger.error(f"准备AI分析数据时出错: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return []
    
    def _save_advice_to_file(self, advice: str) -> bool:
        """将投资建议保存到文件
        
        Args:
            advice: 投资建议文本
            
        Returns:
            是否成功保存
        """
        try:
            # 生成文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"advice_{timestamp}.txt"
            filepath = os.path.join(self.advice_dir, filename)
            
            # 保存建议到文件
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(advice)
            
            logger.info(f"投资建议已保存到: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"保存投资建议到文件时出错: {str(e)}")
            return False

# 使用示例
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # 测试AI顾问功能
    advisor = DeepseekAdvisor()
    advice = advisor.get_investment_advice("data/daily_data.json")
    if advice:
        print("\n========== AI投资建议摘要 ==========")
        print(advice)
        print("====================================\n") 